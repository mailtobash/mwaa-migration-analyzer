"""Unit tests for the CLI module.

Tests each source type with valid and invalid flag combinations,
output format and output file options, credential warning display,
and verbose flag behavior.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.5
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli import cli


@pytest.fixture
def runner():
    """Create a CliRunner with clean environment (no credential env vars)."""
    return CliRunner(env={
        "AIRFLOW_API_ENDPOINT": "",
        "AIRFLOW_API_TOKEN": "",
        "MWAA_ENVIRONMENT_NAME": "",
        "MWAA_REGION": "",
    })


@pytest.fixture
def mock_run_analysis():
    """Mock run_analysis to return a minimal valid result."""
    with patch("cli.run_analysis") as mock:
        mock.return_value = {
            "report_content": "# Migration Report\n\nAll compatible.",
            "recommendation": "lift_and_shift",
            "findings": [],
            "skipped_analyses": [],
            "run_id": "test-run-id",
        }
        yield mock


def _make_mock_connector():
    """Create a mock connector that returns empty environment data."""
    connector = MagicMock()
    connector.connect.return_value = None
    connector.get_dags.return_value = []
    connector.get_requirements.return_value = None
    connector.get_configuration.return_value = {}
    connector.get_plugins.return_value = []
    connector.get_metadata.return_value = MagicMock(
        airflow_version=None,
        source_type="filesystem",
        dag_count=0,
        plugin_count=0,
        has_requirements=False,
        has_configuration=False,
    )
    return connector


# -----------------------------------------------------------------------
# Invalid flag combination tests
# -----------------------------------------------------------------------


class TestInvalidFlagCombinations:
    """Test that invalid flag combinations produce errors."""

    def test_api_missing_endpoint(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "api", "--token", "my-token"
        ])
        assert result.exit_code != 0
        assert "endpoint" in result.output.lower() or "endpoint" in (result.stderr if hasattr(result, 'stderr') else "").lower()

    def test_api_missing_token(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "api", "--endpoint", "https://example.com"
        ])
        assert result.exit_code != 0
        assert "token" in result.output.lower() or "token" in (result.stderr if hasattr(result, 'stderr') else "").lower()

    def test_api_missing_both(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "api"
        ])
        assert result.exit_code != 0

    def test_mwaa_missing_environment_name(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "mwaa", "--region", "us-east-1"
        ])
        assert result.exit_code != 0
        assert "environment-name" in result.output.lower() or "environment_name" in result.output.lower()

    def test_mwaa_missing_region(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "mwaa", "--environment-name", "my-env"
        ])
        assert result.exit_code != 0
        assert "region" in result.output.lower()

    def test_mwaa_missing_both(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "mwaa"
        ])
        assert result.exit_code != 0

    def test_filesystem_missing_path(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem"
        ])
        assert result.exit_code != 0
        assert "path" in result.output.lower()


# -----------------------------------------------------------------------
# Valid flag combination tests
# -----------------------------------------------------------------------


class TestValidFlagCombinations:
    """Test that valid flag combinations work correctly."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_filesystem_valid(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem", "--path", str(tmp_path)
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        mock_create_connector.assert_called_once()

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_api_valid(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "api",
            "--endpoint", "https://airflow.example.com",
            "--token", "my-secret-token",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        mock_create_connector.assert_called_once()

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_mwaa_valid(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "mwaa",
            "--environment-name", "my-env",
            "--region", "us-east-1",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        mock_create_connector.assert_called_once()


# -----------------------------------------------------------------------
# Environment variable credential tests
# -----------------------------------------------------------------------


class TestEnvironmentVariableCredentials:
    """Test that credentials can be provided via environment variables."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_api_credentials_from_env(self, mock_create_connector, mock_telemetry_cls, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        env_runner = CliRunner(env={
            "AIRFLOW_API_ENDPOINT": "https://airflow.example.com",
            "AIRFLOW_API_TOKEN": "env-token-value",
            "MWAA_ENVIRONMENT_NAME": "",
            "MWAA_REGION": "",
        })
        result = env_runner.invoke(cli, [
            "analyze", "--source-type", "api"
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_mwaa_credentials_from_env(self, mock_create_connector, mock_telemetry_cls, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        env_runner = CliRunner(env={
            "AIRFLOW_API_ENDPOINT": "",
            "AIRFLOW_API_TOKEN": "",
            "MWAA_ENVIRONMENT_NAME": "my-env",
            "MWAA_REGION": "us-west-2",
        })
        result = env_runner.invoke(cli, [
            "analyze", "--source-type", "mwaa"
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"


# -----------------------------------------------------------------------
# Credential warning tests
# -----------------------------------------------------------------------


class TestCredentialWarning:
    """Test that credential warnings are displayed when CLI flags are used."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_warning_shown_for_api_cli_flags(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "api",
            "--endpoint", "https://airflow.example.com",
            "--token", "my-secret-token",
        ])
        assert result.exit_code == 0
        assert "WARNING" in result.output or "shell history" in result.output

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_no_warning_for_env_var_credentials(self, mock_create_connector, mock_telemetry_cls, mock_run_analysis):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        env_runner = CliRunner(env={
            "AIRFLOW_API_ENDPOINT": "https://airflow.example.com",
            "AIRFLOW_API_TOKEN": "env-token-value",
            "MWAA_ENVIRONMENT_NAME": "",
            "MWAA_REGION": "",
        })
        result = env_runner.invoke(cli, [
            "analyze", "--source-type", "api"
        ])
        assert result.exit_code == 0
        assert "shell history" not in result.output


