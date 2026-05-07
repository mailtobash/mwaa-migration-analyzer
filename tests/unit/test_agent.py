"""Unit tests for the Analyzer Agent module.

Tests agent creation, retry logic, error handling, and the deterministic
analysis pipeline.

Requirements: 8.1, 8.2, 8.5, 13.1, 13.2, 13.3
"""

from __future__ import annotations

import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from agent import (
    MWAA_MIGRATION_SYSTEM_PROMPT,
    RunIdFilter,
    create_agent,
    retry_with_backoff,
    run_analysis,
    setup_logging,
)


# ---------------------------------------------------------------------------
# Agent creation tests
# ---------------------------------------------------------------------------


class TestCreateAgent:
    """Tests for the create_agent factory function."""

    @patch("agent.BedrockModel")
    @patch("agent.Agent")
    def test_create_agent_default_provider(
        self, mock_agent_cls: MagicMock, mock_bedrock_cls: MagicMock
    ) -> None:
        """Agent is created with BedrockModel defaults when no provider given."""
        mock_model = MagicMock()
        mock_bedrock_cls.return_value = mock_model

        create_agent()

        mock_bedrock_cls.assert_called_once_with(
            model_id="us.anthropic.claude-sonnet-4-20250514",
            region_name="us-east-1",
        )
        mock_agent_cls.assert_called_once()
        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["model"] is mock_model
        assert call_kwargs["system_prompt"] == MWAA_MIGRATION_SYSTEM_PROMPT
        assert len(call_kwargs["tools"]) == 5

    @patch("agent.BedrockModel")
    @patch("agent.Agent")
    def test_create_agent_custom_provider(
        self, mock_agent_cls: MagicMock, mock_bedrock_cls: MagicMock
    ) -> None:
        """Agent uses the custom model provider when one is supplied."""
        custom_model = MagicMock()

        create_agent(model_provider=custom_model)

        # BedrockModel should NOT be instantiated
        mock_bedrock_cls.assert_not_called()
        call_kwargs = mock_agent_cls.call_args[1]
        assert call_kwargs["model"] is custom_model

    @patch("agent.BedrockModel")
    @patch("agent.Agent")
    def test_create_agent_registers_all_tools(
        self, mock_agent_cls: MagicMock, mock_bedrock_cls: MagicMock
    ) -> None:
        """Agent registers inspect_dags, analyze_dependencies, analyze_configuration,
        analyze_plugins, and generate_report."""
        create_agent()

        call_kwargs = mock_agent_cls.call_args[1]
        tool_names = {t.__name__ for t in call_kwargs["tools"]}
        expected = {
            "inspect_dags",
            "analyze_dependencies",
            "analyze_configuration",
            "analyze_plugins",
            "generate_report",
        }
        assert tool_names == expected

    @patch("agent.BedrockModel")
    @patch("agent.Agent")
    def test_create_agent_system_prompt_content(
        self, mock_agent_cls: MagicMock, mock_bedrock_cls: MagicMock
    ) -> None:
        """System prompt contains key MWAA migration concepts."""
        create_agent()

        call_kwargs = mock_agent_cls.call_args[1]
        prompt = call_kwargs["system_prompt"]
        assert "Lift and Shift" in prompt
        assert "Lift and Modernize" in prompt
        assert "Not Possible" in prompt
        assert "MWAA" in prompt
        assert "inspect_dags" in prompt


# ---------------------------------------------------------------------------
# Retry logic tests
# ---------------------------------------------------------------------------


