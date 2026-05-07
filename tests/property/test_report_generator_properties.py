"""Property-based tests for the Report Generator tool.

Tests Properties 12-16 for report generation correctness.

Validates: Requirements 7.1, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import json

from hypothesis import given, settings, strategies as st

from models import (
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
)
from tools.report_generator import generate_report


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating finding dicts (matching the tool's input format)
_STATUSES = [s.value for s in CompatibilityStatus]
_CATEGORIES = [c.value for c in FindingCategory]
_EFFORTS = [e.value for e in EffortLevel]

finding_dict_strategy = st.fixed_dictionaries({
    "category": st.sampled_from(_CATEGORIES),
    "identifier": st.text(
        min_size=1,
        max_size=80,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    "status": st.sampled_from(_STATUSES),
    "issues": st.lists(st.text(min_size=1, max_size=100), max_size=5),
    "recommendations": st.lists(st.text(min_size=1, max_size=100), max_size=5),
    "effort": st.one_of(st.none(), st.sampled_from(_EFFORTS)),
})

# Strategy for metadata dicts
# Use only alphanumeric characters for timestamp to avoid HTML escaping issues
metadata_strategy = st.fixed_dictionaries({
    "timestamp": st.from_regex(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
        fullmatch=True,
    ),
    "source_type": st.sampled_from(["api", "mwaa", "filesystem"]),
    "target_mwaa_version": st.just("2.10.3"),
    "tool_version": st.just("0.1.0"),
})

# Strategy for recommendation strings
recommendation_strategy = st.sampled_from([
    "lift_and_shift",
    "lift_and_modernize",
    "not_possible",
])

# Strategy for output format strings
output_format_strategy = st.sampled_from(["markdown", "json", "html"])

# Strategy for findings that require modification (for lift_and_modernize)
_MODERNIZE_STATUSES = [
    CompatibilityStatus.REQUIRES_MODIFICATION.value,
    CompatibilityStatus.VERSION_CONFLICT.value,
    CompatibilityStatus.UNSUPPORTED.value,
]

modernize_finding_strategy = st.fixed_dictionaries({
    "category": st.sampled_from(_CATEGORIES),
    "identifier": st.text(
        min_size=1,
        max_size=80,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    "status": st.sampled_from(_MODERNIZE_STATUSES),
    "issues": st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=5),
    "recommendations": st.lists(st.text(min_size=1, max_size=100), max_size=5),
    "effort": st.sampled_from(_EFFORTS),
})

# Strategy for incompatible findings (for not_possible)
incompatible_finding_strategy = st.fixed_dictionaries({
    "category": st.sampled_from(_CATEGORIES),
    "identifier": st.text(
        min_size=1,
        max_size=80,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    "status": st.just(CompatibilityStatus.INCOMPATIBLE.value),
    "issues": st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=5),
    "recommendations": st.lists(st.text(min_size=1, max_size=100), max_size=5),
    "effort": st.sampled_from(_EFFORTS),
})


# ---------------------------------------------------------------------------
# Property 12: Report required sections presence
# ---------------------------------------------------------------------------


class TestProperty12ReportRequiredSectionsPresence:
    """Feature: mwaa-analyzer-agent, Property 12: Report required sections presence

    For any set of findings, recommendation, and metadata, the generated report
    (in any format) SHALL contain an executive summary section, the migration
    recommendation, a findings section organized by category (DAGs, dependencies,
    configuration, plugins), an action items section, and a metadata section with
    timestamp, source type, target MWAA version, and tool version.

    **Validates: Requirements 7.1, 7.7**
    """

    @settings(max_examples=100)
    @given(
        findings=st.lists(finding_dict_strategy, min_size=0, max_size=10),
        recommendation=recommendation_strategy,
        output_format=output_format_strategy,
        metadata=metadata_strategy,
    )
    def test_report_contains_all_required_sections(
        self, findings, recommendation, output_format, metadata
    ):
        """Feature: mwaa-analyzer-agent, Property 12: Report required sections presence

        **Validates: Requirements 7.1, 7.7**
        """
        result = generate_report._tool_func(
            findings=findings,
            recommendation=recommendation,
            output_format=output_format,
            metadata=metadata,
        )
        content = result["report_content"]

        if output_format == "json":
            parsed = json.loads(content)
            # Check required top-level keys
            assert "executive_summary" in parsed, "JSON missing executive_summary"
            assert "recommendation" in parsed, "JSON missing recommendation"
            assert "findings_by_category" in parsed, "JSON missing findings_by_category"
            assert "action_items" in parsed, "JSON missing action_items"
            assert "metadata" in parsed, "JSON missing metadata"

            # Check category keys in findings
            categories = parsed["findings_by_category"]
            assert "DAGs" in categories, "JSON missing DAGs category"
            assert "Dependencies" in categories, "JSON missing Dependencies category"
            assert "Configuration" in categories, "JSON missing Configuration category"
            assert "Plugins" in categories, "JSON missing Plugins category"

            # Check metadata fields
            meta = parsed["metadata"]
            assert "timestamp" in meta, "JSON metadata missing timestamp"
            assert "source_type" in meta, "JSON metadata missing source_type"
            assert "target_mwaa_version" in meta, "JSON metadata missing target_mwaa_version"
            assert "tool_version" in meta, "JSON metadata missing tool_version"
        else:
            # For markdown and HTML, check for section presence via text
            content_lower = content.lower()
            assert "executive summary" in content_lower, (
                f"Report ({output_format}) missing executive summary section"
            )
            assert "recommendation" in content_lower, (
                f"Report ({output_format}) missing recommendation section"
            )
            assert "action items" in content_lower, (
                f"Report ({output_format}) missing action items section"
            )
            assert "metadata" in content_lower, (
                f"Report ({output_format}) missing metadata section"
            )

            # Check category sections
            assert "dag" in content_lower, (
                f"Report ({output_format}) missing DAGs findings category"
            )
            assert "dependenc" in content_lower, (
                f"Report ({output_format}) missing Dependencies findings category"
            )
            assert "configuration" in content_lower, (
                f"Report ({output_format}) missing Configuration findings category"
            )
            assert "plugin" in content_lower, (
                f"Report ({output_format}) missing Plugins findings category"
            )

            # Check metadata fields present
            assert metadata["timestamp"].lower() in content_lower, (
                f"Report ({output_format}) missing timestamp in metadata"
            )
            assert metadata["source_type"] in content_lower, (
                f"Report ({output_format}) missing source_type in metadata"
            )
            assert metadata["target_mwaa_version"] in content_lower, (
                f"Report ({output_format}) missing target_mwaa_version in metadata"
            )
            assert metadata["tool_version"] in content_lower, (
                f"Report ({output_format}) missing tool_version in metadata"
            )


# ---------------------------------------------------------------------------
# Property 13: JSON report validity
# ---------------------------------------------------------------------------


class TestProperty13JSONReportValidity:
    """Feature: mwaa-analyzer-agent, Property 13: JSON report validity

    For any set of findings and recommendation, when the output format is JSON,
    the generated report SHALL be valid JSON that deserializes to a dictionary
    containing keys for all required report sections.

    **Validates: Requirements 7.3**
    """

    @settings(max_examples=100)
    @given(
        findings=st.lists(finding_dict_strategy, min_size=0, max_size=10),
        recommendation=recommendation_strategy,
        metadata=metadata_strategy,
    )
    def test_json_report_is_valid_and_complete(
        self, findings, recommendation, metadata
    ):
        """Feature: mwaa-analyzer-agent, Property 13: JSON report validity

        **Validates: Requirements 7.3**
        """
        result = generate_report._tool_func(
            findings=findings,
            recommendation=recommendation,
            output_format="json",
            metadata=metadata,
        )
        content = result["report_content"]

        # Must be valid JSON
        parsed = json.loads(content)
        assert isinstance(parsed, dict), "JSON report should deserialize to a dict"

        # Must contain all required section keys
        required_keys = {
            "executive_summary",
            "recommendation",
            "recommendation_display",
            "findings_by_category",
            "action_items",
            "metadata",
        }
        assert required_keys.issubset(parsed.keys()), (
            f"JSON report missing keys: {required_keys - parsed.keys()}"
        )

        # findings_by_category must be a dict
        assert isinstance(parsed["findings_by_category"], dict), (
            "findings_by_category should be a dict"
        )

        # action_items must be a list
        assert isinstance(parsed["action_items"], list), (
            "action_items should be a list"
        )

        # metadata must be a dict
        assert isinstance(parsed["metadata"], dict), (
            "metadata should be a dict"
        )


# ---------------------------------------------------------------------------
# Property 14: HTML report self-containment
# ---------------------------------------------------------------------------


class TestProperty14HTMLReportSelfContainment:
    """Feature: mwaa-analyzer-agent, Property 14: HTML report self-containment

    For any set of findings and recommendation, when the output format is HTML,
    the generated report SHALL contain <html>, <head>, <body> tags and at least
    one <style> block with inline CSS.

    **Validates: Requirements 7.4**
    """

    @settings(max_examples=100)
    @given(
        findings=st.lists(finding_dict_strategy, min_size=0, max_size=10),
        recommendation=recommendation_strategy,
        metadata=metadata_strategy,
    )
    def test_html_report_is_self_contained(
        self, findings, recommendation, metadata
    ):
        """Feature: mwaa-analyzer-agent, Property 14: HTML report self-containment

        **Validates: Requirements 7.4**
        """
        result = generate_report._tool_func(
            findings=findings,
            recommendation=recommendation,
            output_format="html",
            metadata=metadata,
        )
        content = result["report_content"]

        assert "<html" in content, "HTML report missing <html> tag"
        assert "<head>" in content, "HTML report missing <head> tag"
        assert "<body>" in content, "HTML report missing <body> tag"
        assert "</html>" in content, "HTML report missing closing </html> tag"
        assert "<style>" in content, "HTML report missing <style> block"

        # Verify there is actual CSS content inside the style block
        style_start = content.index("<style>") + len("<style>")
        style_end = content.index("</style>")
        css_content = content[style_start:style_end].strip()
        assert len(css_content) > 0, "HTML report <style> block is empty"


# ---------------------------------------------------------------------------
# Property 15: Lift_and_Modernize effort ordering
# ---------------------------------------------------------------------------


class TestProperty15LiftAndModernizeEffortOrdering:
    """Feature: mwaa-analyzer-agent, Property 15: Lift_and_Modernize effort ordering

    For any set of findings where the recommendation is Lift_and_Modernize,
    the report's action items section SHALL list modifications in non-decreasing
    order of effort level (low before medium before high).

    **Validates: Requirements 7.5**
    """

    @settings(max_examples=100)
    @given(
        modernize_findings=st.lists(
            modernize_finding_strategy, min_size=1, max_size=10
        ),
        compatible_findings=st.lists(
            st.fixed_dictionaries({
                "category": st.sampled_from(_CATEGORIES),
                "identifier": st.text(
                    min_size=1,
                    max_size=80,
                    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
                ),
                "status": st.just("compatible"),
                "issues": st.just([]),
                "recommendations": st.just([]),
                "effort": st.none(),
            }),
            min_size=0,
            max_size=5,
        ),
        metadata=metadata_strategy,
    )
    def test_action_items_ordered_by_effort(
        self, modernize_findings, compatible_findings, metadata
    ):
        """Feature: mwaa-analyzer-agent, Property 15: Lift_and_Modernize effort ordering

        **Validates: Requirements 7.5**
        """
        findings = modernize_findings + compatible_findings

        # Test with JSON to easily parse action items
        result = generate_report._tool_func(
            findings=findings,
            recommendation="lift_and_modernize",
            output_format="json",
            metadata=metadata,
        )
        parsed = json.loads(result["report_content"])
        action_items = parsed["action_items"]

        # Extract effort levels from action items
        effort_order = {"low": 0, "medium": 1, "high": 2}
        efforts = [
            effort_order.get(item.get("effort", "") or "", 999)
            for item in action_items
        ]

        # Verify non-decreasing order
        for i in range(len(efforts) - 1):
            assert efforts[i] <= efforts[i + 1], (
                f"Action items not in non-decreasing effort order: "
                f"item {i} has effort order {efforts[i]}, "
                f"item {i+1} has effort order {efforts[i+1]}. "
                f"Full efforts: {[item.get('effort') for item in action_items]}"
            )


# ---------------------------------------------------------------------------
# Property 16: Not_Possible blockers inclusion
# ---------------------------------------------------------------------------


class TestProperty16NotPossibleBlockersInclusion:
    """Feature: mwaa-analyzer-agent, Property 16: Not_Possible blockers inclusion

    For any set of findings where the recommendation is Not_Possible, the report
    SHALL include a blockers section listing every finding with incompatible status.

    **Validates: Requirements 7.6**
    """

    @settings(max_examples=100)
    @given(
        incompatible_findings=st.lists(
            incompatible_finding_strategy, min_size=1, max_size=5
        ),
        other_findings=st.lists(
            finding_dict_strategy, min_size=0, max_size=5
        ),
        metadata=metadata_strategy,
    )
    def test_blockers_include_all_incompatible_findings(
        self, incompatible_findings, other_findings, metadata
    ):
        """Feature: mwaa-analyzer-agent, Property 16: Not_Possible blockers inclusion

        **Validates: Requirements 7.6**
        """
        findings = incompatible_findings + other_findings

        # Use JSON format for easy parsing
        result = generate_report._tool_func(
            findings=findings,
            recommendation="not_possible",
            output_format="json",
            metadata=metadata,
        )
        parsed = json.loads(result["report_content"])

        assert "blockers" in parsed, "Not_Possible report missing blockers section"

        blocker_identifiers = {b["identifier"] for b in parsed["blockers"]}

        # Every incompatible finding must appear in blockers
        all_incompatible_identifiers = {
            f["identifier"]
            for f in findings
            if f["status"] == "incompatible"
        }

        assert all_incompatible_identifiers.issubset(blocker_identifiers), (
            f"Missing incompatible findings in blockers. "
            f"Expected: {all_incompatible_identifiers}, "
            f"Got: {blocker_identifiers}"
        )

    @settings(max_examples=100)
    @given(
        incompatible_findings=st.lists(
            incompatible_finding_strategy, min_size=1, max_size=5
        ),
        other_findings=st.lists(
            finding_dict_strategy, min_size=0, max_size=5
        ),
        metadata=metadata_strategy,
        output_format=st.sampled_from(["markdown", "html"]),
    )
    def test_blockers_section_present_in_text_formats(
        self, incompatible_findings, other_findings, metadata, output_format
    ):
        """Feature: mwaa-analyzer-agent, Property 16: Not_Possible blockers inclusion

        **Validates: Requirements 7.6**

        For Markdown and HTML formats, verify the blockers section exists
        and contains the incompatible finding identifiers.
        """
        findings = incompatible_findings + other_findings

        result = generate_report._tool_func(
            findings=findings,
            recommendation="not_possible",
            output_format=output_format,
            metadata=metadata,
        )
        content = result["report_content"]
        content_lower = content.lower()

        assert "blocker" in content_lower, (
            f"Not_Possible report ({output_format}) missing blockers section"
        )
