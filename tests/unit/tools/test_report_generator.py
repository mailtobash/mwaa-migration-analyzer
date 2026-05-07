"""Unit tests for the Report Generator tool.

Tests each output format with sample findings and report content
for each recommendation type.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import json

import pytest

from tools.report_generator import (
    generate_report,
    _build_findings_by_category,
    _build_action_items,
    _build_blockers,
    _build_executive_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_metadata():
    """Sample metadata dict for report generation."""
    return {
        "timestamp": "2024-06-15T10:30:00Z",
        "source_type": "filesystem",
        "target_mwaa_version": "2.10.3",
        "tool_version": "0.1.0",
    }


@pytest.fixture
def compatible_findings():
    """Findings where everything is compatible (lift_and_shift)."""
    return [
        {
            "category": "dag",
            "identifier": "etl_pipeline.py",
            "status": "compatible",
            "issues": [],
            "recommendations": [],
            "effort": None,
        },
        {
            "category": "dependency",
            "identifier": "boto3==1.35.36",
            "status": "compatible",
            "issues": [],
            "recommendations": [],
            "effort": None,
        },
        {
            "category": "configuration",
            "identifier": "core.dags_folder",
            "status": "compatible",
            "issues": [],
            "recommendations": [],
            "effort": None,
        },
    ]


@pytest.fixture
def modernize_findings():
    """Findings requiring modernization (lift_and_modernize)."""
    return [
        {
            "category": "dag",
            "identifier": "legacy_dag.py",
            "status": "requires_modification",
            "issues": ["Uses SubDagOperator"],
            "recommendations": ["Migrate to TaskGroups"],
            "effort": "medium",
        },
        {
            "category": "dependency",
            "identifier": "boto3==2.0.0",
            "status": "version_conflict",
            "issues": ["Version conflict with MWAA 1.35.36"],
            "recommendations": ["Update version constraint"],
            "effort": "low",
        },
        {
            "category": "configuration",
            "identifier": "core.sql_alchemy_conn",
            "status": "unsupported",
            "issues": ["Direct DB access not supported"],
            "recommendations": ["Remove this configuration"],
            "effort": "high",
        },
        {
            "category": "plugin",
            "identifier": "custom_plugin.py",
            "status": "compatible",
            "issues": [],
            "recommendations": [],
            "effort": None,
        },
    ]


@pytest.fixture
def not_possible_findings():
    """Findings with incompatible items (not_possible)."""
    return [
        {
            "category": "dependency",
            "identifier": "numpy==1.24.0",
            "status": "incompatible",
            "issues": ["Requires system-level C libraries"],
            "recommendations": ["Use custom container or find alternative"],
            "effort": "high",
        },
        {
            "category": "plugin",
            "identifier": "native_plugin.py",
            "status": "incompatible",
            "issues": ["Uses subprocess.Popen for system calls"],
            "recommendations": ["Rewrite without system calls"],
            "effort": "high",
        },
        {
            "category": "dag",
            "identifier": "simple_dag.py",
            "status": "compatible",
            "issues": [],
            "recommendations": [],
            "effort": None,
        },
    ]


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestBuildFindingsByCategory:
    """Tests for _build_findings_by_category helper."""

    def test_groups_by_category(self, modernize_findings):
        result = _build_findings_by_category(modernize_findings)
        assert "DAGs" in result
        assert "Dependencies" in result
        assert "Configuration" in result
        assert "Plugins" in result
        assert len(result["DAGs"]) == 1
        assert len(result["Dependencies"]) == 1
        assert len(result["Configuration"]) == 1
        assert len(result["Plugins"]) == 1

    def test_empty_findings(self):
        result = _build_findings_by_category([])
        assert "DAGs" in result
        assert "Dependencies" in result
        assert "Configuration" in result
        assert "Plugins" in result
        assert all(len(v) == 0 for v in result.values())


class TestBuildActionItems:
    """Tests for _build_action_items helper."""

    def test_filters_actionable_findings(self, modernize_findings):
        items = _build_action_items(modernize_findings, "lift_and_modernize")
        # 3 actionable: requires_modification, version_conflict, unsupported
        assert len(items) == 3

    def test_sorts_by_effort_for_modernize(self, modernize_findings):
        items = _build_action_items(modernize_findings, "lift_and_modernize")
        efforts = [item.get("effort") for item in items]
        effort_order = {"low": 0, "medium": 1, "high": 2}
        numeric = [effort_order.get(e, 999) for e in efforts]
        assert numeric == sorted(numeric)

    def test_no_action_items_for_compatible(self, compatible_findings):
        items = _build_action_items(compatible_findings, "lift_and_shift")
        assert len(items) == 0


class TestBuildBlockers:
    """Tests for _build_blockers helper."""

    def test_extracts_incompatible_findings(self, not_possible_findings):
        blockers = _build_blockers(not_possible_findings)
        assert len(blockers) == 2
        assert all(b["status"] == "incompatible" for b in blockers)

    def test_no_blockers_for_compatible(self, compatible_findings):
        blockers = _build_blockers(compatible_findings)
        assert len(blockers) == 0


class TestBuildExecutiveSummary:
    """Tests for _build_executive_summary helper."""

    def test_summary_contains_counts(self, modernize_findings):
        summary = _build_executive_summary(
            modernize_findings, "lift_and_modernize"
        )
        assert "4 component(s)" in summary
        assert "1 component(s) are fully compatible" in summary
        assert "Lift and Modernize" in summary

    def test_summary_for_empty_findings(self):
        summary = _build_executive_summary([], "lift_and_shift")
        assert "0 component(s)" in summary
        assert "Lift and Shift" in summary


# ---------------------------------------------------------------------------
# Markdown output format
# ---------------------------------------------------------------------------


class TestMarkdownOutput:
    """Test Markdown report generation."""

    def test_markdown_lift_and_shift(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "# MWAA Migration Assessment Report" in content
        assert "## Executive Summary" in content
        assert "## Migration Recommendation" in content
        assert "Lift and Shift" in content
        assert "## Detailed Findings" in content
        assert "## Action Items" in content
        assert "## Metadata" in content
        assert "2024-06-15T10:30:00Z" in content
        assert "filesystem" in content
        assert "2.10.3" in content
        assert "0.1.0" in content

    def test_markdown_lift_and_modernize(self, modernize_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=modernize_findings,
            recommendation="lift_and_modernize",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "Lift and Modernize" in content
        assert "legacy_dag.py" in content
        assert "Uses SubDagOperator" in content

    def test_markdown_not_possible_has_blockers(
        self, not_possible_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=not_possible_findings,
            recommendation="not_possible",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "Not Possible" in content
        assert "Blockers" in content
        assert "numpy==1.24.0" in content
        assert "native_plugin.py" in content

    def test_markdown_default_format(self, compatible_findings, sample_metadata):
        """Markdown is the default output format."""
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="markdown",
            metadata=sample_metadata,
        )
        assert "# MWAA Migration Assessment Report" in result["report_content"]


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------


class TestJSONOutput:
    """Test JSON report generation."""

    def test_json_is_valid(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        assert isinstance(parsed, dict)

    def test_json_has_required_keys(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        assert "executive_summary" in parsed
        assert "recommendation" in parsed
        assert "findings_by_category" in parsed
        assert "action_items" in parsed
        assert "metadata" in parsed

    def test_json_findings_by_category(self, modernize_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=modernize_findings,
            recommendation="lift_and_modernize",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        categories = parsed["findings_by_category"]
        assert "DAGs" in categories
        assert "Dependencies" in categories
        assert "Configuration" in categories
        assert "Plugins" in categories

    def test_json_not_possible_has_blockers(
        self, not_possible_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=not_possible_findings,
            recommendation="not_possible",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        assert "blockers" in parsed
        assert len(parsed["blockers"]) == 2

    def test_json_metadata_fields(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        meta = parsed["metadata"]
        assert meta["timestamp"] == "2024-06-15T10:30:00Z"
        assert meta["source_type"] == "filesystem"
        assert meta["target_mwaa_version"] == "2.10.3"
        assert meta["tool_version"] == "0.1.0"

    def test_json_action_items_sorted_for_modernize(
        self, modernize_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=modernize_findings,
            recommendation="lift_and_modernize",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        efforts = [item["effort"] for item in parsed["action_items"]]
        effort_order = {"low": 0, "medium": 1, "high": 2}
        numeric = [effort_order.get(e, 999) for e in efforts]
        assert numeric == sorted(numeric)


# ---------------------------------------------------------------------------
# HTML output format
# ---------------------------------------------------------------------------


class TestHTMLOutput:
    """Test HTML report generation."""

    def test_html_has_required_tags(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "<html" in content
        assert "<head>" in content
        assert "<body>" in content
        assert "</html>" in content

    def test_html_has_inline_css(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "<style>" in content
        assert "</style>" in content

    def test_html_is_self_contained(self, compatible_findings, sample_metadata):
        """HTML should not reference external stylesheets or scripts."""
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert 'rel="stylesheet"' not in content
        assert "<script src=" not in content

    def test_html_contains_recommendation(
        self, modernize_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=modernize_findings,
            recommendation="lift_and_modernize",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "Lift and Modernize" in content

    def test_html_not_possible_has_blockers(
        self, not_possible_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=not_possible_findings,
            recommendation="not_possible",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "Blocker" in content or "blocker" in content

    def test_html_contains_metadata(self, compatible_findings, sample_metadata):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "2024-06-15T10:30:00Z" in content
        assert "filesystem" in content
        assert "2.10.3" in content
        assert "0.1.0" in content


# ---------------------------------------------------------------------------
# Empty findings
# ---------------------------------------------------------------------------


class TestEmptyFindings:
    """Test report generation with empty findings."""

    def test_markdown_empty_findings(self, sample_metadata):
        result = generate_report._tool_func(
            findings=[],
            recommendation="lift_and_shift",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "Executive Summary" in content
        assert "No action items required" in content

    def test_json_empty_findings(self, sample_metadata):
        result = generate_report._tool_func(
            findings=[],
            recommendation="lift_and_shift",
            output_format="json",
            metadata=sample_metadata,
        )
        parsed = json.loads(result["report_content"])
        assert parsed["action_items"] == []
        for cat_findings in parsed["findings_by_category"].values():
            assert cat_findings == []

    def test_html_empty_findings(self, sample_metadata):
        result = generate_report._tool_func(
            findings=[],
            recommendation="lift_and_shift",
            output_format="html",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "<html" in content
        assert "No findings in this category" in content


# ---------------------------------------------------------------------------
# Recommendation types
# ---------------------------------------------------------------------------


class TestRecommendationTypes:
    """Test report content varies correctly by recommendation type."""

    def test_lift_and_shift_description(
        self, compatible_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=compatible_findings,
            recommendation="lift_and_shift",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "fully compatible" in content

    def test_lift_and_modernize_description(
        self, modernize_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=modernize_findings,
            recommendation="lift_and_modernize",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "requires some modifications" in content

    def test_not_possible_description(
        self, not_possible_findings, sample_metadata
    ):
        result = generate_report._tool_func(
            findings=not_possible_findings,
            recommendation="not_possible",
            output_format="markdown",
            metadata=sample_metadata,
        )
        content = result["report_content"]
        assert "incompatible components" in content