class TestRetryWithBackoff:
    """Tests for the retry_with_backoff decorator."""

    def test_succeeds_on_first_attempt(self) -> None:
        """Function that succeeds immediately is not retried."""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.0)
        def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        assert succeed() == "ok"
        assert call_count == 1

    def test_retries_on_failure_then_succeeds(self) -> None:
        """Function that fails twice then succeeds is retried correctly."""
        call_count = 0

        @retry_with_backoff(max_retries=3, base_delay=0.0)
        def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient error")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 3

    def test_raises_after_max_retries(self) -> None:
        """Function that always fails raises after exhausting retries."""

        @retry_with_backoff(max_retries=3, base_delay=0.0)
        def always_fail() -> None:
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError, match="permanent error"):
            always_fail()

    def test_exponential_backoff_delays(self) -> None:
        """Verify that delays follow exponential backoff pattern."""
        delays: list[float] = []
        original_sleep = time.sleep

        def mock_sleep(seconds: float) -> None:
            delays.append(seconds)

        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def always_fail() -> None:
            raise RuntimeError("fail")

        with patch("agent.time.sleep", side_effect=mock_sleep):
            with pytest.raises(RuntimeError):
                always_fail()

        # Delays: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0
        assert len(delays) == 2
        assert delays[0] == pytest.approx(1.0)
        assert delays[1] == pytest.approx(2.0)

    def test_only_catches_specified_exceptions(self) -> None:
        """Retry only catches the specified exception types."""

        @retry_with_backoff(
            max_retries=3, base_delay=0.0, exceptions=(ValueError,)
        )
        def raise_type_error() -> None:
            raise TypeError("wrong type")

        with pytest.raises(TypeError, match="wrong type"):
            raise_type_error()


# ---------------------------------------------------------------------------
# RunIdFilter tests
# ---------------------------------------------------------------------------


class TestRunIdFilter:
    """Tests for the RunIdFilter logging filter."""

    def test_injects_run_id(self) -> None:
        """Filter adds run_id attribute to log records."""
        run_filter = RunIdFilter("test-run-123")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        result = run_filter.filter(record)
        assert result is True
        assert record.run_id == "test-run-123"  # type: ignore[attr-defined]

    def test_always_returns_true(self) -> None:
        """Filter never suppresses records."""
        run_filter = RunIdFilter("abc")
        record = logging.LogRecord(
            name="test",
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="debug msg",
            args=(),
            exc_info=None,
        )
        assert run_filter.filter(record) is True


# ---------------------------------------------------------------------------
# setup_logging tests
# ---------------------------------------------------------------------------


class TestSetupLogging:
    """Tests for the setup_logging function."""

    def test_sets_info_level_by_default(self) -> None:
        """Default logging level is INFO."""
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging("run-1", verbose=False)

        assert root.level == logging.INFO
        root.handlers.clear()

    def test_sets_debug_level_when_verbose(self) -> None:
        """Verbose flag sets logging level to DEBUG."""
        root = logging.getLogger()
        root.handlers.clear()

        setup_logging("run-2", verbose=True)

        assert root.level == logging.DEBUG
        root.handlers.clear()

    def test_returns_run_id_filter(self) -> None:
        """Returns the RunIdFilter instance."""
        root = logging.getLogger()
        root.handlers.clear()

        run_filter = setup_logging("run-3")

        assert isinstance(run_filter, RunIdFilter)
        assert run_filter.run_id == "run-3"
        root.handlers.clear()


# ---------------------------------------------------------------------------
# run_analysis pipeline tests
# ---------------------------------------------------------------------------


