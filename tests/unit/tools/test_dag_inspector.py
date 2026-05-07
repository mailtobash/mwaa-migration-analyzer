"""Unit tests for the DAG Inspector tool.

Tests DAG Inspector with sample DAG files, edge cases, and individual
helper functions.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import pytest

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.dag_inspector import (
    detect_local_filesystem_paths,
    detect_metadata_db_access,
    detect_subdag_usage,
    detect_unsupported_operators,
    extract_imports,
    inspect_dags,
)
from data_loader import load_manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manifest():
    """Load the 2.10.3 MWAA version manifest."""
    return load_manifest("2.10.3")


# ---------------------------------------------------------------------------
# Helper: extract_imports
# ---------------------------------------------------------------------------


class TestExtractImports:
    """Tests for the extract_imports helper function."""

    def test_from_import_single(self):
        source = "from airflow.operators.python import PythonOperator\n"
        result = extract_imports(source)
        assert "airflow.operators.python.PythonOperator" in result

    def test_from_import_multiple_statements(self):
        source = (
            "from airflow.operators.python import PythonOperator\n"
            "from airflow.operators.bash import BashOperator\n"
        )
        result = extract_imports(source)
        assert "airflow.operators.python.PythonOperator" in result
        assert "airflow.operators.bash.BashOperator" in result

    def test_regular_import(self):
        source = "import os\nimport json\n"
        result = extract_imports(source)
        assert "os" in result
        assert "json" in result

    def test_from_import_with_multiple_names(self):
        source = "from airflow.operators.python import PythonOperator, BranchPythonOperator\n"
        result = extract_imports(source)
        assert "airflow.operators.python.PythonOperator" in result
        assert "airflow.operators.python.BranchPythonOperator" in result

    def test_syntax_error_returns_empty(self):
        source = "def broken(\n"
        result = extract_imports(source)
        assert result == set()

    def test_empty_source(self):
        result = extract_imports("")
        assert result == set()

    def test_no_imports(self):
        source = "x = 1\ny = 2\n"
        result = extract_imports(source)
        assert result == set()

    def test_provider_imports(self):
        source = "from airflow.providers.amazon.aws.operators.s3 import S3CreateBucketOperator\n"
        result = extract_imports(source)
        assert "airflow.providers.amazon.aws.operators.s3.S3CreateBucketOperator" in result

    def test_dotted_import(self):
        source = "import airflow.operators.python\n"
        result = extract_imports(source)
        assert "airflow.operators.python" in result


# ---------------------------------------------------------------------------
# Helper: detect_unsupported_operators
# ---------------------------------------------------------------------------


class TestDetectUnsupportedOperators:
    """Tests for the detect_unsupported_operators helper function."""

    def test_supported_operator_no_issues(self, manifest):
        imports = {"airflow.operators.python.PythonOperator"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 0

    def test_unsupported_operator_flagged(self, manifest):
        imports = {"airflow.operators.custom.MyCustomOperator"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 1
        assert "MyCustomOperator" in issues[0]

    def test_mixed_supported_and_unsupported(self, manifest):
        imports = {
            "airflow.operators.python.PythonOperator",
            "airflow.operators.bash.BashOperator",
            "airflow.operators.custom.FakeOperator",
        }
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 1
        assert "FakeOperator" in issues[0]

    def test_non_airflow_imports_ignored(self, manifest):
        imports = {"pandas", "numpy", "os"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 0

    def test_supported_provider_operator(self, manifest):
        imports = {"airflow.providers.amazon.aws.operators.s3.S3CreateBucketOperator"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 0

    def test_unsupported_provider_operator(self, manifest):
        imports = {"airflow.providers.google.cloud.operators.bigquery.BigQueryOperator"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 1

    def test_empty_imports(self, manifest):
        issues = detect_unsupported_operators(set(), manifest)
        assert len(issues) == 0

    def test_supported_sensor(self, manifest):
        imports = {"airflow.sensors.external_task.ExternalTaskSensor"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 0

    def test_supported_hook(self, manifest):
        imports = {"airflow.providers.amazon.aws.hooks.s3.S3Hook"}
        issues = detect_unsupported_operators(imports, manifest)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_metadata_db_access
# ---------------------------------------------------------------------------


class TestDetectMetadataDbAccess:
    """Tests for the detect_metadata_db_access helper function."""

    def test_session_import_detected(self):
        source = "from airflow.settings import Session\nsession = Session()\n"
        issues = detect_metadata_db_access(source)
        assert len(issues) >= 1
        assert any("Session" in i for i in issues)

    def test_settings_session_detected(self):
        source = "from airflow import settings\ns = settings.Session()\n"
        issues = detect_metadata_db_access(source)
        assert len(issues) >= 1

    def test_session_query_detected(self):
        source = "result = session.query(DagRun).all()\n"
        issues = detect_metadata_db_access(source)
        assert len(issues) >= 1
        assert any("session.query" in i for i in issues)

    def test_metadata_bind_detected(self):
        source = "engine = metadata.bind\n"
        issues = detect_metadata_db_access(source)
        assert len(issues) >= 1

    def test_clean_source_no_issues(self):
        source = "from airflow.operators.python import PythonOperator\n"
        issues = detect_metadata_db_access(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_metadata_db_access("")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_subdag_usage
# ---------------------------------------------------------------------------


class TestDetectSubdagUsage:
    """Tests for the detect_subdag_usage helper function."""

    def test_subdag_import_detected(self):
        source = "from airflow.operators.subdag import SubDagOperator\n"
        issues = detect_subdag_usage(source)
        assert len(issues) == 1
        assert "SubDagOperator" in issues[0]

    def test_subdag_usage_detected(self):
        source = "task = SubDagOperator(task_id='sub', subdag=my_subdag)\n"
        issues = detect_subdag_usage(source)
        assert len(issues) == 1

    def test_no_subdag_no_issues(self):
        source = "from airflow.operators.python import PythonOperator\n"
        issues = detect_subdag_usage(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_subdag_usage("")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_local_filesystem_paths
# ---------------------------------------------------------------------------


class TestDetectLocalFilesystemPaths:
    """Tests for the detect_local_filesystem_paths helper function."""

    def test_tmp_path_detected(self):
        source = 'path = "/tmp/data.csv"\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) >= 1
        assert any("/tmp/" in i for i in issues)

    def test_open_write_detected(self):
        source = 'f = open("/some/path", "w")\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) >= 1

    def test_home_path_detected(self):
        source = 'data = "/home/user/data.txt"\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) >= 1

    def test_var_path_detected(self):
        source = 'log = "/var/log/airflow.log"\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) >= 1

    def test_opt_path_detected(self):
        source = 'config = "/opt/airflow/config.yaml"\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) >= 1

    def test_clean_source_no_issues(self):
        source = "x = 1\ny = 2\n"
        issues = detect_local_filesystem_paths(source)
        assert len(issues) == 0

    def test_s3_path_not_flagged(self):
        source = 'path = "s3://my-bucket/data.csv"\n'
        issues = detect_local_filesystem_paths(source)
        assert len(issues) == 0

    def test_open_append_mode_detected(self):
        source = 'f = open("output.txt", "a")\n'
        issues = detect_local_filesystem_paths(source)
        assert any("writing" in i.lower() for i in issues)

    def test_empty_source_no_issues(self):
        issues = detect_local_filesystem_paths("")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# inspect_dags tool: compatible DAGs
# ---------------------------------------------------------------------------


class TestInspectDagsCompatible:
    """Test inspect_dags with DAGs that should be fully compatible."""

    def test_compatible_dag_python_operator(self):
        source = (
            "from airflow import DAG\n"
            "from airflow.operators.python import PythonOperator\n"
            "from datetime import datetime\n"
            "\n"
            "with DAG('my_dag', start_date=datetime(2024, 1, 1)) as dag:\n"
            "    task = PythonOperator(task_id='task', python_callable=lambda: None)\n"
        )
        dag_files = [{"filename": "my_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["issues"] == []

    def test_compatible_dag_bash_operator(self):
        source = (
            "from airflow import DAG\n"
            "from airflow.operators.bash import BashOperator\n"
            "from datetime import datetime\n"
            "\n"
            "with DAG('bash_dag', start_date=datetime(2024, 1, 1)) as dag:\n"
            "    task = BashOperator(task_id='task', bash_command='echo hello')\n"
        )
        dag_files = [{"filename": "bash_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_compatible_dag_multiple_supported_operators(self):
        """A DAG with only supported operators should have no issues."""
        source = (
            "from airflow import DAG\n"
            "from airflow.operators.python import PythonOperator\n"
            "from airflow.operators.bash import BashOperator\n"
            "from airflow.sensors.external_task import ExternalTaskSensor\n"
            "from datetime import datetime\n"
            "\n"
            "with DAG('clean_dag', start_date=datetime(2024, 1, 1)) as dag:\n"
            "    pass\n"
        )
        dag_files = [{"filename": "clean_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["issues"] == []


# ---------------------------------------------------------------------------
# inspect_dags tool: requires_modification DAGs
# ---------------------------------------------------------------------------


class TestInspectDagsRequiresModification:
    """Test inspect_dags with DAGs that require modification."""

    def test_subdag_flagged(self):
        source = (
            "from airflow import DAG\n"
            "from airflow.operators.subdag import SubDagOperator\n"
            "from datetime import datetime\n"
            "\n"
            "with DAG('parent_dag', start_date=datetime(2024, 1, 1)) as dag:\n"
            "    sub = SubDagOperator(task_id='sub', subdag=None)\n"
        )
        dag_files = [{"filename": "subdag_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] != CompatibilityStatus.COMPATIBLE.value
        assert any(
            "SubDAG" in issue or "SubDag" in issue
            for issue in findings[0]["issues"]
        )

    def test_sqlalchemy_session_flagged(self):
        source = (
            "from airflow.settings import Session\n"
            "from airflow.models import DagRun\n"
            "\n"
            "session = Session()\n"
            "runs = session.query(DagRun).all()\n"
        )
        dag_files = [{"filename": "db_access_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any(
            "metadata DB" in issue or "Session" in issue
            for issue in findings[0]["issues"]
        )

    def test_tmp_path_flagged(self):
        source = (
            "from airflow import DAG\n"
            "from airflow.operators.python import PythonOperator\n"
            "\n"
            "def process():\n"
            '    with open("/tmp/data.csv", "w") as f:\n'
            "        f.write('hello')\n"
        )
        dag_files = [{"filename": "local_path_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any(
            "filesystem" in issue.lower() or "/tmp/" in issue
            for issue in findings[0]["issues"]
        )

    def test_recommendations_present_for_issues(self):
        """When issues are found, recommendations should be provided."""
        source = (
            "from airflow.settings import Session\n"
            "session = Session()\n"
        )
        dag_files = [{"filename": "rec_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0


# ---------------------------------------------------------------------------
# inspect_dags tool: incompatible DAGs
# ---------------------------------------------------------------------------


class TestInspectDagsIncompatible:
    """Test inspect_dags with DAGs that are incompatible."""

    def test_unsupported_operator_incompatible(self):
        source = (
            "from airflow import DAG\n"
            "from airflow.providers.google.cloud.operators.bigquery import BigQueryOperator\n"
            "from datetime import datetime\n"
            "\n"
            "with DAG('gcp_dag', start_date=datetime(2024, 1, 1)) as dag:\n"
            "    task = BigQueryOperator(task_id='bq')\n"
        )
        dag_files = [{"filename": "gcp_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.INCOMPATIBLE.value
        assert any("Unsupported" in issue for issue in findings[0]["issues"])


# ---------------------------------------------------------------------------
# inspect_dags tool: edge cases
# ---------------------------------------------------------------------------


class TestInspectDagsEdgeCases:
    """Test inspect_dags with edge cases."""

    def test_empty_dag_file(self):
        dag_files = [{"filename": "empty.py", "content": ""}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["identifier"] == "empty.py"

    def test_syntax_error_dag(self):
        source = "def broken(\n  invalid syntax here\n"
        dag_files = [{"filename": "broken.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any(
            "syntax" in issue.lower() or "Syntax" in issue
            for issue in findings[0]["issues"]
        )

    def test_empty_dag_list(self):
        result = inspect_dags._tool_func(
            dag_files=[], target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_multiple_dags(self):
        dag_files = [
            {
                "filename": "dag1.py",
                "content": "from airflow.operators.python import PythonOperator\n",
            },
            {
                "filename": "dag2.py",
                "content": "from airflow.operators.subdag import SubDagOperator\n",
            },
        ]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 2
        dag1_finding = next(f for f in findings if f["identifier"] == "dag1.py")
        dag2_finding = next(f for f in findings if f["identifier"] == "dag2.py")
        assert dag1_finding["status"] == CompatibilityStatus.COMPATIBLE.value
        assert dag2_finding["status"] != CompatibilityStatus.COMPATIBLE.value

    def test_finding_has_category(self):
        dag_files = [{"filename": "test.py", "content": "x = 1\n"}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["category"] == FindingCategory.DAG.value

    def test_finding_has_identifier(self):
        dag_files = [{"filename": "my_dag.py", "content": "x = 1\n"}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["identifier"] == "my_dag.py"

    def test_no_imports_compatible(self):
        """A file with no imports should be compatible."""
        source = "x = 1\nprint('hello')\n"
        dag_files = [{"filename": "no_imports.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_effort_level_for_incompatible(self):
        """Unsupported operators should result in HIGH effort."""
        source = "from airflow.providers.google.cloud.operators.bigquery import BigQueryOperator\n"
        dag_files = [{"filename": "effort.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "high"

    def test_effort_level_for_subdag(self):
        """SubDAG usage should result in MEDIUM effort."""
        source = "task = SubDagOperator(task_id='sub', subdag=None)\n"
        dag_files = [{"filename": "subdag_effort.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "medium"

    def test_effort_level_for_filesystem(self):
        """Local filesystem path usage should result in LOW effort."""
        source = 'path = "/tmp/data.csv"\n'
        dag_files = [{"filename": "fs_effort.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "low"

    def test_compatible_dag_no_effort(self):
        """Compatible DAGs should have no effort level."""
        source = "from airflow.operators.python import PythonOperator\n"
        dag_files = [{"filename": "no_effort.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] is None
