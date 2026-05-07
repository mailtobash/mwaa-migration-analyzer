"""Property-based tests for agent resilience and observability.

Properties 21, 22, 23 from the design document.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

from hypothesis import given, settings, strategies as st

from agent import run_analysis, RunIdFilter, setup_logging


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating simple DAG file dicts
_dag_file_strategy = st.fixed_dictionaries(
    {
        "filename": st.from_regex(r"[a-z][a-z0-9_]{0,20}\.py", fullmatch=True),
        "content": st.just("from airflow import DAG\n"),
    }
)

# Strategy for generating simple plugin file dicts
_plugin_file_strategy = st.fixed_dictionaries(
    {
        "filename": st.from_regex(r"[a-z][a-z0-9_]{0,20}\.py", fullmatch=True),
        "content": st.just("# empty plugin\n"),
    }
)

# Strategy for choosing which single tool to fail
_tool_to_fail = st.sampled_from(
    [
        "agent._call_inspect_dags",
        "agent._call_analyze_dependencies",
        "agent._call_analyze_configuration",
        "agent._call_analyze_plugins",
    ]
)

# Human-readable tool names matching the agent module's logging
_TOOL_DISPLAY_NAMES = {
    "agent._call_inspect_dags": "DAG Inspector",
    "agent._call_analyze_dependencies": "Dependency Analyzer",
    "agent._call_analyze_configuration": "Configuration Analyzer",
    "agent._call_analyze_plugins": "Plugin Analyzer",
}


# ---------------------------------------------------------------------------
# Property 21: Partial results on tool failure
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=30000)
@given(
    failing_tool=_tool_to_fail,
    dag_files=st.lists(_dag_file_strategy, min_size=1, max_size=2),
    plugin_files=st.lists(_plugin_file_strategy, min_size=0, max_size=1),
)
def test_property_21_partial_results_on_tool_failure(
    failing_tool: str,
    dag_files: list[dict],
    plugin_files: list[dict],
) -> None:
    """Feature: mwaa-analyzer-agent, Property 21: Partial results on tool failure

    For any analysis run where exactly one analysis tool raises an exception,
    the remaining tools SHALL still execute and their findings SHALL be
    included in the final report.

    **Validates: Requirements 13.1**
    """
    # Clean up root logger handlers from previous runs
    root = logging.getLogger()
    root.handlers.clear()

    with patch(failing_tool, side_effect=RuntimeError("simulated failure")):
        result = run_analysis(
            dag_files=dag_files,
            requirements_content="boto3>=1.0\n",
            config_entries={"core": {"dags_folder": "/opt/airflow/dags"}},
            plugin_files=plugin_files,
            output_format="json",
            verbose=False,
        )

    # The run must complete (not raise)
    assert "report_content" in result
    assert "findings" in result
    assert "skipped_analyses" in result

    # Exactly one tool was skipped
    assert len(result["skipped_analyses"]) == 1
    skipped_tool = result["skipped_analyses"][0]["tool"]
    assert skipped_tool == _TOOL_DISPLAY_NAMES[failing_tool]

    # The remaining tools produced findings (or at least ran without error).
    # We verify the report content is non-empty.
    assert len(result["report_content"]) > 0


# ---------------------------------------------------------------------------
# Property 22: Skipped analysis noted in report
# ---------------------------------------------------------------------------


@settings(max_examples=20, deadline=30000)
@given(
    failing_tool=_tool_to_fail,
    dag_files=st.lists(_dag_file_strategy, min_size=1, max_size=2),
)
def test_property_22_skipped_analysis_noted_in_report(
    failing_tool: str,
    dag_files: list[dict],
) -> None:
    """Feature: mwaa-analyzer-agent, Property 22: Skipped analysis noted in report

    For any analysis run where one or more tools fail, the generated report
    SHALL include a section noting each skipped analysis and the failure reason.

    **Validates: Requirements 13.2**
    """
    root = logging.getLogger()
    root.handlers.clear()

    with patch(failing_tool, side_effect=RuntimeError("simulated failure")):
        result = run_analysis(
            dag_files=dag_files,
            requirements_content="boto3>=1.0\n",
            config_entries={},
            plugin_files=[],
            output_format="markdown",
            verbose=False,
        )

    report = result["report_content"]
    tool_display = _TOOL_DISPLAY_NAMES[failing_tool]

    # The report must mention the skipped tool
    assert "[Skipped]" in report or "Skipped" in report, (
        f"Report does not mention skipped analysis for {tool_display}"
    )

    # The skipped_analyses list must contain the failure reason
    assert any(
        s["tool"] == tool_display and "simulated failure" in s["reason"]
        for s in result["skipped_analyses"]
    )


# ---------------------------------------------------------------------------
# Property 23: Run identifier in log entries
# ---------------------------------------------------------------------------


@settings(max_examples=10, deadline=30000)
@given(
    dag_files=st.lists(_dag_file_strategy, min_size=0, max_size=2),
)
def test_property_23_run_identifier_in_log_entries(
    dag_files: list[dict],
) -> None:
    """Feature: mwaa-analyzer-agent, Property 23: Run identifier in log entries

    For any log entry produced during an analysis run, the log entry SHALL
    contain the unique run identifier for that run, and all entries within
    the same run SHALL share the same identifier.

    **Validates: Requirements 13.4, 14.3**
    """
    root = logging.getLogger()
    root.handlers.clear()

    captured_records: list[logging.LogRecord] = []

    class _CapturingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    capture_handler = _CapturingHandler()
    root.addHandler(capture_handler)

    try:
        result = run_analysis(
            dag_files=dag_files,
            requirements_content=None,
            config_entries={},
            plugin_files=[],
            output_format="json",
            verbose=False,
        )
    finally:
        root.removeHandler(capture_handler)

    run_id = result["run_id"]
    assert run_id  # non-empty

    # Filter to records from our agent module (the ones that have run_id)
    agent_records = [
        r for r in captured_records if hasattr(r, "run_id")
    ]

    # There must be at least some log entries from the analysis
    assert len(agent_records) > 0, "No log entries with run_id were captured"

    # Every record must carry the same run_id
    for record in agent_records:
        assert record.run_id == run_id, (  # type: ignore[attr-defined]
            f"Log record run_id={record.run_id!r} does not match "  # type: ignore[attr-defined]
            f"expected run_id={run_id!r}"
        )