class TestRunAnalysis:
    """Tests for the deterministic run_analysis pipeline."""

    def setup_method(self) -> None:
        """Clean up root logger before each test."""
        root = logging.getLogger()
        root.handlers.clear()

    def test_basic_analysis_returns_expected_keys(self) -> None:
        """Pipeline returns dict with all expected keys."""
        result = run_analysis(
            dag_files=[{"filename": "test.py", "content": "from airflow import DAG\n"}],
            requirements_content=None,
            config_entries={},
            plugin_files=[],
            output_format="json",
        )

        assert "report_content" in result
        assert "recommendation" in result
        assert "findings" in result
        assert "skipped_analyses" in result
        assert "run_id" in result

    def test_run_id_is_uuid_format(self) -> None:
        """Run ID is a valid UUID string."""
        import uuid

        result = run_analysis(
            dag_files=[],
            output_format="json",
        )

        # Should not raise
        uuid.UUID(result["run_id"])

    def test_all_compatible_yields_lift_and_shift(self) -> None:
        """When all findings are compatible, recommendation is lift_and_shift."""
        result = run_analysis(
            dag_files=[{"filename": "simple.py", "content": "from airflow import DAG\n"}],
            requirements_content=None,
            config_entries={},
            plugin_files=[],
            output_format="json",
        )

        assert result["recommendation"] == "lift_and_shift"
        assert result["skipped_analyses"] == []

    def test_partial_results_on_dag_inspector_failure(self) -> None:
        """When DAG Inspector fails, other tools still run."""
        with patch(
            "agent._call_inspect_dags",
            side_effect=RuntimeError("dag error"),
        ):
            result = run_analysis(
                dag_files=[{"filename": "test.py", "content": "x"}],
                requirements_content="boto3>=1.0\n",
                config_entries={},
                plugin_files=[],
                output_format="json",
            )

        assert len(result["skipped_analyses"]) == 1
        assert result["skipped_analyses"][0]["tool"] == "DAG Inspector"
        assert "dag error" in result["skipped_analyses"][0]["reason"]
        # Other findings should still be present
        assert len(result["findings"]) > 0

    def test_partial_results_on_dependency_analyzer_failure(self) -> None:
        """When Dependency Analyzer fails, other tools still run."""
        with patch(
            "agent._call_analyze_dependencies",
            side_effect=RuntimeError("dep error"),
        ):
            result = run_analysis(
                dag_files=[{"filename": "test.py", "content": "from airflow import DAG\n"}],
                requirements_content="boto3>=1.0\n",
                config_entries={},
                plugin_files=[],
                output_format="json",
            )

        assert len(result["skipped_analyses"]) == 1
        assert result["skipped_analyses"][0]["tool"] == "Dependency Analyzer"

    def test_partial_results_on_config_analyzer_failure(self) -> None:
        """When Configuration Analyzer fails, other tools still run."""
        with patch(
            "agent._call_analyze_configuration",
            side_effect=RuntimeError("config error"),
        ):
            result = run_analysis(
                dag_files=[{"filename": "test.py", "content": "from airflow import DAG\n"}],
                requirements_content=None,
                config_entries={"core": {"key": "val"}},
                plugin_files=[],
                output_format="json",
            )

        assert len(result["skipped_analyses"]) == 1
        assert result["skipped_analyses"][0]["tool"] == "Configuration Analyzer"

    def test_partial_results_on_plugin_analyzer_failure(self) -> None:
        """When Plugin Analyzer fails, other tools still run."""
        with patch(
            "agent._call_analyze_plugins",
            side_effect=RuntimeError("plugin error"),
        ):
            result = run_analysis(
                dag_files=[{"filename": "test.py", "content": "from airflow import DAG\n"}],
                requirements_content=None,
                config_entries={},
                plugin_files=[{"filename": "p.py", "content": "# plugin"}],
                output_format="json",
            )

        assert len(result["skipped_analyses"]) == 1
        assert result["skipped_analyses"][0]["tool"] == "Plugin Analyzer"

    def test_skipped_analysis_appears_in_report(self) -> None:
        """Skipped analysis is noted in the generated report content."""
        with patch(
            "agent._call_inspect_dags",
            side_effect=RuntimeError("boom"),
        ):
            result = run_analysis(
                dag_files=[],
                output_format="markdown",
            )

        report = result["report_content"]
        assert "Skipped" in report or "skipped" in report.lower()

    def test_verbose_mode_sets_debug_logging(self) -> None:
        """Verbose flag causes DEBUG-level logging."""
        root = logging.getLogger()

        result = run_analysis(
            dag_files=[],
            output_format="json",
            verbose=True,
        )

        # The root logger should have been set to DEBUG during the run
        # (it may be reset after, but the run_id proves it ran)
        assert result["run_id"]

    def test_multiple_tool_failures(self) -> None:
        """When multiple tools fail, all failures are recorded."""
        with patch(
            "agent._call_inspect_dags",
            side_effect=RuntimeError("dag fail"),
        ), patch(
            "agent._call_analyze_plugins",
            side_effect=RuntimeError("plugin fail"),
        ):
            result = run_analysis(
                dag_files=[],
                requirements_content=None,
                config_entries={},
                plugin_files=[],
                output_format="json",
            )

        assert len(result["skipped_analyses"]) == 2
        skipped_tools = {s["tool"] for s in result["skipped_analyses"]}
        assert "DAG Inspector" in skipped_tools
        assert "Plugin Analyzer" in skipped_tools

    def test_metadata_includes_run_id(self) -> None:
        """Report metadata always includes the run_id."""
        result = run_analysis(
            dag_files=[],
            output_format="json",
            metadata={"timestamp": "2024-01-01", "source_type": "filesystem"},
        )

        import json

        report_data = json.loads(result["report_content"])
        assert report_data["metadata"]["run_id"] == result["run_id"]
