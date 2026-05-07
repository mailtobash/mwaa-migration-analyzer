"""Unit tests for the Dependency Analyzer tool.

Tests Dependency Analyzer with known packages, edge cases, and individual
helper functions.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
"""

from __future__ import annotations

import pytest

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.dependency_analyzer import (
    analyze_dependencies,
    classify_dependency,
    _build_normalized_lookup,
    _build_normalized_incompatible_set,
    _normalize_package_name,
)
from data_loader import load_manifest
from packaging.requirements import Requirement


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manifest():
    """Load the 2.10.3 MWAA version manifest."""
    return load_manifest("2.10.3")


@pytest.fixture
def pkg_lookup(manifest):
    """Build normalized package lookup from manifest."""
    return _build_normalized_lookup(manifest.pre_installed_packages)


@pytest.fixture
def incompatible_lookup(manifest):
    """Build normalized incompatible package lookup from manifest."""
    return _build_normalized_incompatible_set(manifest.known_incompatible_packages)


# ---------------------------------------------------------------------------
# Helper: _normalize_package_name
# ---------------------------------------------------------------------------


class TestNormalizePackageName:
    """Tests for the _normalize_package_name helper function."""

    def test_lowercase(self):
        assert _normalize_package_name("Flask") == "flask"

    def test_underscore_to_hyphen(self):
        assert _normalize_package_name("psycopg2_binary") == "psycopg2-binary"

    def test_mixed_case_and_separators(self):
        assert _normalize_package_name("Flask-AppBuilder") == "flask-appbuilder"

    def test_already_normalized(self):
        assert _normalize_package_name("boto3") == "boto3"

    def test_dots_normalized(self):
        assert _normalize_package_name("some.package.name") == "some-package-name"

    def test_multiple_hyphens(self):
        assert _normalize_package_name("my--package") == "my-package"

    def test_multiple_underscores(self):
        assert _normalize_package_name("my__package") == "my-package"


# ---------------------------------------------------------------------------
# Compatible packages
# ---------------------------------------------------------------------------


