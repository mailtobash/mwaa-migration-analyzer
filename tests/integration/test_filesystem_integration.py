"""Integration tests for the full analysis pipeline using the filesystem source type.

Tests the complete CLI → connector → analysis tools → recommendation →
report generation → output pipeline with real Airflow project files on disk.

Requirements: 1.3, 6.1, 7.1, 10.4
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from cli import cli


def _extract_json(output: str) -> dict:
    """Extract and parse the JSON object from CLI output that may contain log lines.

    The run_analysis function adds logging handlers that may write log lines
    to stderr, which the CliRunner captures alongside stdout. This helper
    finds the JSON object in the mixed output.
    """
    # Find the first '{' and match to the last '}'
    start = output.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in output:\n{output[:500]}")
    # Find the matching closing brace by counting braces
    depth = 0
    for i in range(start, len(output)):
        if output[i] == "{":
            depth += 1
        elif output[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(output[start : i + 1])
    raise ValueError(f"Unbalanced braces in output:\n{output[:500]}")


# ---------------------------------------------------------------------------
# Helpers — sample Airflow project file content
# ---------------------------------------------------------------------------

_COMPATIBLE_DAG = """\
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

with DAG(
    dag_id="compatible_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
) as dag:
    task = PythonOperator(
        task_id="hello",
        python_callable=lambda: print("hello"),
    )
"""

_SUBDAG_DAG = """\
from airflow import DAG
from airflow.operators.subdag import SubDagOperator
from datetime import datetime

with DAG(
    dag_id="subdag_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
) as dag:
    sub = SubDagOperator(
        task_id="sub_task",
        subdag=None,
    )
"""

_METADATA_DB_DAG = """\
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.settings import Session
from datetime import datetime

def query_metadata():
    session = Session()
    session.query("something")

with DAG(
    dag_id="metadata_db_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
) as dag:
    task = PythonOperator(
        task_id="query",
        python_callable=query_metadata,
    )
"""

_LOCAL_FS_DAG = """\
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def write_tmp():
    with open("/tmp/data.csv", "w") as f:
        f.write("hello")

with DAG(
    dag_id="local_fs_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
) as dag:
    task = PythonOperator(
        task_id="write",
        python_callable=write_tmp,
    )
"""

_COMPATIBLE_REQUIREMENTS = """\
boto3>=1.34.0
requests>=2.31.0
"""

_CONFLICTING_REQUIREMENTS = """\
boto3==1.20.0
numpy==1.24.0
"""

_INCOMPATIBLE_REQUIREMENTS = """\
pyodbc==5.1.0
"""

_COMPATIBLE_CONFIG = """\
[core]
executor = CeleryExecutor
"""

_UNSUPPORTED_CONFIG = """\
[webserver]
rbac = True
[core]
executor = CeleryExecutor
"""

_PATH_CONFIG = """\
[core]
dags_folder = /home/user/airflow/dags
"""

_COMPATIBLE_PLUGIN = """\
from airflow.plugins_manager import AirflowPlugin

class MyPlugin(AirflowPlugin):
    name = "my_plugin"
"""

_SUBPROCESS_PLUGIN = """\
import subprocess

def run_command():
    subprocess.run(["ls", "-la"])
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    """Create a CliRunner with clean environment."""
    return CliRunner(
        env={
            "AIRFLOW_API_ENDPOINT": "",
            "AIRFLOW_API_TOKEN": "",
            "MWAA_ENVIRONMENT_NAME": "",
            "MWAA_REGION": "",
        },
    )


def _create_airflow_project(
    base: Path,
    dags: dict[str, str] | None = None,
    requirements: str | None = None,
    config: str | None = None,
    plugins: dict[str, str] | None = None,
) -> Path:
    """Create a sample Airflow project directory structure.

    Args:
        base: The base temporary directory.
        dags: Mapping of filename → content for DAG files.
        requirements: Content for requirements.txt.
        config: Content for airflow.cfg.
        plugins: Mapping of filename → content for plugin files.

    Returns:
        The path to the created project directory.
    """
    project = base / "airflow_project"
    project.mkdir(exist_ok=True)

    if dags:
        dags_dir = project / "dags"
        dags_dir.mkdir(exist_ok=True)
        for name, content in dags.items():
            (dags_dir / name).write_text(content, encoding="utf-8")

    if requirements is not None:
        (project / "requirements.txt").write_text(requirements, encoding="utf-8")

    if config is not None:
        (project / "airflow.cfg").write_text(config, encoding="utf-8")

    if plugins:
        plugins_dir = project / "plugins"
        plugins_dir.mkdir(exist_ok=True)
        for name, content in plugins.items():
            (plugins_dir / name).write_text(content, encoding="utf-8")

    return project