# -----------------------------------------------------------------------
# Output format and file tests
# -----------------------------------------------------------------------


class TestOutputOptions:
    """Test output format and output file options."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_output_format_json(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
            "--output-format", "json",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        # Verify run_analysis was called with json format
        mock_run_analysis.assert_called_once()
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["output_format"] == "json"

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_output_format_html(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
            "--output-format", "html",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["output_format"] == "html"

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_output_file(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        output_path = str(tmp_path / "report.md")
        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
            "--output-file", output_path,
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        # Verify the file was written
        with open(output_path) as f:
            content = f.read()
        assert "Migration Report" in content

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_output_to_stdout(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
        ])
        assert result.exit_code == 0
        assert "Migration Report" in result.output


# -----------------------------------------------------------------------
# Target MWAA version tests
# -----------------------------------------------------------------------


class TestTargetMwaaVersion:
    """Test target MWAA version flag."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_custom_target_version(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
            "--target-mwaa-version", "2.8.1",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["target_mwaa_version"] == "2.8.1"

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_default_target_version(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["target_mwaa_version"] == "2.10.3"


# -----------------------------------------------------------------------
# Verbose flag tests
# -----------------------------------------------------------------------


class TestVerboseFlag:
    """Test verbose flag behavior."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_verbose_passed_to_analysis(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
            "--verbose",
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["verbose"] is True

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_no_verbose_by_default(self, mock_create_connector, mock_telemetry_cls, runner, mock_run_analysis, tmp_path):
        mock_create_connector.return_value = _make_mock_connector()
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "filesystem",
            "--path", str(tmp_path),
        ])
        assert result.exit_code == 0, f"Unexpected error: {result.output}"
        call_kwargs = mock_run_analysis.call_args[1]
        assert call_kwargs["verbose"] is False


# -----------------------------------------------------------------------
# Error handling tests
# -----------------------------------------------------------------------


class TestErrorHandling:
    """Test error handling for connector failures."""

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_connection_error(self, mock_create_connector, mock_telemetry_cls, runner):
        connector = _make_mock_connector()
        connector.connect.side_effect = ConnectionError("Auth failed")
        mock_create_connector.return_value = connector
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "api",
            "--endpoint", "https://airflow.example.com",
            "--token", "bad-token",
        ])
        assert result.exit_code != 0
        assert "Auth failed" in result.output

    @patch("cli.TelemetryCollector")
    @patch("cli.create_connector")
    def test_timeout_error(self, mock_create_connector, mock_telemetry_cls, runner):
        connector = _make_mock_connector()
        connector.connect.side_effect = TimeoutError("Connection timed out")
        mock_create_connector.return_value = connector
        mock_telemetry_cls.return_value = MagicMock()

        result = runner.invoke(cli, [
            "analyze", "--source-type", "api",
            "--endpoint", "https://airflow.example.com",
            "--token", "my-token",
        ])
        assert result.exit_code != 0
        assert "timed out" in result.output

    def test_invalid_source_type(self, runner):
        result = runner.invoke(cli, [
            "analyze", "--source-type", "invalid"
        ])
        assert result.exit_code != 0