class TestCompatiblePackages:
    """Test analyze_dependencies with known compatible packages."""

    def test_boto3_exact_version(self):
        """boto3==1.35.36 is pre-installed in MWAA 2.10.3."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==1.35.36",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["issues"] == []

    def test_click_gte_constraint(self):
        """click>=8.0 should be compatible since MWAA has 8.1.7."""
        result = analyze_dependencies._tool_func(
            requirements_content="click>=8.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_requests_compatible_range(self):
        """requests>=2.30 should be compatible since MWAA has 2.32.3."""
        result = analyze_dependencies._tool_func(
            requirements_content="requests>=2.30",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_compatible_no_effort(self):
        """Compatible packages should have no effort level."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==1.35.36",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] is None

    def test_finding_has_category(self):
        """All findings should have the dependency category."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==1.35.36",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["category"] == FindingCategory.DEPENDENCY.value


# ---------------------------------------------------------------------------
# Version conflicts
# ---------------------------------------------------------------------------


class TestVersionConflicts:
    """Test analyze_dependencies with version conflicts."""

    def test_boto3_future_version(self):
        """boto3==2.0.0 conflicts with MWAA's 1.35.36."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==2.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.VERSION_CONFLICT.value
        assert len(findings[0]["issues"]) > 0
        assert "1.35.36" in findings[0]["issues"][0]

    def test_flask_old_version(self):
        """Flask==1.0.0 conflicts with MWAA's 2.2.5."""
        result = analyze_dependencies._tool_func(
            requirements_content="Flask==1.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.VERSION_CONFLICT.value

    def test_version_conflict_has_recommendations(self):
        """Version conflict findings should include recommendations."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==2.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0

    def test_version_conflict_low_effort(self):
        """Version conflicts should have LOW effort."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3==2.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "low"


# ---------------------------------------------------------------------------
# Unavailable packages
# ---------------------------------------------------------------------------


class TestUnavailablePackages:
    """Test analyze_dependencies with unavailable packages."""

    def test_random_package(self):
        """A package not in MWAA should be unavailable."""
        result = analyze_dependencies._tool_func(
            requirements_content="some-random-package==1.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.UNAVAILABLE.value
        assert len(findings[0]["issues"]) > 0

    def test_unavailable_has_recommendations(self):
        """Unavailable packages should include recommendations."""
        result = analyze_dependencies._tool_func(
            requirements_content="some-random-package==1.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0

    def test_unavailable_medium_effort(self):
        """Unavailable packages should have MEDIUM effort."""
        result = analyze_dependencies._tool_func(
            requirements_content="some-random-package==1.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "medium"


# ---------------------------------------------------------------------------
# Incompatible packages (system-level C libraries)
# ---------------------------------------------------------------------------


class TestIncompatiblePackages:
    """Test analyze_dependencies with known incompatible packages."""

    def test_numpy_incompatible(self):
        """numpy requires system-level C libraries."""
        result = analyze_dependencies._tool_func(
            requirements_content="numpy==1.24.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.INCOMPATIBLE.value
        assert any("system-level" in issue for issue in findings[0]["issues"])

    def test_opencv_incompatible(self):
        """opencv-python requires system-level C libraries."""
        result = analyze_dependencies._tool_func(
            requirements_content="opencv-python==4.8.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.INCOMPATIBLE.value

    def test_pyodbc_incompatible(self):
        """pyodbc requires system-level C libraries."""
        result = analyze_dependencies._tool_func(
            requirements_content="pyodbc==4.0.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.INCOMPATIBLE.value

    def test_incompatible_high_effort(self):
        """Incompatible packages should have HIGH effort."""
        result = analyze_dependencies._tool_func(
            requirements_content="numpy==1.24.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "high"

    def test_incompatible_has_recommendations(self):
        """Incompatible packages should include recommendations."""
        result = analyze_dependencies._tool_func(
            requirements_content="numpy==1.24.0",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0


# ---------------------------------------------------------------------------
# Empty and malformed input
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test analyze_dependencies with edge cases."""

    def test_empty_requirements(self):
        """Empty requirements.txt should produce no findings."""
        result = analyze_dependencies._tool_func(
            requirements_content="",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_malformed_entry_skipped(self):
        """Malformed entries should be skipped without error."""
        result = analyze_dependencies._tool_func(
            requirements_content="this is not a valid requirement!!!@@@",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_comments_and_blank_lines(self):
        """Comments and blank lines should be skipped."""
        content = (
            "# This is a comment\n"
            "\n"
            "   \n"
            "# Another comment\n"
            "boto3==1.35.36\n"
            "\n"
        )
        result = analyze_dependencies._tool_func(
            requirements_content=content,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_mixed_valid_and_malformed(self):
        """Valid entries should be processed even if some are malformed."""
        content = (
            "boto3==1.35.36\n"
            "!!!invalid!!!\n"
            "click>=8.0\n"
        )
        result = analyze_dependencies._tool_func(
            requirements_content=content,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 2


# ---------------------------------------------------------------------------
# Package name normalization
# ---------------------------------------------------------------------------


class TestPackageNameNormalization:
    """Test that package name normalization works correctly in classification."""

    def test_flask_case_insensitive(self):
        """Flask vs flask should both match the pre-installed package."""
        result_upper = analyze_dependencies._tool_func(
            requirements_content="Flask==2.2.5",
            target_mwaa_version="2.10.3",
        )
        result_lower = analyze_dependencies._tool_func(
            requirements_content="flask==2.2.5",
            target_mwaa_version="2.10.3",
        )
        assert result_upper["findings"][0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert result_lower["findings"][0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_psycopg2_binary_underscore_vs_hyphen(self):
        """psycopg2-binary vs psycopg2_binary should both match."""
        result_hyphen = analyze_dependencies._tool_func(
            requirements_content="psycopg2-binary==2.9.9",
            target_mwaa_version="2.10.3",
        )
        result_underscore = analyze_dependencies._tool_func(
            requirements_content="psycopg2_binary==2.9.9",
            target_mwaa_version="2.10.3",
        )
        assert result_hyphen["findings"][0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert result_underscore["findings"][0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_markup_safe_normalization(self):
        """MarkupSafe vs markupsafe should both match."""
        result = analyze_dependencies._tool_func(
            requirements_content="markupsafe==2.1.5",
            target_mwaa_version="2.10.3",
        )
        assert result["findings"][0]["status"] == CompatibilityStatus.COMPATIBLE.value


# ---------------------------------------------------------------------------
# Bare package names (no version constraint)
# ---------------------------------------------------------------------------


class TestBarePackageNames:
    """Test analyze_dependencies with bare package names (no version constraint)."""

    def test_bare_pre_installed_package(self):
        """A bare pre-installed package name should be compatible."""
        result = analyze_dependencies._tool_func(
            requirements_content="boto3",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_bare_unknown_package(self):
        """A bare unknown package name should be unavailable."""
        result = analyze_dependencies._tool_func(
            requirements_content="some-random-package",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.UNAVAILABLE.value

    def test_bare_incompatible_package(self):
        """A bare incompatible package name should be incompatible."""
        result = analyze_dependencies._tool_func(
            requirements_content="numpy",
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.INCOMPATIBLE.value


# ---------------------------------------------------------------------------
# Multiple dependencies
# ---------------------------------------------------------------------------


class TestMultipleDependencies:
    """Test analyze_dependencies with multiple dependencies."""

    def test_mixed_statuses(self):
        """A requirements.txt with mixed statuses should produce correct findings."""
        content = (
            "boto3==1.35.36\n"
            "boto3==2.0.0\n"
            "some-random-package==1.0.0\n"
            "numpy==1.24.0\n"
        )
        result = analyze_dependencies._tool_func(
            requirements_content=content,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 4

        statuses = [f["status"] for f in findings]
        assert CompatibilityStatus.COMPATIBLE.value in statuses
        assert CompatibilityStatus.VERSION_CONFLICT.value in statuses
        assert CompatibilityStatus.UNAVAILABLE.value in statuses
        assert CompatibilityStatus.INCOMPATIBLE.value in statuses

    def test_all_compatible(self):
        """All compatible packages should produce all compatible findings."""
        content = (
            "boto3==1.35.36\n"
            "click>=8.0\n"
            "requests>=2.30\n"
        )
        result = analyze_dependencies._tool_func(
            requirements_content=content,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 3
        assert all(
            f["status"] == CompatibilityStatus.COMPATIBLE.value
            for f in findings
        )
