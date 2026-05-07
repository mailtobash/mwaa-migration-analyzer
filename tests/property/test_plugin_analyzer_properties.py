"""Property-based tests for the Plugin Analyzer tool.

Tests Properties 9, 10, and 4 as they relate to the Plugin Analyzer:
- Property 9: Plugin system resource access detection
- Property 10: Plugin unavailable import detection
- Property 4: Compatibility finding structural invariant (Plugin Analyzer)
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.plugin_analyzer import (
    analyze_plugins,
    detect_local_file_io,
    detect_os_system_calls,
    detect_socket_usage,
    detect_subprocess_calls,
    detect_unavailable_imports,
    extract_imports,
)
from data_loader import load_manifest


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating subprocess call patterns
_subprocess_pattern = st.sampled_from([
    "import subprocess\nsubprocess.run(['ls', '-la'])\n",
    "import subprocess\nresult = subprocess.Popen(['echo', 'hello'])\n",
    "import subprocess\nsubprocess.call(['cat', '/etc/hosts'])\n",
])

# Strategy for generating os.system call patterns
_os_system_pattern = st.sampled_from([
    "import os\nos.system('ls -la')\n",
    "import os\nresult = os.system('echo hello')\n",
])

# Strategy for generating file I/O patterns outside DAGs folder
_file_io_outside_dags = st.sampled_from([
    "f = open('/tmp/data.csv', 'r')\n",
    "f = open('/etc/config.txt', 'w')\n",
    "f = open('/home/user/output.json', 'r')\n",
    "f = open('/var/log/app.log', 'a')\n",
])

# Strategy for generating socket usage patterns
_socket_pattern = st.sampled_from([
    "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n",
    "import socket\nconn = socket.create_connection(('example.com', 80))\n",
    "import socket\ninfo = socket.getaddrinfo('example.com', 80)\n",
])

# Combined strategy for any system resource access pattern
_system_resource_pattern = st.one_of(
    _subprocess_pattern,
    _os_system_pattern,
    _file_io_outside_dags,
    _socket_pattern,
)

# Strategy for generating unavailable package import statements
_unavailable_import = st.sampled_from([
    "import pandas\n",
    "import numpy\n",
    "import scipy\n",
    "import tensorflow\n",
    "import torch\n",
    "import sklearn\n",
    "import matplotlib\n",
    "import seaborn\n",
    "from pyspark.sql import SparkSession\n",
    "import dask\n",
])

# Strategy for generating plugin filenames
_plugin_filename = st.from_regex(
    r"[a-z][a-z0-9_]{1,20}\.py", fullmatch=True
)


# ---------------------------------------------------------------------------
# Property 9: Plugin system resource access detection
# ---------------------------------------------------------------------------

class TestProperty9PluginSystemResourceAccessDetection:
    """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

    For any Python source file containing calls to subprocess.run,
    subprocess.Popen, os.system, open() with paths outside the DAGs folder,
    or socket operations, the Plugin_Analyzer SHALL flag the plugin as
    requiring modernization and list the specific system resource access
    patterns found.

    Validates: Requirements 5.3
    """

    @settings(max_examples=100)
    @given(pattern=_subprocess_pattern)
    def test_subprocess_calls_detected(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        issues = detect_subprocess_calls(pattern)
        assert len(issues) > 0, (
            f"subprocess call should be detected in:\n{pattern}"
        )
        assert any("subprocess" in issue for issue in issues), (
            f"Issue should mention 'subprocess', got: {issues}"
        )

    @settings(max_examples=100)
    @given(pattern=_os_system_pattern)
    def test_os_system_calls_detected(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        issues = detect_os_system_calls(pattern)
        assert len(issues) > 0, (
            f"os.system() call should be detected in:\n{pattern}"
        )
        assert any("os.system" in issue for issue in issues), (
            f"Issue should mention 'os.system', got: {issues}"
        )

    @settings(max_examples=100)
    @given(pattern=_file_io_outside_dags)
    def test_file_io_outside_dags_detected(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        issues = detect_local_file_io(pattern)
        assert len(issues) > 0, (
            f"File I/O outside DAGs folder should be detected in:\n{pattern}"
        )
        assert any("file I/O" in issue.lower() or "outside DAGs folder" in issue for issue in issues), (
            f"Issue should mention file I/O outside DAGs folder, got: {issues}"
        )

    @settings(max_examples=100)
    @given(pattern=_socket_pattern)
    def test_socket_usage_detected(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        issues = detect_socket_usage(pattern)
        assert len(issues) > 0, (
            f"Socket usage should be detected in:\n{pattern}"
        )
        assert any("socket" in issue for issue in issues), (
            f"Issue should mention 'socket', got: {issues}"
        )

    @settings(max_examples=100)
    @given(pattern=_system_resource_pattern)
    def test_system_resource_flags_plugin_via_analyze(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        plugin_files = [{"filename": "test_plugin.py", "content": pattern}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["status"] != CompatibilityStatus.COMPATIBLE.value, (
            f"Plugin with system resource access should not be compatible. "
            f"Pattern:\n{pattern}\nFinding: {finding}"
        )
        assert len(finding["issues"]) > 0, (
            f"Plugin with system resource access should have issues listed. "
            f"Pattern:\n{pattern}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_multiple_resource_patterns_all_listed(self, data):
        """Feature: mwaa-analyzer-agent, Property 9: Plugin system resource access detection

        **Validates: Requirements 5.3**
        """
        # Combine two different resource access patterns
        pattern1 = data.draw(_subprocess_pattern)
        pattern2 = data.draw(_socket_pattern)
        combined = pattern1 + pattern2

        plugin_files = [{"filename": "multi_resource.py", "content": combined}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        # Should have issues from both patterns
        assert len(finding["issues"]) >= 2, (
            f"Plugin with multiple resource patterns should have multiple issues. "
            f"Got: {finding['issues']}"
        )


# ---------------------------------------------------------------------------
# Property 10: Plugin unavailable import detection
# ---------------------------------------------------------------------------

class TestProperty10PluginUnavailableImportDetection:
    """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

    For any plugin source file containing import statements for packages not
    available in the MWAA runtime (as defined by the version manifest), the
    Plugin_Analyzer SHALL flag the plugin as requiring modification and list
    all missing imports.

    Validates: Requirements 5.2
    """

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        self.manifest = load_manifest("2.10.3")

    @settings(max_examples=100)
    @given(import_stmt=_unavailable_import)
    def test_unavailable_import_detected(self, import_stmt):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        issues = detect_unavailable_imports(import_stmt, self.manifest)
        assert len(issues) > 0, (
            f"Unavailable import should be detected in:\n{import_stmt}"
        )
        assert any("Unavailable import" in issue for issue in issues), (
            f"Issue should mention 'Unavailable import', got: {issues}"
        )

    @settings(max_examples=100)
    @given(import_stmt=_unavailable_import)
    def test_unavailable_import_flags_plugin_via_analyze(self, import_stmt):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        plugin_files = [{"filename": "test_plugin.py", "content": import_stmt}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value, (
            f"Plugin with unavailable import should require modification. "
            f"Import:\n{import_stmt}\nFinding: {finding}"
        )
        assert len(finding["issues"]) > 0, (
            f"Plugin with unavailable import should have issues listed"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_available_import_not_flagged(self, data):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        # Pick a pre-installed package from the manifest
        assume(len(self.manifest.pre_installed_packages) > 0)
        pkg_name = data.draw(
            st.sampled_from(sorted(self.manifest.pre_installed_packages.keys()))
        )
        # Use the underscore variant for import (e.g., flask_appbuilder)
        import_name = pkg_name.replace("-", "_").lower()
        source = f"import {import_name}\n"

        issues = detect_unavailable_imports(source, self.manifest)
        assert len(issues) == 0, (
            f"Pre-installed package '{pkg_name}' (imported as '{import_name}') "
            f"should not be flagged as unavailable, got: {issues}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_stdlib_import_not_flagged(self, data):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        stdlib_module = data.draw(st.sampled_from([
            "os", "sys", "json", "re", "datetime", "collections",
            "pathlib", "logging", "typing", "functools", "itertools",
            "hashlib", "uuid", "math", "io", "csv", "xml",
        ]))
        source = f"import {stdlib_module}\n"

        issues = detect_unavailable_imports(source, self.manifest)
        assert len(issues) == 0, (
            f"Standard library module '{stdlib_module}' should not be flagged "
            f"as unavailable, got: {issues}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_airflow_import_not_flagged(self, data):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        airflow_import = data.draw(st.sampled_from([
            "from airflow import DAG\n",
            "from airflow.operators.python import PythonOperator\n",
            "from airflow.hooks.base import BaseHook\n",
            "from airflow.plugins_manager import AirflowPlugin\n",
        ]))

        issues = detect_unavailable_imports(airflow_import, self.manifest)
        assert len(issues) == 0, (
            f"Airflow import should not be flagged as unavailable, got: {issues}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_multiple_unavailable_imports_all_listed(self, data):
        """Feature: mwaa-analyzer-agent, Property 10: Plugin unavailable import detection

        **Validates: Requirements 5.2**
        """
        # Pick 2-3 unavailable imports
        num_imports = data.draw(st.integers(min_value=2, max_value=3))
        import_stmts = [data.draw(_unavailable_import) for _ in range(num_imports)]
        source = "".join(import_stmts)

        # Count unique top-level unavailable modules
        imports = extract_imports(source)
        # Filter to only those that are actually unavailable
        unavailable_count = 0
        for imp in imports:
            issues = detect_unavailable_imports(f"import {imp}\n", self.manifest)
            if issues:
                unavailable_count += 1

        all_issues = detect_unavailable_imports(source, self.manifest)
        assert len(all_issues) == unavailable_count, (
            f"Expected {unavailable_count} unavailable import issues, "
            f"got {len(all_issues)}: {all_issues}"
        )


# ---------------------------------------------------------------------------
# Property 4: Compatibility finding structural invariant (Plugin Analyzer)
# ---------------------------------------------------------------------------

class TestProperty4FindingStructuralInvariantPluginAnalyzer:
    """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Plugin Analyzer)

    For any input to analyze_plugins, every produced finding SHALL contain a
    non-empty identifier, a valid CompatibilityStatus enum value, and an
    issues list.

    Validates: Requirements 5.4
    """

    @settings(max_examples=100)
    @given(
        filename=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
        ),
        content=st.text(min_size=0, max_size=200),
    )
    def test_finding_has_required_fields(self, filename, content):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Plugin Analyzer)

        **Validates: Requirements 5.4**
        """
        plugin_files = [{"filename": filename, "content": content}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) >= 1, (
            "analyze_plugins should produce at least one finding"
        )

        valid_statuses = {s.value for s in CompatibilityStatus}

        for finding in findings:
            # Non-empty identifier
            assert "identifier" in finding
            assert isinstance(finding["identifier"], str)
            assert len(finding["identifier"]) > 0, (
                "Finding identifier must be non-empty"
            )

            # Valid status
            assert "status" in finding
            assert finding["status"] in valid_statuses, (
                f"Status '{finding['status']}' is not a valid CompatibilityStatus"
            )

            # Issues list present
            assert "issues" in finding
            assert isinstance(finding["issues"], list), (
                "Issues must be a list"
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_multiple_plugins_all_have_valid_findings(self, data):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Plugin Analyzer)

        **Validates: Requirements 5.4**
        """
        num_plugins = data.draw(st.integers(min_value=1, max_value=5))
        plugin_files = []
        for i in range(num_plugins):
            filename = f"plugin_{i}.py"
            content = data.draw(st.sampled_from([
                "from airflow.plugins_manager import AirflowPlugin\n",
                "import subprocess\nsubprocess.run(['ls'])\n",
                "import pandas\n",
                "import os\n",
                "",  # empty content
                "def helper(): pass\n",
            ]))
            plugin_files.append({"filename": filename, "content": content})

        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]

        # Should have one finding per plugin
        assert len(findings) == num_plugins

        valid_statuses = {s.value for s in CompatibilityStatus}
        for finding in findings:
            assert finding["identifier"]  # non-empty
            assert finding["status"] in valid_statuses
            assert isinstance(finding["issues"], list)

    @settings(max_examples=100)
    @given(
        filename=_plugin_filename,
        content=st.sampled_from([
            "from airflow.plugins_manager import AirflowPlugin\n",
            "import subprocess\nsubprocess.run(['ls'])\n",
            "import pandas\n",
            "",
        ]),
    )
    def test_finding_category_is_plugin(self, filename, content):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Plugin Analyzer)

        **Validates: Requirements 5.4**
        """
        plugin_files = [{"filename": filename, "content": content}]
        result = analyze_plugins._tool_func(
            plugin_files=plugin_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["category"] == FindingCategory.PLUGIN.value, (
            f"Finding category should be 'plugin', got '{finding['category']}'"
        )
