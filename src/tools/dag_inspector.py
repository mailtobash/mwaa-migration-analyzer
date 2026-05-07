"""DAG Inspector tool for analyzing Airflow DAG files for MWAA compatibility."""

from __future__ import annotations

import ast
import logging
import re

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


def extract_imports(source: str) -> set[str]:
    """Use ast.parse to extract all import statements from Python source.

    Returns fully qualified names. For example:
      ``from airflow.operators.python import PythonOperator``
    yields ``"airflow.operators.python.PythonOperator"``.

    Regular ``import foo.bar`` yields ``"foo.bar"``.
    """
    imports: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if module:
                    imports.add(f"{module}.{alias.name}")
                else:
                    imports.add(alias.name)
    return imports


def detect_unsupported_operators(
    imports: set[str], manifest: MWAAVersionManifest
) -> list[str]:
    """Compare imports against the manifest's supported operators.

    Only imports that look like Airflow operator/hook/sensor paths are checked.
    Returns a list of issue description strings for unsupported imports.
    """
    issues: list[str] = []
    airflow_prefixes = (
        "airflow.operators.",
        "airflow.sensors.",
        "airflow.hooks.",
        "airflow.providers.",
    )
    for imp in sorted(imports):
        if any(imp.startswith(prefix) for prefix in airflow_prefixes):
            if imp not in manifest.supported_operators:
                issues.append(
                    f"Unsupported operator/hook/sensor: {imp}"
                )
    return issues


def detect_metadata_db_access(source: str) -> list[str]:
    """Detect direct Airflow metadata database access patterns.

    Looks for SQLAlchemy session usage patterns such as:
    - ``from airflow.settings import Session``
    - ``from airflow import settings`` followed by ``settings.Session``
    - ``session.query(``
    - ``metadata.bind``
    - ``from airflow.models import DagRun`` with ``.query`` usage
    """
    issues: list[str] = []

    # Pattern: importing Session from airflow.settings
    if re.search(
        r"from\s+airflow\.settings\s+import\s+.*\bSession\b", source
    ):
        issues.append(
            "Direct metadata DB access: imports Session from airflow.settings"
        )

    # Pattern: importing settings and using settings.Session
    if re.search(r"from\s+airflow\s+import\s+.*\bsettings\b", source) and re.search(
        r"settings\.Session", source
    ):
        issues.append(
            "Direct metadata DB access: uses settings.Session"
        )

    # Pattern: session.query(
    if re.search(r"\bsession\.query\s*\(", source, re.IGNORECASE):
        issues.append(
            "Direct metadata DB access: uses session.query()"
        )

    # Pattern: metadata.bind
    if re.search(r"\bmetadata\.bind\b", source):
        issues.append(
            "Direct metadata DB access: uses metadata.bind"
        )

    return issues


def detect_subdag_usage(source: str) -> list[str]:
    """Detect SubDagOperator imports or usage.

    Returns a list of issue description strings.
    """
    issues: list[str] = []

    if re.search(r"\bSubDagOperator\b", source):
        issues.append(
            "SubDAG usage detected: SubDagOperator is deprecated; "
            "migrate to TaskGroups"
        )

    return issues


def detect_local_filesystem_paths(source: str) -> list[str]:
    """Detect local filesystem path usage for inter-task data exchange.

    Looks for patterns like:
    - /tmp/ paths
    - open() calls that write to local files
    - Hardcoded local paths used for data exchange
    """
    issues: list[str] = []

    # Pattern: /tmp/ path usage
    if re.search(r'["\'/]tmp/', source):
        issues.append(
            "Local filesystem usage: /tmp/ path detected; "
            "use S3 or XCom for inter-task data exchange"
        )

    # Pattern: open() with write mode for local files
    # Matches open('some_path', 'w') or open("some_path", "w") etc.
    if re.search(
        r"\bopen\s*\([^)]*['\"][wWaA]['\"]", source
    ):
        issues.append(
            "Local filesystem usage: writing to local files detected; "
            "use S3 or XCom for inter-task data exchange"
        )

    # Pattern: hardcoded absolute paths (not /tmp which is already caught)
    # Look for paths like /home/, /var/, /opt/, /usr/, /data/, /mnt/
    if re.search(
        r'["\']/(home|var|opt|usr|data|mnt)/', source
    ):
        issues.append(
            "Local filesystem usage: hardcoded absolute path detected; "
            "use S3 or XCom for inter-task data exchange"
        )

    return issues



