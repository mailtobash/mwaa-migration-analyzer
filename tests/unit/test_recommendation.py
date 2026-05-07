"""Unit tests for the Recommendation Engine.

Tests each recommendation outcome with specific finding combinations
and edge cases.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

import pytest

from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
    MigrationRecommendation,
)
from recommendation import determine_recommendation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_finding(
    status: CompatibilityStatus,
    category: FindingCategory = FindingCategory.DAG,
    identifier: str = "test-item",
) -> CompatibilityFinding:
    """Create a CompatibilityFinding with the given status."""
    return CompatibilityFinding(
        category=category,
        identifier=identifier,
        status=status,
        issues=["test issue"] if status != CompatibilityStatus.COMPATIBLE else [],
        recommendations=["test rec"] if status != CompatibilityStatus.COMPATIBLE else [],
        effort=EffortLevel.MEDIUM if status != CompatibilityStatus.COMPATIBLE else None,
    )


# ---------------------------------------------------------------------------
# Empty findings
# ---------------------------------------------------------------------------


class TestEmptyFindings:
    """Test recommendation with an empty findings list."""

    def test_empty_list_returns_lift_and_shift(self):
        """An empty findings list means no issues found → LIFT_AND_SHIFT."""
        result = determine_recommendation([])
        assert result == MigrationRecommendation.LIFT_AND_SHIFT


# ---------------------------------------------------------------------------
# All COMPATIBLE → LIFT_AND_SHIFT
# ---------------------------------------------------------------------------


class TestLiftAndShift:
    """Test that all-compatible findings produce LIFT_AND_SHIFT."""

    def test_single_compatible(self):
        findings = [_make_finding(CompatibilityStatus.COMPATIBLE)]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_SHIFT

    def test_multiple_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DAG, "dag1"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DEPENDENCY, "pkg1"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.CONFIGURATION, "core.parallelism"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.PLUGIN, "plugin1"),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_SHIFT

    def test_compatible_with_unavailable(self):
        """UNAVAILABLE status does not trigger modernize or not_possible."""
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE),
            _make_finding(CompatibilityStatus.UNAVAILABLE),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_SHIFT


# ---------------------------------------------------------------------------
# Any INCOMPATIBLE → NOT_POSSIBLE
# ---------------------------------------------------------------------------


class TestNotPossible:
    """Test that any incompatible finding produces NOT_POSSIBLE."""

    def test_single_incompatible(self):
        findings = [_make_finding(CompatibilityStatus.INCOMPATIBLE)]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_incompatible_with_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE),
            _make_finding(CompatibilityStatus.INCOMPATIBLE),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_incompatible_with_requires_modification(self):
        """INCOMPATIBLE takes precedence over REQUIRES_MODIFICATION."""
        findings = [
            _make_finding(CompatibilityStatus.REQUIRES_MODIFICATION),
            _make_finding(CompatibilityStatus.INCOMPATIBLE),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_incompatible_with_version_conflict(self):
        """INCOMPATIBLE takes precedence over VERSION_CONFLICT."""
        findings = [
            _make_finding(CompatibilityStatus.VERSION_CONFLICT),
            _make_finding(CompatibilityStatus.INCOMPATIBLE),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_incompatible_with_unsupported(self):
        """INCOMPATIBLE takes precedence over UNSUPPORTED."""
        findings = [
            _make_finding(CompatibilityStatus.UNSUPPORTED),
            _make_finding(CompatibilityStatus.INCOMPATIBLE),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_multiple_incompatible(self):
        findings = [
            _make_finding(CompatibilityStatus.INCOMPATIBLE, FindingCategory.DAG, "dag1"),
            _make_finding(CompatibilityStatus.INCOMPATIBLE, FindingCategory.DEPENDENCY, "pkg1"),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE


# ---------------------------------------------------------------------------
# REQUIRES_MODIFICATION / VERSION_CONFLICT / UNSUPPORTED → LIFT_AND_MODERNIZE
# ---------------------------------------------------------------------------


class TestLiftAndModernize:
    """Test that modernize-triggering statuses produce LIFT_AND_MODERNIZE."""

    def test_requires_modification_only(self):
        findings = [_make_finding(CompatibilityStatus.REQUIRES_MODIFICATION)]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_version_conflict_only(self):
        findings = [_make_finding(CompatibilityStatus.VERSION_CONFLICT)]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_unsupported_only(self):
        findings = [_make_finding(CompatibilityStatus.UNSUPPORTED)]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_requires_modification_with_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE),
            _make_finding(CompatibilityStatus.REQUIRES_MODIFICATION),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_version_conflict_with_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE),
            _make_finding(CompatibilityStatus.VERSION_CONFLICT),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_unsupported_with_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE),
            _make_finding(CompatibilityStatus.UNSUPPORTED),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_mixed_modernize_statuses(self):
        """Multiple modernize-triggering statuses still yield LIFT_AND_MODERNIZE."""
        findings = [
            _make_finding(CompatibilityStatus.REQUIRES_MODIFICATION),
            _make_finding(CompatibilityStatus.VERSION_CONFLICT),
            _make_finding(CompatibilityStatus.UNSUPPORTED),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE

    def test_modernize_with_unavailable(self):
        """UNAVAILABLE combined with modernize-triggering status → LIFT_AND_MODERNIZE."""
        findings = [
            _make_finding(CompatibilityStatus.UNAVAILABLE),
            _make_finding(CompatibilityStatus.REQUIRES_MODIFICATION),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE


# ---------------------------------------------------------------------------
# Mixed categories
# ---------------------------------------------------------------------------


class TestMixedCategories:
    """Test recommendation with findings from different categories."""

    def test_all_categories_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DAG, "dag1"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DEPENDENCY, "boto3"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.CONFIGURATION, "core.parallelism"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.PLUGIN, "my_plugin"),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_SHIFT

    def test_one_category_incompatible_rest_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DAG, "dag1"),
            _make_finding(CompatibilityStatus.INCOMPATIBLE, FindingCategory.DEPENDENCY, "bad-pkg"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.CONFIGURATION, "core.parallelism"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.PLUGIN, "my_plugin"),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.NOT_POSSIBLE

    def test_one_category_modernize_rest_compatible(self):
        findings = [
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DAG, "dag1"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.DEPENDENCY, "boto3"),
            _make_finding(CompatibilityStatus.UNSUPPORTED, FindingCategory.CONFIGURATION, "webserver.workers"),
            _make_finding(CompatibilityStatus.COMPATIBLE, FindingCategory.PLUGIN, "my_plugin"),
        ]
        assert determine_recommendation(findings) == MigrationRecommendation.LIFT_AND_MODERNIZE
