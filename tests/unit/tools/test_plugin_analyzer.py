"""Unit tests for the Plugin Analyzer tool.

Tests Plugin Analyzer with sample plugin files, edge cases, and individual
helper functions.

Requirements: 5.1, 5.2, 5.3, 5.4
"""

from __future__ import annotations

import pytest

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.plugin_analyzer import (
    analyze_plugins,
    check_plugin_structure,
    detect_local_file_io,
    detect_os_system_calls,
    detect_socket_usage,
    detect_subprocess_calls,
    detect_unavailable_imports,
    extract_imports,
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

    def test_simple_import(self):
        source = "import pandas\n"
        result = extract_imports(source)
        assert "pandas" in result

    def test_from_import(self):
        source = "from airflow.operators.python import PythonOperator\n"
        result = extract_imports(source)
        assert "airflow" in result

    def test_multiple_imports(self):
        source = "import os\nimport json\nimport pandas\n"
        result = extract_imports(source)
        assert "os" in result
        assert "json" in result
        assert "pandas" in result

    def test_dotted_import(self):
        source = "import airflow.operators.python\n"
        result = extract_imports(source)
        assert "airflow" in result

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


# ---------------------------------------------------------------------------
# Helper: detect_subprocess_calls
# ---------------------------------------------------------------------------


class TestDetectSubprocessCalls:
    """Tests for the detect_subprocess_calls helper function."""

    def test_subprocess_run_detected(self):
        source = "import subprocess\nsubprocess.run(['ls', '-la'])\n"
        issues = detect_subprocess_calls(source)
        assert len(issues) >= 1
        assert any("subprocess.run" in i for i in issues)

    def test_subprocess_popen_detected(self):
        source = "import subprocess\nresult = subprocess.Popen(['echo', 'hello'])\n"
        issues = detect_subprocess_calls(source)
        assert len(issues) >= 1
        assert any("subprocess.Popen" in i for i in issues)

    def test_subprocess_call_detected(self):
        source = "import subprocess\nsubprocess.call(['cat', '/etc/hosts'])\n"
        issues = detect_subprocess_calls(source)
        assert len(issues) >= 1
        assert any("subprocess.call" in i for i in issues)

    def test_no_subprocess_no_issues(self):
        source = "import os\nprint('hello')\n"
        issues = detect_subprocess_calls(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_subprocess_calls("")
        assert len(issues) == 0

    def test_multiple_subprocess_calls(self):
        source = (
            "import subprocess\n"
            "subprocess.run(['ls'])\n"
            "subprocess.Popen(['echo', 'hi'])\n"
            "subprocess.call(['cat', 'file.txt'])\n"
        )
        issues = detect_subprocess_calls(source)
        assert len(issues) == 3


# ---------------------------------------------------------------------------
# Helper: detect_os_system_calls
# ---------------------------------------------------------------------------


class TestDetectOsSystemCalls:
    """Tests for the detect_os_system_calls helper function."""

    def test_os_system_detected(self):
        source = "import os\nos.system('ls -la')\n"
        issues = detect_os_system_calls(source)
        assert len(issues) >= 1
        assert any("os.system" in i for i in issues)

    def test_no_os_system_no_issues(self):
        source = "import os\nos.path.exists('/tmp')\n"
        issues = detect_os_system_calls(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_os_system_calls("")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_local_file_io
# ---------------------------------------------------------------------------


class TestDetectLocalFileIo:
    """Tests for the detect_local_file_io helper function."""

    def test_open_tmp_detected(self):
        source = "f = open('/tmp/data.csv', 'r')\n"
        issues = detect_local_file_io(source)
        assert len(issues) >= 1
        assert any("/tmp/" in i for i in issues)

    def test_open_etc_detected(self):
        source = "f = open('/etc/config.txt', 'w')\n"
        issues = detect_local_file_io(source)
        assert len(issues) >= 1

    def test_open_home_detected(self):
        source = "f = open('/home/user/output.json', 'r')\n"
        issues = detect_local_file_io(source)
        assert len(issues) >= 1

    def test_open_dags_folder_not_flagged(self):
        source = "f = open('/usr/local/airflow/dags/config.json', 'r')\n"
        issues = detect_local_file_io(source)
        assert len(issues) == 0

    def test_no_open_no_issues(self):
        source = "x = 1\nprint('hello')\n"
        issues = detect_local_file_io(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_local_file_io("")
        assert len(issues) == 0

    def test_relative_path_not_flagged(self):
        """Relative paths (not starting with /) should not be flagged."""
        source = "f = open('data.csv', 'r')\n"
        issues = detect_local_file_io(source)
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_socket_usage
# ---------------------------------------------------------------------------


class TestDetectSocketUsage:
    """Tests for the detect_socket_usage helper function."""

    def test_socket_socket_detected(self):
        source = "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        issues = detect_socket_usage(source)
        assert len(issues) >= 1
        assert any("socket" in i for i in issues)

    def test_socket_create_connection_detected(self):
        source = "import socket\nconn = socket.create_connection(('example.com', 80))\n"
        issues = detect_socket_usage(source)
        assert len(issues) >= 1

    def test_socket_getaddrinfo_detected(self):
        source = "import socket\ninfo = socket.getaddrinfo('example.com', 80)\n"
        issues = detect_socket_usage(source)
        assert len(issues) >= 1

    def test_no_socket_no_issues(self):
        source = "import os\nprint('hello')\n"
        issues = detect_socket_usage(source)
        assert len(issues) == 0

    def test_empty_source_no_issues(self):
        issues = detect_socket_usage("")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Helper: detect_unavailable_imports
# ---------------------------------------------------------------------------


class TestDetectUnavailableImports:
    """Tests for the detect_unavailable_imports helper function."""

    def test_unavailable_package_flagged(self, manifest):
        source = "import pandas\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) >= 1
        assert any("pandas" in i for i in issues)

    def test_available_package_not_flagged(self, manifest):
        source = "import boto3\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 0

    def test_stdlib_not_flagged(self, manifest):
        source = "import os\nimport json\nimport re\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 0

    def test_airflow_not_flagged(self, manifest):
        source = "from airflow.operators.python import PythonOperator\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 0

    def test_multiple_unavailable_flagged(self, manifest):
        source = "import pandas\nimport numpy\nimport scipy\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 3

    def test_mixed_available_and_unavailable(self, manifest):
        source = "import os\nimport boto3\nimport pandas\n"
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 1
        assert any("pandas" in i for i in issues)

    def test_empty_source_no_issues(self, manifest):
        issues = detect_unavailable_imports("", manifest)
        assert len(issues) == 0

    def test_hyphenated_package_available(self, manifest):
        """Packages with hyphens in names should be matched via normalization."""
        source = "import psycopg2_binary\n"
        # psycopg2-binary is in the manifest; import as psycopg2_binary
        # The top-level import name is psycopg2_binary
        issues = detect_unavailable_imports(source, manifest)
        assert len(issues) == 0, (
            f"psycopg2_binary should be recognized as available (psycopg2-binary), "
            f"got: {issues}"
        )


# ---------------------------------------------------------------------------
# Helper: check_plugin_structure
# ---------------------------------------------------------------------------


class TestCheckPluginStructure:
    """Tests for the check_plugin_structure helper function."""

    def test_valid_python_no_issues(self):
        source = "def hello(): pass\n"
        issues = check_plugin_structure(source, "plugin.py")
        assert len(issues) == 0

    def test_syntax_error_flagged(self):
        source = "def broken(\n  invalid syntax\n"
        issues = check_plugin_structure(source, "broken_plugin.py")
        assert len(issues) >= 1
        assert any("syntax" in i.lower() for i in issues)

    def test_empty_source_no_issues(self):
        issues = check_plugin_structure("", "empty.py")
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# analyze_plugins tool: compatible plugins
# ---------------------------------------------------------------------------


class TestAnalyzePluginsCompatible:
    """Test analyze_plugins with plugins that should be fully compatible."""

    def test_clean_plugin(self):
        source = (
            "from airflow.plugins_manager import AirflowPlugin\n"
            "from airflow.operators.python import PythonOperator\n"
            "\n"
            "class MyPlugin(AirflowPlugin):\n"
            "    name = 'my_plugin'\n"
        )
        plugin_files = [{"filename": "my_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["issues"] == []

    def test_plugin_with_stdlib_imports(self):
        source = (
            "import os\n"
            "import json\n"
            "import logging\n"
            "\n"
            "logger = logging.getLogger(__name__)\n"
        )
        plugin_files = [{"filename": "stdlib_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_empty_plugin(self):
        plugin_files = [{"filename": "empty.py", "content": ""}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["identifier"] == "empty.py"

    def test_plugin_with_available_packages(self):
        source = (
            "import boto3\n"
            "import requests\n"
            "from airflow.hooks.base import BaseHook\n"
        )
        plugin_files = [{"filename": "aws_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value


# ---------------------------------------------------------------------------
# analyze_plugins tool: requires_modification plugins
# ---------------------------------------------------------------------------


class TestAnalyzePluginsRequiresModification:
    """Test analyze_plugins with plugins that require modification."""

    def test_subprocess_run_flagged(self):
        source = (
            "import subprocess\n"
            "\n"
            "def run_command(cmd):\n"
            "    return subprocess.run(cmd, capture_output=True)\n"
        )
        plugin_files = [{"filename": "subprocess_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("subprocess.run" in issue for issue in findings[0]["issues"])

    def test_subprocess_popen_flagged(self):
        source = (
            "import subprocess\n"
            "\n"
            "proc = subprocess.Popen(['echo', 'hello'], stdout=subprocess.PIPE)\n"
        )
        plugin_files = [{"filename": "popen_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("subprocess.Popen" in issue for issue in findings[0]["issues"])

    def test_socket_usage_flagged(self):
        source = (
            "import socket\n"
            "\n"
            "def check_port(host, port):\n"
            "    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
            "    s.connect((host, port))\n"
            "    s.close()\n"
        )
        plugin_files = [{"filename": "socket_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("socket" in issue for issue in findings[0]["issues"])

    def test_os_system_flagged(self):
        source = (
            "import os\n"
            "\n"
            "def cleanup():\n"
            "    os.system('rm -rf /tmp/cache')\n"
        )
        plugin_files = [{"filename": "os_system_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("os.system" in issue for issue in findings[0]["issues"])

    def test_missing_imports_flagged(self):
        source = (
            "import pandas as pd\n"
            "import numpy as np\n"
            "\n"
            "def process_data():\n"
            "    df = pd.DataFrame({'a': [1, 2, 3]})\n"
            "    return np.mean(df['a'])\n"
        )
        plugin_files = [{"filename": "data_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("pandas" in issue or "numpy" in issue for issue in findings[0]["issues"])

    def test_file_io_outside_dags_flagged(self):
        source = (
            "def read_config():\n"
            "    f = open('/etc/airflow/config.json', 'r')\n"
            "    return f.read()\n"
        )
        plugin_files = [{"filename": "fileio_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("file I/O" in issue.lower() or "outside DAGs folder" in issue for issue in findings[0]["issues"])

    def test_recommendations_present_for_issues(self):
        """When issues are found, recommendations should be provided."""
        source = "import subprocess\nsubprocess.run(['ls'])\n"
        plugin_files = [{"filename": "rec_plugin.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0

    def test_syntax_error_flagged(self):
        source = "def broken(\n  invalid syntax\n"
        plugin_files = [{"filename": "broken.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("syntax" in issue.lower() for issue in findings[0]["issues"])


# ---------------------------------------------------------------------------
# analyze_plugins tool: edge cases
# ---------------------------------------------------------------------------


class TestAnalyzePluginsEdgeCases:
    """Test analyze_plugins with edge cases."""

    def test_empty_plugin_list(self):
        result = analyze_plugins._tool_func(
            plugin_files=[], target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_multiple_plugins(self):
        plugin_files = [
            {
                "filename": "clean_plugin.py",
                "content": "from airflow.plugins_manager import AirflowPlugin\n",
            },
            {
                "filename": "subprocess_plugin.py",
                "content": "import subprocess\nsubprocess.run(['ls'])\n",
            },
        ]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 2
        clean_finding = next(f for f in findings if f["identifier"] == "clean_plugin.py")
        sub_finding = next(f for f in findings if f["identifier"] == "subprocess_plugin.py")
        assert clean_finding["status"] == CompatibilityStatus.COMPATIBLE.value
        assert sub_finding["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value

    def test_finding_has_category(self):
        plugin_files = [{"filename": "test.py", "content": "x = 1\n"}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["category"] == FindingCategory.PLUGIN.value

    def test_finding_has_identifier(self):
        plugin_files = [{"filename": "my_plugin.py", "content": "x = 1\n"}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["identifier"] == "my_plugin.py"

    def test_effort_level_for_system_resource(self):
        """System resource access should result in HIGH effort."""
        source = "import subprocess\nsubprocess.run(['ls'])\n"
        plugin_files = [{"filename": "effort.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "high"

    def test_effort_level_for_missing_imports(self):
        """Missing imports should result in MEDIUM effort."""
        source = "import pandas\n"
        plugin_files = [{"filename": "import_effort.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "medium"

    def test_effort_level_for_syntax_error(self):
        """Syntax errors should result in LOW effort."""
        source = "def broken(\n"
        plugin_files = [{"filename": "syntax_effort.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "low"

    def test_compatible_plugin_no_effort(self):
        """Compatible plugins should have no effort level."""
        source = "from airflow.plugins_manager import AirflowPlugin\n"
        plugin_files = [{"filename": "no_effort.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert findings[0]["effort"] is None

    def test_file_io_inside_dags_folder_not_flagged(self):
        """File I/O within the MWAA DAGs folder should not be flagged."""
        source = "f = open('/usr/local/airflow/dags/config.json', 'r')\n"
        plugin_files = [{"filename": "dags_io.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        # Should not have file I/O issues
        assert not any("file I/O" in issue.lower() for issue in findings[0]["issues"])

    def test_combined_issues(self):
        """Plugin with both subprocess and missing imports should list all issues."""
        source = (
            "import subprocess\n"
            "import pandas\n"
            "\n"
            "subprocess.run(['ls'])\n"
        )
        plugin_files = [{"filename": "combined.py", "content": source}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        # Should have both subprocess and import issues
        has_subprocess = any("subprocess" in i for i in findings[0]["issues"])
        has_import = any("pandas" in i for i in findings[0]["issues"])
        assert has_subprocess and has_import, (
            f"Expected both subprocess and import issues, got: {findings[0]['issues']}"
        )
