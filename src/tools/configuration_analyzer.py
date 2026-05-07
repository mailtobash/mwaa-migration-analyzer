"""Configuration Analyzer tool for checking Airflow configuration against MWAA compatibility."""

from __future__ import annotations

import logging
import re

from strands import tool

from data_loader import load_manifest
from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
)

logger = logging.getLogger(__name__)

# Regex pattern for detecting filesystem paths in configuration values.
# Matches:
#   - Unix absolute paths: /some/path
#   - Unix relative paths: ./some/path or ../some/path
#   - Windows drive letter paths: C:\ or D:/
_FILESYSTEM_PATH_RE = re.compile(
    r"(?:^/[a-zA-Z0-9_.\-/]+)"       # Unix absolute path
    r"|(?:^\.\.?/[a-zA-Z0-9_.\-/]*)"  # Unix relative path (./ or ../)
    r"|(?:^[a-zA-Z]:[\\\/])",          # Windows drive letter (e.g., C:\ or D:/)
)


def _is_filesystem_path(value: str) -> bool:
    """Check whether a configuration value looks like a filesystem path.

    Detects values starting with ``/``, ``./``, ``../``, or a Windows drive
    letter such as ``C:\\``.
    """
    return bool(_FILESYSTEM_PATH_RE.match(value.strip()))


def classify_config_entry(
    section: str,
    key: str,
    value: str,
    supported_keys: set[str],
) -> CompatibilityFinding:
    """Classify a single configuration entry against the MWAA version manifest.

    Args:
        section: The configuration section (e.g., "core", "webserver").
        key: The configuration key within the section.
        value: The configuration value.
        supported_keys: Set of supported config keys in "section.key" format.

    Returns:
        A CompatibilityFinding for this configuration entry.
    """
    config_key = f"{section}.{key}"
    identifier = f"{config_key} = {value}"

    # Check if the key is supported by MWAA
    is_supported = config_key in supported_keys

    # Check if the value contains a filesystem path
    has_path = _is_filesystem_path(value)

    # Determine status, issues, and recommendations
    if not is_supported:
        return CompatibilityFinding(
            category=FindingCategory.CONFIGURATION,
            identifier=identifier,
            status=CompatibilityStatus.UNSUPPORTED,
            issues=[
                f"Configuration key '{config_key}' is not supported by MWAA; "
                f"MWAA manages this setting internally"
            ],
            recommendations=[
                "Remove this configuration override or check the MWAA documentation "
                "for the equivalent MWAA-managed setting"
            ],
            effort=EffortLevel.LOW,
        )

    if has_path:
        return CompatibilityFinding(
            category=FindingCategory.CONFIGURATION,
            identifier=identifier,
            status=CompatibilityStatus.REQUIRES_MODIFICATION,
            issues=[
                f"Configuration value for '{config_key}' references a local "
                f"filesystem path '{value}'; MWAA uses managed storage"
            ],
            recommendations=[
                "Replace the local filesystem path with an S3 path or "
                "MWAA-compatible storage reference"
            ],
            effort=EffortLevel.MEDIUM,
        )

    # Supported key with no path issues
    return CompatibilityFinding(
        category=FindingCategory.CONFIGURATION,
        identifier=identifier,
        status=CompatibilityStatus.COMPATIBLE,
        issues=[],
        recommendations=[],
        effort=None,
    )


@tool
def analyze_configuration(
    config_entries: dict, target_mwaa_version: str = "2.10.3"
) -> dict:
    """Analyze Airflow configuration for MWAA compatibility.

    Args:
        config_entries: Dict of {section: {key: value}} configuration entries.
        target_mwaa_version: Target MWAA Airflow version (e.g., "2.10.3").

    Returns:
        A dict with 'findings' containing compatibility results per config entry.
    """
    manifest = load_manifest(target_mwaa_version)
    findings: list[dict] = []

    for section, keys in config_entries.items():
        if not isinstance(keys, dict):
            logger.warning(
                "Skipping non-dict section value for section '%s'", section
            )
            continue

        for key, value in keys.items():
            finding = classify_config_entry(
                section=section,
                key=key,
                value=str(value),
                supported_keys=manifest.supported_config_keys,
            )
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