# ---------------------------------------------------------------------------
# Test: All compatible — Lift and Shift
# ---------------------------------------------------------------------------


class TestFilesystemLiftAndShift:
    """End-to-end tests for environments that are fully compatible (Lift and Shift)."""

    def test_all_compatible_markdown(self, runner, tmp_path):
        """A fully compatible project should produce a Lift and Shift recommendation."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_COMPATIBLE_REQUIREMENTS,
            config=_COMPATIBLE_CONFIG,
            plugins={"my_plugin.py": _COMPATIBLE_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        # Report should contain the recommendation
        assert "Lift and Shift" in output or "lift_and_shift" in output

    def test_all_compatible_json(self, runner, tmp_path):
        """JSON output for a fully compatible project should be valid JSON with expected keys."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_COMPATIBLE_REQUIREMENTS,
            config=_COMPATIBLE_CONFIG,
            plugins={"my_plugin.py": _COMPATIBLE_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        assert "executive_summary" in report
        assert "recommendation" in report
        assert "findings_by_category" in report
        assert "action_items" in report
        assert "metadata" in report
        assert report["recommendation"] == "lift_and_shift"

    def test_all_compatible_html(self, runner, tmp_path):
        """HTML output should be self-contained with expected tags."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_COMPATIBLE_REQUIREMENTS,
            config=_COMPATIBLE_CONFIG,
            plugins={"my_plugin.py": _COMPATIBLE_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "html",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "<html" in output
        assert "<head>" in output
        assert "<body>" in output
        assert "<style>" in output

    def test_empty_project(self, runner, tmp_path):
        """An empty project (no dags, no requirements, no config, no plugins) should still produce a report."""
        project = _create_airflow_project(tmp_path)

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        # Should still produce a report with Lift and Shift (no findings = all compatible)
        assert "Lift and Shift" in result.output or "lift_and_shift" in result.output


# ---------------------------------------------------------------------------
# Test: Requires modification — Lift and Modernize
# ---------------------------------------------------------------------------


class TestFilesystemLiftAndModernize:
    """End-to-end tests for environments requiring modification (Lift and Modernize)."""

    def test_subdag_requires_modernization(self, runner, tmp_path):
        """A project with SubDagOperator should recommend Lift and Modernize."""
        project = _create_airflow_project(
            tmp_path,
            dags={"subdag_dag.py": _SUBDAG_DAG},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        # Should detect SubDAG and recommend modernization
        assert "SubDAG" in output or "SubDag" in output or "subdag" in output.lower()

    def test_metadata_db_access_requires_modernization(self, runner, tmp_path):
        """A project with direct metadata DB access should recommend Lift and Modernize."""
        project = _create_airflow_project(
            tmp_path,
            dags={"metadata_db_dag.py": _METADATA_DB_DAG},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "metadata" in output.lower() or "session" in output.lower()

    def test_local_filesystem_usage(self, runner, tmp_path):
        """A project using local filesystem paths should recommend Lift and Modernize."""
        project = _create_airflow_project(
            tmp_path,
            dags={"local_fs_dag.py": _LOCAL_FS_DAG},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "/tmp" in output or "local filesystem" in output.lower() or "S3" in output

    def test_unsupported_config_keys(self, runner, tmp_path):
        """A project with unsupported config keys should recommend Lift and Modernize."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            config=_UNSUPPORTED_CONFIG,
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        # Should flag unsupported config
        assert "unsupported" in output.lower() or "Modernize" in output or "modernize" in output.lower()

    def test_subprocess_plugin(self, runner, tmp_path):
        """A project with subprocess calls in plugins should recommend Lift and Modernize."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            plugins={"bad_plugin.py": _SUBPROCESS_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "subprocess" in output.lower() or "system resource" in output.lower()

    def test_config_with_filesystem_path(self, runner, tmp_path):
        """A project with filesystem paths in config values should flag them."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            config=_PATH_CONFIG,
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "path" in output.lower() or "filesystem" in output.lower()

    def test_modernize_json_has_action_items(self, runner, tmp_path):
        """JSON output for Lift and Modernize should include action items."""
        project = _create_airflow_project(
            tmp_path,
            dags={"subdag_dag.py": _SUBDAG_DAG},
            config=_UNSUPPORTED_CONFIG,
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        assert report["recommendation"] in ("lift_and_modernize", "not_possible")
        assert len(report["action_items"]) > 0


# ---------------------------------------------------------------------------
# Test: Incompatible — Not Possible
# ---------------------------------------------------------------------------


class TestFilesystemNotPossible:
    """End-to-end tests for environments with incompatible components (Not Possible)."""

    def test_incompatible_dependency(self, runner, tmp_path):
        """A project with incompatible system-level dependencies should recommend Not Possible."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_INCOMPATIBLE_REQUIREMENTS,
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output
        assert "Not Possible" in output or "not_possible" in output

    def test_not_possible_json_has_blockers(self, runner, tmp_path):
        """JSON output for Not Possible should include blockers."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_INCOMPATIBLE_REQUIREMENTS,
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        assert report["recommendation"] == "not_possible"
        assert "blockers" in report
        assert len(report["blockers"]) > 0


# ---------------------------------------------------------------------------
# Test: Output to file
# ---------------------------------------------------------------------------


class TestFilesystemOutputFile:
    """Test writing report output to a file."""

    def test_output_to_file(self, runner, tmp_path):
        """Report should be written to the specified output file."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
        )
        output_file = tmp_path / "report.md"

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-file", str(output_file),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Migration" in content or "migration" in content


# ---------------------------------------------------------------------------
# Test: Report sections presence
# ---------------------------------------------------------------------------


class TestReportSections:
    """Verify that reports contain all required sections."""

    def test_markdown_report_sections(self, runner, tmp_path):
        """Markdown report should contain executive summary, recommendation, findings, and metadata."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
            requirements=_COMPATIBLE_REQUIREMENTS,
            config=_COMPATIBLE_CONFIG,
            plugins={"my_plugin.py": _COMPATIBLE_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        output = result.output.lower()
        assert "executive summary" in output or "summary" in output
        assert "recommendation" in output
        assert "findings" in output or "dags" in output
        assert "metadata" in output or "version" in output

    def test_json_report_all_keys(self, runner, tmp_path):
        """JSON report should contain all required top-level keys."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG, "subdag_dag.py": _SUBDAG_DAG},
            requirements=_COMPATIBLE_REQUIREMENTS,
            config=_COMPATIBLE_CONFIG,
            plugins={"my_plugin.py": _COMPATIBLE_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        assert "executive_summary" in report
        assert "recommendation" in report
        assert "recommendation_display" in report
        assert "findings_by_category" in report
        assert "action_items" in report
        assert "metadata" in report

        # Verify findings_by_category has the expected categories
        categories = report["findings_by_category"]
        assert "DAGs" in categories
        assert "Dependencies" in categories
        assert "Configuration" in categories
        assert "Plugins" in categories

    def test_json_metadata_fields(self, runner, tmp_path):
        """JSON report metadata should contain source_type, target_mwaa_version, and tool_version."""
        project = _create_airflow_project(
            tmp_path,
            dags={"compatible_dag.py": _COMPATIBLE_DAG},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        metadata = report["metadata"]
        assert metadata["source_type"] == "filesystem"
        assert metadata["target_mwaa_version"] == "2.10.3"
        assert metadata["tool_version"] == "0.1.0"


# ---------------------------------------------------------------------------
# Test: Mixed scenarios
# ---------------------------------------------------------------------------


class TestFilesystemMixedScenarios:
    """Test scenarios with a mix of compatible and incompatible components."""

    def test_mixed_dags_compatible_and_subdag(self, runner, tmp_path):
        """A project with both compatible and SubDAG DAGs should flag the SubDAG one."""
        project = _create_airflow_project(
            tmp_path,
            dags={
                "compatible_dag.py": _COMPATIBLE_DAG,
                "subdag_dag.py": _SUBDAG_DAG,
            },
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        dag_findings = report["findings_by_category"]["DAGs"]
        # Should have findings for both DAGs
        assert len(dag_findings) == 2
        # At least one should have issues
        has_issues = any(len(f["issues"]) > 0 for f in dag_findings)
        assert has_issues

    def test_multiple_issues_across_categories(self, runner, tmp_path):
        """A project with issues in multiple categories should report all of them."""
        project = _create_airflow_project(
            tmp_path,
            dags={"subdag_dag.py": _SUBDAG_DAG},
            requirements=_CONFLICTING_REQUIREMENTS,
            config=_UNSUPPORTED_CONFIG,
            plugins={"bad_plugin.py": _SUBPROCESS_PLUGIN},
        )

        result = runner.invoke(cli, [
            "analyze",
            "--source-type", "filesystem",
            "--path", str(project),
            "--output-format", "json",
        ])

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        report = _extract_json(result.output)
        # Should have findings across multiple categories
        categories_with_findings = sum(
            1 for cat_findings in report["findings_by_category"].values()
            if len(cat_findings) > 0
        )
        assert categories_with_findings >= 2