@tool
def inspect_dags(
    dag_files: list[dict], target_mwaa_version: str = "2.10.3"
) -> dict:
    """Analyze DAG files for MWAA compatibility.

    Args:
        dag_files: List of DAG file dicts with 'filename' and 'content' keys.
        target_mwaa_version: Target MWAA Airflow version.

    Returns:
        A dict with 'findings' containing compatibility results per DAG.
    """
    manifest = load_manifest(target_mwaa_version)
    findings: list[dict] = []

    for dag_file in dag_files:
        filename = dag_file.get("filename", "unknown")
        content = dag_file.get("content", "")

        all_issues: list[str] = []
        all_recommendations: list[str] = []

        # Try to parse the file; handle syntax errors gracefully
        try:
            ast.parse(content)
        except SyntaxError as exc:
            logger.warning(
                "Syntax error in DAG file %s: %s — skipping detailed analysis",
                filename,
                exc,
            )
            finding = CompatibilityFinding(
                category=FindingCategory.DAG,
                identifier=filename,
                status=CompatibilityStatus.REQUIRES_MODIFICATION,
                issues=[
                    f"Syntax error: unable to parse DAG file ({exc})"
                ],
                recommendations=[
                    "Fix the syntax error and re-run the analysis"
                ],
                effort=EffortLevel.LOW,
            )
            findings.append(_finding_to_dict(finding))
            continue

        # Extract imports and run detection functions
        imports = extract_imports(content)

        unsupported_issues = detect_unsupported_operators(imports, manifest)
        if unsupported_issues:
            all_issues.extend(unsupported_issues)
            all_recommendations.append(
                "Replace unsupported operators with MWAA-compatible alternatives "
                "or install the required provider packages via requirements.txt"
            )

        metadata_issues = detect_metadata_db_access(content)
        if metadata_issues:
            all_issues.extend(metadata_issues)
            all_recommendations.append(
                "Replace direct metadata DB access with Airflow REST API "
                "or XCom for inter-task communication"
            )

        subdag_issues = detect_subdag_usage(content)
        if subdag_issues:
            all_issues.extend(subdag_issues)
            all_recommendations.append(
                "Migrate SubDagOperator usage to TaskGroups"
            )

        filesystem_issues = detect_local_filesystem_paths(content)
        if filesystem_issues:
            all_issues.extend(filesystem_issues)
            all_recommendations.append(
                "Replace local filesystem paths with S3 or XCom "
                "for inter-task data exchange"
            )

        # Determine status based on issues found
        status = _determine_status(all_issues)

        # Determine effort level
        effort = _determine_effort(all_issues)

        finding = CompatibilityFinding(
            category=FindingCategory.DAG,
            identifier=filename,
            status=status,
            issues=all_issues,
            recommendations=all_recommendations,
            effort=effort,
        )
        findings.append(_finding_to_dict(finding))

    return {"findings": findings}


def _determine_status(issues: list[str]) -> CompatibilityStatus:
    """Determine the overall compatibility status from a list of issues.

    - No issues → COMPATIBLE
    - Has unsupported operator issues → INCOMPATIBLE
    - Has other issues → REQUIRES_MODIFICATION
    """
    if not issues:
        return CompatibilityStatus.COMPATIBLE

    # Check if any issue indicates an incompatible operator
    for issue in issues:
        if issue.startswith("Unsupported operator/hook/sensor:"):
            return CompatibilityStatus.INCOMPATIBLE

    return CompatibilityStatus.REQUIRES_MODIFICATION


def _determine_effort(issues: list[str]) -> EffortLevel | None:
    """Determine the effort level based on the types of issues found."""
    if not issues:
        return None

    has_unsupported = any(
        issue.startswith("Unsupported operator/hook/sensor:") for issue in issues
    )
    has_metadata_db = any(
        issue.startswith("Direct metadata DB access:") for issue in issues
    )
    has_subdag = any("SubDAG usage" in issue for issue in issues)

    # Unsupported operators or metadata DB access are high effort
    if has_unsupported or has_metadata_db:
        return EffortLevel.HIGH

    # SubDAG migration is medium effort
    if has_subdag:
        return EffortLevel.MEDIUM

    # Local filesystem path changes are low effort
    return EffortLevel.LOW


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
