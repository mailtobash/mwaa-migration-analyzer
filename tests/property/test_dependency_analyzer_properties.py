"""Property-based tests for the Dependency Analyzer tool.

Tests Properties 5, 6, and 4 as they relate to the Dependency Analyzer:
- Property 5: Requirements.txt parsing round-trip
- Property 6: Dependency compatibility classification
- Property 4: Compatibility finding structural invariant (Dependency Analyzer)
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume
from packaging.requirements import Requirement

from models import (
    CompatibilityStatus,
    FindingCategory,
    MWAAVersionManifest,
)
from tools.dependency_analyzer import (
    analyze_dependencies,
    classify_dependency,
    _build_normalized_lookup,
    _build_normalized_incompatible_set,
    _normalize_package_name,
)
from data_loader import load_manifest


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating valid requirements.txt lines.
# We use a composite strategy to ensure the package name is valid
# (no trailing hyphens/underscores, only ASCII digits in versions).
@st.composite
def _requirement_line(draw):
    """Generate a valid requirements.txt line that packaging can parse."""
    # Package name: starts with letter, middle can have letters/digits/hyphens,
    # ends with letter or digit (no trailing hyphen/underscore)
    prefix = draw(st.from_regex(r"[a-z]", fullmatch=True))
    middle = draw(st.from_regex(r"[a-z0-9]([a-z0-9_-]{0,20}[a-z0-9])?", fullmatch=True))
    name = prefix + middle
    op = draw(st.sampled_from(["==", ">=", "<=", "~=", "!="]))
    major = draw(st.integers(min_value=0, max_value=99))
    minor = draw(st.integers(min_value=0, max_value=99))
    use_patch = draw(st.booleans())
    if use_patch:
        patch = draw(st.integers(min_value=0, max_value=99))
        return f"{name}{op}{major}.{minor}.{patch}"
    return f"{name}{op}{major}.{minor}"


requirement_strategy = _requirement_line()


# ---------------------------------------------------------------------------
# Property 5: Requirements.txt parsing round-trip
# ---------------------------------------------------------------------------


class TestProperty5RequirementsParsingRoundTrip:
    """Feature: mwaa-analyzer-agent, Property 5: Requirements.txt parsing round-trip

    For any valid requirements.txt entry string containing a package name and
    version constraint, parsing the entry and then formatting it back SHALL
    produce a string that, when parsed again, yields the same package name
    and version constraint.

    Validates: Requirements 3.1
    """

    @settings(max_examples=100)
    @given(req_line=requirement_strategy)
    def test_parse_format_reparse_yields_same_name_and_specifier(self, req_line):
        """Feature: mwaa-analyzer-agent, Property 5: Requirements.txt parsing round-trip

        **Validates: Requirements 3.1**
        """
        # Parse the requirement line
        req1 = Requirement(req_line)

        # Format it back to a string
        formatted = str(req1)

        # Parse the formatted string again
        req2 = Requirement(formatted)

        # The normalized name and specifier should be identical
        assert _normalize_package_name(req1.name) == _normalize_package_name(req2.name), (
            f"Package name mismatch after round-trip: "
            f"'{req1.name}' vs '{req2.name}' (from '{req_line}')"
        )
        assert str(req1.specifier) == str(req2.specifier), (
            f"Specifier mismatch after round-trip: "
            f"'{req1.specifier}' vs '{req2.specifier}' (from '{req_line}')"
        )


# ---------------------------------------------------------------------------
# Property 6: Dependency compatibility classification
# ---------------------------------------------------------------------------


class TestProperty6DependencyCompatibilityClassification:
    """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

    For any dependency with a package name and version constraint, given a
    MWAA version manifest, the Dependency_Analyzer SHALL classify it as:
    compatible, version_conflict, unavailable, or incompatible.

    Validates: Requirements 3.2, 3.3, 3.4
    """

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        self.manifest = load_manifest("2.10.3")
        self.pkg_lookup = _build_normalized_lookup(
            self.manifest.pre_installed_packages
        )
        self.incompatible_lookup = _build_normalized_incompatible_set(
            self.manifest.known_incompatible_packages
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_pre_installed_compatible_version(self, data):
        """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

        **Validates: Requirements 3.2, 3.3, 3.4**

        A pre-installed package with a matching version constraint should be
        classified as compatible.
        """
        # Pick a random pre-installed package from the manifest
        assume(len(self.manifest.pre_installed_packages) > 0)
        pkg_name = data.draw(
            st.sampled_from(sorted(self.manifest.pre_installed_packages.keys()))
        )
        pkg_version = self.manifest.pre_installed_packages[pkg_name]

        # Build a requirement that matches the installed version exactly
        req_line = f"{pkg_name}=={pkg_version}"
        req = Requirement(req_line)

        finding = classify_dependency(
            req, self.manifest, self.pkg_lookup, self.incompatible_lookup
        )
        assert finding.status == CompatibilityStatus.COMPATIBLE, (
            f"Pre-installed package '{req_line}' should be compatible, "
            f"got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_pre_installed_version_conflict(self, data):
        """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

        **Validates: Requirements 3.2, 3.3, 3.4**

        A pre-installed package with a non-matching version constraint should
        be classified as version_conflict.
        """
        assume(len(self.manifest.pre_installed_packages) > 0)
        pkg_name = data.draw(
            st.sampled_from(sorted(self.manifest.pre_installed_packages.keys()))
        )

        # Use a version that definitely won't match (99.99.99)
        req_line = f"{pkg_name}==99.99.99"
        req = Requirement(req_line)

        finding = classify_dependency(
            req, self.manifest, self.pkg_lookup, self.incompatible_lookup
        )
        assert finding.status == CompatibilityStatus.VERSION_CONFLICT, (
            f"Pre-installed package '{req_line}' with impossible version "
            f"should be version_conflict, got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_known_incompatible_package(self, data):
        """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

        **Validates: Requirements 3.2, 3.3, 3.4**

        A package in the known_incompatible_packages set should be classified
        as incompatible.
        """
        assume(len(self.manifest.known_incompatible_packages) > 0)
        pkg_name = data.draw(
            st.sampled_from(sorted(self.manifest.known_incompatible_packages))
        )

        req_line = f"{pkg_name}==1.0.0"
        req = Requirement(req_line)

        finding = classify_dependency(
            req, self.manifest, self.pkg_lookup, self.incompatible_lookup
        )
        assert finding.status == CompatibilityStatus.INCOMPATIBLE, (
            f"Known incompatible package '{req_line}' should be incompatible, "
            f"got {finding.status}"
        )

    @settings(max_examples=100)
    @given(req_line=requirement_strategy)
    def test_classification_is_always_valid_status(self, req_line):
        """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

        **Validates: Requirements 3.2, 3.3, 3.4**

        For any valid requirement, the classification should always produce
        one of the four valid statuses.
        """
        req = Requirement(req_line)
        finding = classify_dependency(
            req, self.manifest, self.pkg_lookup, self.incompatible_lookup
        )

        valid_statuses = {
            CompatibilityStatus.COMPATIBLE,
            CompatibilityStatus.VERSION_CONFLICT,
            CompatibilityStatus.UNAVAILABLE,
            CompatibilityStatus.INCOMPATIBLE,
        }
        assert finding.status in valid_statuses, (
            f"Classification of '{req_line}' produced unexpected status: "
            f"{finding.status}"
        )

    @settings(max_examples=100)
    @given(
        pkg_suffix=st.from_regex(r"[a-z][a-z0-9]{5,20}", fullmatch=True),
        major=st.integers(min_value=0, max_value=99),
        minor=st.integers(min_value=0, max_value=99),
        patch=st.integers(min_value=0, max_value=99),
    )
    def test_unknown_package_is_unavailable(self, pkg_suffix, major, minor, patch):
        """Feature: mwaa-analyzer-agent, Property 6: Dependency compatibility classification

        **Validates: Requirements 3.2, 3.3, 3.4**

        A package that is neither pre-installed nor known-incompatible should
        be classified as unavailable.
        """
        # Prefix with "zzz-test-" to ensure it's not in any manifest
        pkg_name = f"zzz-test-{pkg_suffix}"
        normalized = _normalize_package_name(pkg_name)

        # Skip if by some chance it matches a real package
        assume(normalized not in self.pkg_lookup)
        assume(normalized not in self.incompatible_lookup)

        version = f"{major}.{minor}.{patch}"
        req_line = f"{pkg_name}=={version}"
        req = Requirement(req_line)

        finding = classify_dependency(
            req, self.manifest, self.pkg_lookup, self.incompatible_lookup
        )
        assert finding.status == CompatibilityStatus.UNAVAILABLE, (
            f"Unknown package '{req_line}' should be unavailable, "
            f"got {finding.status}"
        )


# ---------------------------------------------------------------------------
# Property 4: Compatibility finding structural invariant (Dependency Analyzer)
# ---------------------------------------------------------------------------


class TestProperty4FindingStructuralInvariantDependencyAnalyzer:
    """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Dependency Analyzer)

    For any input to analyze_dependencies, every produced finding SHALL
    contain a non-empty identifier, a valid CompatibilityStatus enum value,
    and an issues list.

    Validates: Requirements 3.5
    """

    @settings(max_examples=100)
    @given(req_line=requirement_strategy)
    def test_single_requirement_finding_structure(self, req_line):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Dependency Analyzer)

        **Validates: Requirements 3.5**
        """
        result = analyze_dependencies._tool_func(
            requirements_content=req_line,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) >= 1, (
            f"analyze_dependencies should produce at least one finding for '{req_line}'"
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
    def test_multiple_requirements_all_have_valid_findings(self, data):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Dependency Analyzer)

        **Validates: Requirements 3.5**
        """
        num_reqs = data.draw(st.integers(min_value=1, max_value=5))
        lines = [data.draw(requirement_strategy) for _ in range(num_reqs)]
        requirements_content = "\n".join(lines)

        result = analyze_dependencies._tool_func(
            requirements_content=requirements_content,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]

        # Should have one finding per requirement line
        assert len(findings) == num_reqs, (
            f"Expected {num_reqs} findings, got {len(findings)}"
        )

        valid_statuses = {s.value for s in CompatibilityStatus}

        for finding in findings:
            assert finding["identifier"]  # non-empty
            assert finding["status"] in valid_statuses
            assert isinstance(finding["issues"], list)
