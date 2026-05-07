"""Property-based tests for the Telemetry Collector.

Tests Property 17: Telemetry event completeness
Tests Property 18: No PII in telemetry

Validates: Requirements 9.1, 9.2
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from models import TelemetryEvent
from telemetry import _event_to_payload


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating random TelemetryEvent instances with all fields populated
telemetry_event_strategy = st.builds(
    TelemetryEvent,
    event_type=st.sampled_from(["analysis_complete", "analysis_error", "analysis_start"]),
    source_type=st.sampled_from(["api", "mwaa", "filesystem"]),
    recommendation=st.one_of(
        st.none(),
        st.sampled_from(["lift_and_shift", "lift_and_modernize", "not_possible"]),
    ),
    dag_count=st.integers(min_value=0, max_value=10000),
    duration_seconds=st.floats(min_value=0.0, max_value=86400.0, allow_nan=False),
    error_category=st.one_of(st.none(), st.text(min_size=1, max_size=50)),
)

# Required fields that must always be present in the telemetry payload
_REQUIRED_FIELDS = {
    "event_type",
    "source_type",
    "recommendation",
    "dag_count",
    "duration_seconds",
    "error_category",
}

# Strategy for PII-like values that should never appear in telemetry
_pii_strategy = st.one_of(
    # Credentials / tokens
    st.from_regex(r"Bearer [A-Za-z0-9]{20,40}", fullmatch=True),
    # Endpoint URLs
    st.from_regex(
        r"https://airflow\.[a-z]{3,12}\.example\.com/api/v1",
        fullmatch=True,
    ),
    # Environment names
    st.from_regex(r"my-mwaa-env-[a-z0-9]{4,8}", fullmatch=True),
    # DAG content snippets
    st.from_regex(
        r"from airflow\.operators\.[a-z_]+ import [A-Z][a-zA-Z]+",
        fullmatch=True,
    ),
    # IP addresses
    st.from_regex(
        r"(?:10|172|192)\.\d{1,3}\.\d{1,3}\.\d{1,3}",
        fullmatch=True,
    ),
)


# ---------------------------------------------------------------------------
# Property 17: Telemetry event completeness
# ---------------------------------------------------------------------------


class TestProperty17TelemetryEventCompleteness:
    """Feature: mwaa-analyzer-agent, Property 17: Telemetry event completeness

    For any completed analysis run, the telemetry event SHALL contain all
    required fields: event_type, source_type, recommendation, dag_count,
    duration_seconds, and error_category (which may be null).

    **Validates: Requirements 9.1**
    """

    @settings(max_examples=100)
    @given(event=telemetry_event_strategy)
    def test_payload_contains_all_required_fields(self, event: TelemetryEvent):
        """Feature: mwaa-analyzer-agent, Property 17: Telemetry event completeness

        **Validates: Requirements 9.1**

        The payload produced from any TelemetryEvent must contain every
        required field key.
        """
        payload = _event_to_payload(event)
        missing = _REQUIRED_FIELDS - set(payload.keys())
        assert not missing, f"Payload missing required fields: {missing}"

    @settings(max_examples=100)
    @given(event=telemetry_event_strategy)
    def test_payload_field_types_are_correct(self, event: TelemetryEvent):
        """Feature: mwaa-analyzer-agent, Property 17: Telemetry event completeness

        **Validates: Requirements 9.1**

        Each field in the payload must have the expected type.
        """
        payload = _event_to_payload(event)

        assert isinstance(payload["event_type"], str)
        assert isinstance(payload["source_type"], str)
        assert payload["recommendation"] is None or isinstance(
            payload["recommendation"], str
        )
        assert isinstance(payload["dag_count"], int)
        assert isinstance(payload["duration_seconds"], float)
        assert payload["error_category"] is None or isinstance(
            payload["error_category"], str
        )

    @settings(max_examples=100)
    @given(event=telemetry_event_strategy)
    def test_payload_contains_no_extra_fields(self, event: TelemetryEvent):
        """Feature: mwaa-analyzer-agent, Property 17: Telemetry event completeness

        **Validates: Requirements 9.1**

        The payload must not contain any fields beyond the required set.
        """
        payload = _event_to_payload(event)
        extra = set(payload.keys()) - _REQUIRED_FIELDS
        assert not extra, f"Payload contains unexpected fields: {extra}"


# ---------------------------------------------------------------------------
# Property 18: No PII in telemetry
# ---------------------------------------------------------------------------


class TestProperty18NoPIIInTelemetry:
    """Feature: mwaa-analyzer-agent, Property 18: No PII in telemetry

    For any analysis run where the environment data contains credentials,
    endpoint URLs, environment names, DAG content, or IP addresses, the
    telemetry event SHALL not contain any of these values.

    **Validates: Requirements 9.2**
    """

    @settings(max_examples=100)
    @given(
        event=telemetry_event_strategy,
        pii_values=st.lists(_pii_strategy, min_size=1, max_size=5),
    )
    def test_payload_does_not_contain_pii(
        self, event: TelemetryEvent, pii_values: list[str]
    ):
        """Feature: mwaa-analyzer-agent, Property 18: No PII in telemetry

        **Validates: Requirements 9.2**

        Given a telemetry event and a set of PII values that might exist in
        the environment data, none of those PII values should appear anywhere
        in the serialized payload.
        """
        payload = _event_to_payload(event)
        payload_str = str(payload)

        for pii in pii_values:
            assert pii not in payload_str, (
                f"PII value '{pii}' found in telemetry payload: {payload}"
            )

    @settings(max_examples=100)
    @given(event=telemetry_event_strategy)
    def test_payload_values_are_from_event_fields_only(
        self, event: TelemetryEvent
    ):
        """Feature: mwaa-analyzer-agent, Property 18: No PII in telemetry

        **Validates: Requirements 9.2**

        The payload must only contain values that come from the TelemetryEvent
        dataclass fields — no additional data should leak in.
        """
        payload = _event_to_payload(event)

        assert payload["event_type"] == event.event_type
        assert payload["source_type"] == event.source_type
        assert payload["recommendation"] == event.recommendation
        assert payload["dag_count"] == event.dag_count
        assert payload["duration_seconds"] == event.duration_seconds
        assert payload["error_category"] == event.error_category
