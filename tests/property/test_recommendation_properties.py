"""Property-based tests for the Recommendation Engine.

Tests Property 11: Migration recommendation determinism.

For any list of Compatibility_Findings, the recommendation engine SHALL produce:
- Lift_and_Shift if all findings have compatible status
- Not_Possible if any finding has incompatible status
- Lift_and_Modernize if at least one finding has requires_modification,
  version_conflict, or unsupported status and none have incompatible status.

Validates: Requirements 6.2, 6.3, 6.4
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
    MigrationRecommendation,
)
from recommendation import determine_recommendation


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating random CompatibilityFinding instances
finding_strategy = st.builds(
    CompatibilityFinding,
    category=st.sampled_from(FindingCategory),
    identifier=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    status=st.sampled_from(CompatibilityStatus),
    issues=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    recommendations=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    effort=st.one_of(st.none(), st.sampled_from(EffortLevel)),
)

# Strategy for findings that are all COMPATIBLE
compatible_finding_strategy = st.builds(
    CompatibilityFinding,
    category=st.sampled_from(FindingCategory),
    identifier=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    status=st.just(CompatibilityStatus.COMPATIBLE),
    issues=st.just([]),
    recommendations=st.just([]),
    effort=st.none(),
)

# Statuses that trigger LIFT_AND_MODERNIZE (when no INCOMPATIBLE is present)
_MODERNIZE_STATUSES = [
    CompatibilityStatus.REQUIRES_MODIFICATION,
    CompatibilityStatus.VERSION_CONFLICT,
    CompatibilityStatus.UNSUPPORTED,
]

# Strategy for findings with a modernize-triggering status
modernize_finding_strategy = st.builds(
    CompatibilityFinding,
    category=st.sampled_from(FindingCategory),
    identifier=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    status=st.sampled_from(_MODERNIZE_STATUSES),
    issues=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    recommendations=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    effort=st.one_of(st.none(), st.sampled_from(EffortLevel)),
)

# Strategy for findings that are NOT incompatible (compatible, modernize-triggering, or unavailable)
non_incompatible_finding_strategy = st.builds(
    CompatibilityFinding,
    category=st.sampled_from(FindingCategory),
    identifier=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    status=st.sampled_from([
        s for s in CompatibilityStatus if s != CompatibilityStatus.INCOMPATIBLE
    ]),
    issues=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    recommendations=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    effort=st.one_of(st.none(), st.sampled_from(EffortLevel)),
)

# Strategy for an INCOMPATIBLE finding
incompatible_finding_strategy = st.builds(
    CompatibilityFinding,
    category=st.sampled_from(FindingCategory),
    identifier=st.text(
        min_size=1,
        max_size=100,
        alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    ),
    status=st.just(CompatibilityStatus.INCOMPATIBLE),
    issues=st.lists(st.text(min_size=1, max_size=200), min_size=1, max_size=5),
    recommendations=st.lists(st.text(min_size=1, max_size=200), max_size=5),
    effort=st.one_of(st.none(), st.sampled_from(EffortLevel)),
)


# ---------------------------------------------------------------------------
# Property 11: Migration recommendation determinism
# ---------------------------------------------------------------------------


class TestProperty11MigrationRecommendationDeterminism:
    """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

    For any list of Compatibility_Findings, the recommendation engine SHALL
    produce: Lift_and_Shift if all findings have compatible status;
    Not_Possible if any finding has incompatible status;
    Lift_and_Modernize if at least one finding has requires_modification,
    version_conflict, or unsupported status and none have incompatible status.

    Validates: Requirements 6.2, 6.3, 6.4
    """

    @settings(max_examples=100)
    @given(findings=st.lists(compatible_finding_strategy, min_size=0, max_size=20))
    def test_all_compatible_yields_lift_and_shift(self, findings):
        """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

        **Validates: Requirements 6.2**

        When all findings have COMPATIBLE status, the recommendation should
        be LIFT_AND_SHIFT.
        """
        result = determine_recommendation(findings)
        assert result == MigrationRecommendation.LIFT_AND_SHIFT, (
            f"Expected LIFT_AND_SHIFT for all-compatible findings, got {result}"
        )

    @settings(max_examples=100)
    @given(
        other_findings=st.lists(finding_strategy, min_size=0, max_size=10),
        incompatible=incompatible_finding_strategy,
    )
    def test_any_incompatible_yields_not_possible(self, other_findings, incompatible):
        """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

        **Validates: Requirements 6.4**

        When any finding has INCOMPATIBLE status, the recommendation should
        be NOT_POSSIBLE regardless of other findings.
        """
        findings = other_findings + [incompatible]
        result = determine_recommendation(findings)
        assert result == MigrationRecommendation.NOT_POSSIBLE, (
            f"Expected NOT_POSSIBLE when INCOMPATIBLE finding present, got {result}"
        )

    @settings(max_examples=100)
    @given(
        non_incompatible=st.lists(non_incompatible_finding_strategy, min_size=0, max_size=10),
        modernize=modernize_finding_strategy,
    )
    def test_modernize_status_without_incompatible_yields_lift_and_modernize(
        self, non_incompatible, modernize
    ):
        """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

        **Validates: Requirements 6.3**

        When at least one finding has requires_modification, version_conflict,
        or unsupported status and none have incompatible status, the
        recommendation should be LIFT_AND_MODERNIZE.
        """
        findings = non_incompatible + [modernize]
        result = determine_recommendation(findings)
        assert result == MigrationRecommendation.LIFT_AND_MODERNIZE, (
            f"Expected LIFT_AND_MODERNIZE with modernize-triggering status "
            f"and no incompatible, got {result}"
        )

    @settings(max_examples=100)
    @given(findings=st.lists(finding_strategy, min_size=0, max_size=20))
    def test_recommendation_is_always_valid_enum(self, findings):
        """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

        **Validates: Requirements 6.2, 6.3, 6.4**

        For any list of findings, the recommendation should always be a valid
        MigrationRecommendation enum value.
        """
        result = determine_recommendation(findings)
        assert isinstance(result, MigrationRecommendation), (
            f"Expected MigrationRecommendation enum, got {type(result)}"
        )

    @settings(max_examples=100)
    @given(findings=st.lists(finding_strategy, min_size=0, max_size=20))
    def test_recommendation_is_deterministic(self, findings):
        """Feature: mwaa-analyzer-agent, Property 11: Migration recommendation determinism

        **Validates: Requirements 6.2, 6.3, 6.4**

        Calling determine_recommendation twice with the same findings should
        produce the same result.
        """
        result1 = determine_recommendation(findings)
        result2 = determine_recommendation(findings)
        assert result1 == result2, (
            f"Non-deterministic recommendation: {result1} vs {result2}"
        )
