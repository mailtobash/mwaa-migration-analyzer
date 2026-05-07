"""Property-based tests for the DAG Inspector tool.

Tests Properties 1-4 as they relate to the DAG Inspector:
- Property 1: DAG import extraction completeness
- Property 2: Unsupported operator flagging
- Property 3: DAG incompatible pattern detection
- Property 4: Compatibility finding structural invariant (DAG Inspector)
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume

from models import (
    CompatibilityStatus,
    FindingCategory,
    MWAAVersionManifest,
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
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating airflow module paths (operators, hooks, sensors)
_airflow_category = st.sampled_from(["operators", "hooks", "sensors"])
_PYTHON_KEYWORDS = frozenset({
    "False", "None", "True", "and", "as", "assert", "async", "await",
    "break", "class", "continue", "def", "del", "elif", "else", "except",
    "finally", "for", "from", "global", "if", "import", "in", "is",
    "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
    "while", "with", "yield",
})
_module_name = st.from_regex(r"[a-z][a-z_]{0,15}", fullmatch=True).filter(
    lambda s: s not in _PYTHON_KEYWORDS
)
_class_name = st.from_regex(r"[A-Z][a-zA-Z]{1,20}", fullmatch=True)


@st.composite
def airflow_import_statement(draw):
    """Generate a random `from airflow.<cat>.<mod> import <Name>` statement."""
    category = draw(_airflow_category)
    module = draw(_module_name)
    cls = draw(_class_name)
    return f"from airflow.{category}.{module} import {cls}"


@st.composite
def airflow_import_fqn(draw):
    """Generate the fully-qualified name that extract_imports should return."""
    category = draw(_airflow_category)
    module = draw(_module_name)
    cls = draw(_class_name)
    stmt = f"from airflow.{category}.{module} import {cls}"
    fqn = f"airflow.{category}.{module}.{cls}"
    return stmt, fqn


# Strategy for random operator names (some will be in manifest, most won't)
_random_operator_name = st.from_regex(
    r"airflow\.(operators|hooks|sensors|providers)\.[a-z_]{1,15}\.[A-Z][a-zA-Z]{1,20}",
    fullmatch=True,
)

# Strategy for generating DAG source with incompatible patterns
_incompatible_patterns = st.sampled_from([
    "from airflow.settings import Session",
    'session.query(DagRun)',
    "from airflow.operators.subdag import SubDagOperator",
    'open("/tmp/data.csv", "r")',
    'path = "/tmp/output.txt"',
    'f = open("/home/user/data.txt", "w")',
])


# ---------------------------------------------------------------------------
# Property 1: DAG import extraction completeness
# ---------------------------------------------------------------------------

class TestProperty1ImportExtractionCompleteness:
    """Feature: mwaa-analyzer-agent, Property 1: DAG import extraction completeness

    For any valid Python source file containing known operator, hook, or sensor
    imports, extract_imports SHALL return a set that includes every import
    present in the source.

    Validates: Requirements 2.1
    """

    @settings(max_examples=100)
    @given(data=st.data())
    def test_all_generated_imports_are_extracted(self, data):
        """Feature: mwaa-analyzer-agent, Property 1: DAG import extraction completeness

        **Validates: Requirements 2.1**
        """
        # Generate between 1 and 5 import statements
        num_imports = data.draw(st.integers(min_value=1, max_value=5))
        stmts_and_fqns = [data.draw(airflow_import_fqn()) for _ in range(num_imports)]

        statements = [s for s, _ in stmts_and_fqns]
        expected_fqns = {f for _, f in stmts_and_fqns}

        source = "\n".join(statements) + "\n"
        result = extract_imports(source)

        # Every expected FQN must be in the result
        for fqn in expected_fqns:
            assert fqn in result, (
                f"Expected import '{fqn}' not found in extracted imports. "
                f"Source:\n{source}\nExtracted: {result}"
            )

    @settings(max_examples=100)
    @given(
        category=_airflow_category,
        module=_module_name,
        cls=_class_name,
    )
    def test_single_import_always_extracted(self, category, module, cls):
        """Feature: mwaa-analyzer-agent, Property 1: DAG import extraction completeness

        **Validates: Requirements 2.1**
        """
        source = f"from airflow.{category}.{module} import {cls}\n"
        expected = f"airflow.{category}.{module}.{cls}"
        result = extract_imports(source)
        assert expected in result


# ---------------------------------------------------------------------------
# Property 2: Unsupported operator flagging
# ---------------------------------------------------------------------------

class TestProperty2UnsupportedOperatorFlagging:
    """Feature: mwaa-analyzer-agent, Property 2: Unsupported operator flagging

    For any operator name and a given MWAA version manifest, if the operator
    is not in the manifest's supported operators set,
    detect_unsupported_operators SHALL produce a finding with a non-compatible
    status; if in the supported set, no issue.

    Validates: Requirements 2.2
    """

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        self.manifest = load_manifest("2.10.3")

    @settings(max_examples=100)
    @given(operator_name=_random_operator_name)
    def test_unsupported_operator_flagged(self, operator_name):
        """Feature: mwaa-analyzer-agent, Property 2: Unsupported operator flagging

        **Validates: Requirements 2.2**
        """
        imports = {operator_name}
        issues = detect_unsupported_operators(imports, self.manifest)

        if operator_name in self.manifest.supported_operators:
            # Supported operator should produce no issues
            assert len(issues) == 0, (
                f"Supported operator '{operator_name}' should not produce issues, "
                f"but got: {issues}"
            )
        else:
            # Unsupported operator should produce an issue
            assert len(issues) > 0, (
                f"Unsupported operator '{operator_name}' should produce an issue"
            )
            assert any(operator_name in issue for issue in issues), (
                f"Issue should mention the operator name '{operator_name}'"
            )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_supported_operator_no_issues(self, data):
        """Feature: mwaa-analyzer-agent, Property 2: Unsupported operator flagging

        **Validates: Requirements 2.2**
        """
        assume(len(self.manifest.supported_operators) > 0)
        operator = data.draw(
            st.sampled_from(sorted(self.manifest.supported_operators))
        )
        imports = {operator}
        issues = detect_unsupported_operators(imports, self.manifest)
        assert len(issues) == 0, (
            f"Supported operator '{operator}' should not produce issues"
        )


# ---------------------------------------------------------------------------
# Property 3: DAG incompatible pattern detection
# ---------------------------------------------------------------------------

class TestProperty3IncompatiblePatternDetection:
    """Feature: mwaa-analyzer-agent, Property 3: DAG incompatible pattern detection

    For any DAG source containing known incompatible patterns (SQLAlchemy,
    SubDagOperator, local filesystem paths), the DAG_Inspector SHALL flag
    the DAG as requiring modernization.

    Validates: Requirements 2.3, 2.4, 2.5
    """

    @settings(max_examples=100)
    @given(data=st.data())
    def test_sqlalchemy_session_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 3: DAG incompatible pattern detection

        **Validates: Requirements 2.3, 2.4, 2.5**
        """
        # Generate a source with SQLAlchemy session usage
        pattern = data.draw(st.sampled_from([
            "from airflow.settings import Session\nsession = Session()\n",
            "from airflow import settings\ns = settings.Session()\n",
            "result = session.query(DagRun).all()\n",
        ]))
        source = f"import airflow\n{pattern}"
        issues = detect_metadata_db_access(source)
        assert len(issues) > 0, (
            f"SQLAlchemy pattern should be detected in:\n{source}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_subdag_usage_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 3: DAG incompatible pattern detection

        **Validates: Requirements 2.3, 2.4, 2.5**
        """
        # Generate source with SubDagOperator
        prefix = data.draw(st.sampled_from([
            "from airflow.operators.subdag import SubDagOperator\n",
            "task = SubDagOperator(task_id='sub', subdag=sub_dag)\n",
        ]))
        source = f"import airflow\n{prefix}"
        issues = detect_subdag_usage(source)
        assert len(issues) > 0, (
            f"SubDagOperator usage should be detected in:\n{source}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_local_filesystem_paths_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 3: DAG incompatible pattern detection

        **Validates: Requirements 2.3, 2.4, 2.5**
        """
        pattern = data.draw(st.sampled_from([
            'path = "/tmp/data.csv"\n',
            'f = open("/tmp/output.txt", "w")\n',
            'data_path = "/home/user/data.txt"\n',
            'log_path = "/var/log/airflow.log"\n',
        ]))
        source = f"import os\n{pattern}"
        issues = detect_local_filesystem_paths(source)
        assert len(issues) > 0, (
            f"Local filesystem path should be detected in:\n{source}"
        )

    @settings(max_examples=100)
    @given(pattern=_incompatible_patterns)
    def test_injected_pattern_flags_dag_via_inspect(self, pattern):
        """Feature: mwaa-analyzer-agent, Property 3: DAG incompatible pattern detection

        **Validates: Requirements 2.3, 2.4, 2.5**
        """
        # Build a minimal valid DAG source with the injected pattern
        source = f"import airflow\n{pattern}\n"
        dag_files = [{"filename": "test_dag.py", "content": source}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        # The DAG should not be marked as compatible
        assert finding["status"] != CompatibilityStatus.COMPATIBLE.value, (
            f"DAG with pattern '{pattern}' should not be compatible. "
            f"Finding: {finding}"
        )


# ---------------------------------------------------------------------------
# Property 4: Compatibility finding structural invariant (DAG Inspector)
# ---------------------------------------------------------------------------

class TestProperty4FindingStructuralInvariant:
    """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (DAG Inspector)

    For any input to inspect_dags, every produced finding SHALL contain a
    non-empty identifier, a valid status, and an issues list.

    Validates: Requirements 2.6
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
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (DAG Inspector)

        **Validates: Requirements 2.6**
        """
        dag_files = [{"filename": filename, "content": content}]
        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]
        assert len(findings) >= 1, "inspect_dags should produce at least one finding"

        for finding in findings:
            # Non-empty identifier
            assert "identifier" in finding
            assert isinstance(finding["identifier"], str)
            assert len(finding["identifier"]) > 0, (
                "Finding identifier must be non-empty"
            )

            # Valid status
            assert "status" in finding
            valid_statuses = {s.value for s in CompatibilityStatus}
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
    def test_multiple_dags_all_have_valid_findings(self, data):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (DAG Inspector)

        **Validates: Requirements 2.6**
        """
        num_dags = data.draw(st.integers(min_value=1, max_value=5))
        dag_files = []
        for i in range(num_dags):
            filename = f"dag_{i}.py"
            # Mix of valid and invalid content
            content = data.draw(st.sampled_from([
                "from airflow.operators.python import PythonOperator\n",
                "from airflow.operators.subdag import SubDagOperator\n",
                'path = "/tmp/data.csv"\n',
                "import os\n",
                "",  # empty content
                "def hello(): pass\n",
            ]))
            dag_files.append({"filename": filename, "content": content})

        result = inspect_dags._tool_func(
            dag_files=dag_files, target_mwaa_version="2.10.3"
        )
        findings = result["findings"]

        # Should have one finding per DAG
        assert len(findings) == num_dags

        valid_statuses = {s.value for s in CompatibilityStatus}
        for finding in findings:
            assert finding["identifier"]  # non-empty
            assert finding["status"] in valid_statuses
            assert isinstance(finding["issues"], list)
