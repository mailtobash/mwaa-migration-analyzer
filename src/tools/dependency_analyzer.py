"""Dependency Analyzer tool for checking Python dependencies against MWAA compatibility."""

from __future__ import annotations

import logging
import re

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from strands import tool

from data_loader import load_manifest
from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
    MWAAVersionManifest,
)

logger = logging.getLogger(__name__)


def _normalize_package_name(name: str) -> str:
    """Normalize a package name for case-insensitive, hyphen/underscore-agnostic comparison.

    PEP 503: package names are compared by lowercasing and replacing any run of
    underscores, hyphens, or periods with a single hyphen.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _build_normalized_lookup(
    packages: dict[str, str],
) -> dict[str, tuple[str, str]]:
    """Build a lookup dict mapping normalized package names to (original_name, version).

    Args:
        packages: Dict of package_name -> version from the manifest.

    Returns:
        Dict mapping normalized name to (original_name, version_string).
    """
    lookup: dict[str, tuple[str, str]] = {}
    for name, version in packages.items():
        normalized = _normalize_package_name(name)
        lookup[normalized] = (name, version)
    return lookup


def _build_normalized_incompatible_set(
    incompatible: set[str],
) -> dict[str, str]:
    """Build a lookup dict mapping normalized incompatible package names to original names.

    Args:
        incompatible: Set of known incompatible package names.

    Returns:
        Dict mapping normalized name to original name.
    """
    return {_normalize_package_name(name): name for name in incompatible}


def classify_dependency(
    req: Requirement,
    manifest: MWAAVersionManifest,
    pkg_lookup: dict[str, tuple[str, str]],
    incompatible_lookup: dict[str, str],
) -> CompatibilityFinding:
    """Classify a single dependency against the MWAA version manifest.

    Args:
        req: Parsed Requirement object.
        manifest: The MWAA version manifest.
        pkg_lookup: Normalized package name -> (original_name, version) lookup.
        incompatible_lookup: Normalized package name -> original name for incompatible packages.

    Returns:
        A CompatibilityFinding for this dependency.
    """
    normalized_name = _normalize_package_name(req.name)
    identifier = str(req)

    # Check if the package is in the known incompatible set
    if normalized_name in incompatible_lookup:
        return CompatibilityFinding(
            category=FindingCategory.DEPENDENCY,
            identifier=identifier,
            status=CompatibilityStatus.INCOMPATIBLE,
            issues=[
                f"Package '{req.name}' requires system-level C libraries "
                f"that are not available in the MWAA runtime"
            ],
            recommendations=[
                "Consider using a custom container image for MWAA, "
                "or find a pure-Python alternative package"
            ],
            effort=EffortLevel.HIGH,
        )

    # Check if the package is pre-installed in MWAA
    if normalized_name in pkg_lookup:
        original_name, mwaa_version_str = pkg_lookup[normalized_name]
        mwaa_version = Version(mwaa_version_str)

        # Check if the version constraint is satisfied
        if req.specifier and not req.specifier.contains(mwaa_version):
            return CompatibilityFinding(
                category=FindingCategory.DEPENDENCY,
                identifier=identifier,
                status=CompatibilityStatus.VERSION_CONFLICT,
                issues=[
                    f"Package '{req.name}' requires {req.specifier} but MWAA provides "
                    f"version {mwaa_version_str}"
                ],
                recommendations=[
                    f"Update the version constraint to be compatible with "
                    f"{original_name}=={mwaa_version_str} provided by MWAA, "
                    f"or pin to the MWAA-provided version"
                ],
                effort=EffortLevel.LOW,
            )

        # Package is pre-installed and version is compatible
        return CompatibilityFinding(
            category=FindingCategory.DEPENDENCY,
            identifier=identifier,
            status=CompatibilityStatus.COMPATIBLE,
            issues=[],
            recommendations=[],
            effort=None,
        )

    # Package is not pre-installed and not known-incompatible
    return CompatibilityFinding(
        category=FindingCategory.DEPENDENCY,
        identifier=identifier,
        status=CompatibilityStatus.UNAVAILABLE,
        issues=[
            f"Package '{req.name}' is not pre-installed in MWAA {manifest.airflow_version}"
        ],
        recommendations=[
            "Add this package to your MWAA requirements.txt; "
            "it will be installed at environment startup"
        ],
        effort=EffortLevel.MEDIUM,
    )


@tool
def analyze_dependencies(
    requirements_content: str, target_mwaa_version: str = "2.10.3"
) -> dict:
    """Analyze Python dependencies for MWAA compatibility.

    Args:
        requirements_content: Raw content of requirements.txt.
        target_mwaa_version: Target MWAA Airflow version (e.g., "2.10.3").

    Returns:
        A dict with 'findings' containing compatibility results per dependency.
    """
    manifest = load_manifest(target_mwaa_version)
    findings: list[dict] = []

    # Build normalized lookup tables once
    pkg_lookup = _build_normalized_lookup(manifest.pre_installed_packages)
    incompatible_lookup = _build_normalized_incompatible_set(
        manifest.known_incompatible_packages
    )

    for line in requirements_content.splitlines():
        # Strip whitespace
        stripped = line.strip()

        # Skip blank lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Try to parse the requirement line
        try:
            req = Requirement(stripped)
        except InvalidRequirement:
            logger.warning(
                "Malformed requirement line, skipping: %s", stripped
            )
            continue

        finding = classify_dependency(req, manifest, pkg_lookup, incompatible_lookup)
        findings.append(_finding_to_dict(finding))

    return {"findings": findings}


def _finding_to_dict(finding: CompatibilityFinding) -> dict:
    """Convert a CompatibilityFinding dataclass to a plain dict for tool output."""
    return {
        "category": finding.category.value,
        "identifier": finding.identifier,
        "status": finding.status.value,
        "issues": finding.issues,
        "recommendations": finding.recommendations,
        "effort": finding.effort.value if finding.effort else None,
    }
