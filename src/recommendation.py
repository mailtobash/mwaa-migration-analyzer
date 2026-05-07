"""Recommendation Engine for deriving migration recommendations from findings.

Deterministic logic for mapping a list of CompatibilityFinding instances
to a single MigrationRecommendation outcome.

Requirements: 6.1, 6.2, 6.3, 6.4
"""

from __future__ import annotations

from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    MigrationRecommendation,
)


def determine_recommendation(
    findings: list[CompatibilityFinding],
) -> MigrationRecommendation:
    """Determine the migration recommendation from a list of compatibility findings.

    Decision logic (evaluated in priority order):
    1. If any finding has INCOMPATIBLE status → NOT_POSSIBLE
    2. If any finding has REQUIRES_MODIFICATION, VERSION_CONFLICT, or UNSUPPORTED
       status (and none are INCOMPATIBLE) → LIFT_AND_MODERNIZE
    3. If all findings have COMPATIBLE status (or the list is empty) → LIFT_AND_SHIFT

    Args:
        findings: List of CompatibilityFinding instances from analysis tools.

    Returns:
        A MigrationRecommendation enum value.
    """
    statuses = [f.status for f in findings]

    if any(s == CompatibilityStatus.INCOMPATIBLE for s in statuses):
        return MigrationRecommendation.NOT_POSSIBLE

    if any(
        s
        in (
            CompatibilityStatus.REQUIRES_MODIFICATION,
            CompatibilityStatus.VERSION_CONFLICT,
            CompatibilityStatus.UNSUPPORTED,
        )
        for s in statuses
    ):
        return MigrationRecommendation.LIFT_AND_MODERNIZE

    return MigrationRecommendation.LIFT_AND_SHIFT
