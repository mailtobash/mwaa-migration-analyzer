"""Unit tests for the Telemetry Collector.

Tests opt-out behavior, first-run notice, network failure handling,
and that no PII is included in events.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest

from models import TelemetryEvent
from telemetry import (
    TelemetryCollector,
    _event_to_payload,
    _FIRST_RUN_NOTICE,
    _MARKER_FILENAME,
    _TELEMETRY_OPT_OUT_ENV,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_event(**overrides) -> TelemetryEvent:
    """Create a sample TelemetryEvent with sensible defaults."""
    defaults = {
        "event_type": "analysis_complete",
        "source_type": "filesystem",
        "recommendation": "lift_and_shift",
        "dag_count": 5,
        "duration_seconds": 12.3,
        "error_category": None,
    }
    defaults.update(overrides)
    return TelemetryEvent(**defaults)


# ---------------------------------------------------------------------------
# event_to_payload helper
# ---------------------------------------------------------------------------


class TestEventToPayload:
    """Tests for the _event_to_payload serialization helper."""

    def test_converts_event_to_dict(self):
        event = _sample_event()
        payload = _event_to_payload(event)
        assert isinstance(payload, dict)
        assert payload["event_type"] == "analysis_complete"
        assert payload["source_type"] == "filesystem"
        assert payload["recommendation"] == "lift_and_shift"
        assert payload["dag_count"] == 5
        assert payload["duration_seconds"] == 12.3
        assert payload["error_category"] is None

    def test_includes_all_required_fields(self):
        event = _sample_event()
        payload = _event_to_payload(event)
        required = {"event_type", "source_type", "recommendation", "dag_count",
                     "duration_seconds", "error_category"}
        assert required == set(payload.keys())

    def test_none_fields_preserved(self):
        event = _sample_event(recommendation=None, error_category=None)
        payload = _event_to_payload(event)
        assert payload["recommendation"] is None
        assert payload["error_category"] is None

    def test_no_pii_fields_in_payload(self):
        """Payload must not contain credentials, URLs, env names, DAG content, or IPs."""
        event = _sample_event()
        payload = _event_to_payload(event)
        payload_str = str(payload)
        # These PII-like strings should never appear
        for pii in ["password", "secret", "token", "Bearer", "endpoint"]:
            assert pii not in payload_str


# ---------------------------------------------------------------------------
# TelemetryCollector — construction and opt-out
# ---------------------------------------------------------------------------


class TestTelemetryCollectorOptOut:
    """Tests for opt-out behavior via environment variable and constructor flag."""

    def test_enabled_by_default(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        assert collector.enabled is True

    def test_disabled_via_constructor(self):
        collector = TelemetryCollector(
            endpoint="https://telemetry.example.com", enabled=False
        )
        assert collector.enabled is False

    def test_disabled_via_env_var(self):
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: "true"}):
            collector = TelemetryCollector(endpoint="https://telemetry.example.com")
            assert collector.enabled is False

    def test_disabled_via_env_var_case_insensitive(self):
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: "True"}):
            collector = TelemetryCollector(endpoint="https://telemetry.example.com")
            assert collector.enabled is False

    def test_env_var_overrides_enabled_flag(self):
        """Even if enabled=True is passed, the env var takes precedence."""
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: "true"}):
            collector = TelemetryCollector(
                endpoint="https://telemetry.example.com", enabled=True
            )
            assert collector.enabled is False

    def test_env_var_non_true_does_not_opt_out(self):
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: "false"}):
            collector = TelemetryCollector(endpoint="https://telemetry.example.com")
            assert collector.enabled is True

    def test_env_var_empty_does_not_opt_out(self):
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: ""}):
            collector = TelemetryCollector(endpoint="https://telemetry.example.com")
            assert collector.enabled is True


# ---------------------------------------------------------------------------
# TelemetryCollector — record_event
# ---------------------------------------------------------------------------


class TestRecordEvent:
    """Tests for the record_event method."""

    def test_records_event_when_enabled(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        event = _sample_event()
        collector.record_event(event)
        assert len(collector._buffer) == 1
        assert collector._buffer[0] is event

    def test_discards_event_when_disabled(self):
        collector = TelemetryCollector(
            endpoint="https://telemetry.example.com", enabled=False
        )
        collector.record_event(_sample_event())
        assert len(collector._buffer) == 0

    def test_discards_event_when_opted_out(self):
        with patch.dict(os.environ, {_TELEMETRY_OPT_OUT_ENV: "true"}):
            collector = TelemetryCollector(endpoint="https://telemetry.example.com")
            collector.record_event(_sample_event())
            assert len(collector._buffer) == 0

    def test_buffers_multiple_events(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        for i in range(3):
            collector.record_event(_sample_event(dag_count=i))
        assert len(collector._buffer) == 3


# ---------------------------------------------------------------------------
# TelemetryCollector — flush
# ---------------------------------------------------------------------------


class TestFlush:
    """Tests for the flush method including network failure handling."""

    def test_flush_sends_buffered_events(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        collector.record_event(_sample_event())
        collector.record_event(_sample_event(event_type="analysis_error"))

        with patch("telemetry.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            collector.flush()

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://telemetry.example.com"
            payloads = call_args[1]["json"]
            assert len(payloads) == 2

    def test_flush_clears_buffer(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        collector.record_event(_sample_event())

        with patch("telemetry.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            collector.flush()
            assert len(collector._buffer) == 0

    def test_flush_noop_when_disabled(self):
        collector = TelemetryCollector(
            endpoint="https://telemetry.example.com", enabled=False
        )
        collector._buffer.append(_sample_event())  # force an event into buffer

        with patch("telemetry.httpx.Client") as mock_client_cls:
            collector.flush()
            mock_client_cls.assert_not_called()

    def test_flush_noop_when_buffer_empty(self):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")

        with patch("telemetry.httpx.Client") as mock_client_cls:
            collector.flush()
            mock_client_cls.assert_not_called()

    def test_flush_silently_discards_on_network_error(self):
        """Network failures must not raise — events are silently discarded (Req 9.5)."""
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        collector.record_event(_sample_event())

        with patch("telemetry.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            # Should not raise
            collector.flush()
            assert len(collector._buffer) == 0

    def test_flush_silently_discards_on_timeout(self):
        """Timeout errors must not raise (Req 9.5)."""
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        collector.record_event(_sample_event())

        with patch("telemetry.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.post.side_effect = httpx.TimeoutException("Timed out")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

            collector.flush()
            assert len(collector._buffer) == 0

    def test_flush_clears_buffer_on_failure(self):
        """Buffer must be cleared even when the POST fails."""
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")
        collector.record_event(_sample_event())

        with patch("telemetry.httpx.Client") as mock_client_cls:
            mock_client_cls.side_effect = Exception("Unexpected error")

            collector.flush()
            assert len(collector._buffer) == 0


# ---------------------------------------------------------------------------
# TelemetryCollector — first-run notice
# ---------------------------------------------------------------------------


class TestFirstRunNotice:
    """Tests for the show_first_run_notice method."""

    def test_shows_notice_when_marker_absent(self, tmp_path):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")

        with patch("telemetry.Path.home", return_value=tmp_path):
            with patch("builtins.print") as mock_print:
                collector.show_first_run_notice()
                mock_print.assert_called_once_with(_FIRST_RUN_NOTICE)

        # Marker file should be created
        marker = tmp_path / _MARKER_FILENAME
        assert marker.exists()

    def test_does_not_show_notice_when_marker_exists(self, tmp_path):
        marker = tmp_path / _MARKER_FILENAME
        marker.touch()

        collector = TelemetryCollector(endpoint="https://telemetry.example.com")

        with patch("telemetry.Path.home", return_value=tmp_path):
            with patch("builtins.print") as mock_print:
                collector.show_first_run_notice()
                mock_print.assert_not_called()

    def test_creates_marker_file(self, tmp_path):
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")

        with patch("telemetry.Path.home", return_value=tmp_path):
            with patch("builtins.print"):
                collector.show_first_run_notice()

        assert (tmp_path / _MARKER_FILENAME).exists()

    def test_handles_marker_creation_failure_gracefully(self, tmp_path):
        """If marker file cannot be created, notice still shows without error."""
        collector = TelemetryCollector(endpoint="https://telemetry.example.com")

        with patch("telemetry.Path.home", return_value=tmp_path):
            with patch("builtins.print") as mock_print:
                # Make the marker path's touch() raise
                with patch.object(Path, "touch", side_effect=OSError("Permission denied")):
                    # exists() returns False so notice is shown
                    with patch.object(Path, "exists", return_value=False):
                        collector.show_first_run_notice()
                        mock_print.assert_called_once_with(_FIRST_RUN_NOTICE)


# ---------------------------------------------------------------------------
# No PII in telemetry events
# ---------------------------------------------------------------------------


class TestNoPIIInTelemetry:
    """Verify that telemetry payloads do not contain PII-like data."""

    def test_payload_excludes_credentials(self):
        """Credentials should never appear in telemetry payloads."""
        event = _sample_event()
        payload = _event_to_payload(event)
        payload_str = str(payload)

        sensitive_patterns = [
            "aws_access_key_id",
            "aws_secret_access_key",
            "AKIA",  # AWS key prefix
            "Bearer",
            "password",
        ]
        for pattern in sensitive_patterns:
            assert pattern not in payload_str

    def test_payload_excludes_endpoint_urls(self):
        """Endpoint URLs should not appear in telemetry."""
        event = _sample_event()
        payload = _event_to_payload(event)
        payload_str = str(payload)

        assert "https://airflow" not in payload_str
        assert "http://" not in payload_str

    def test_payload_excludes_environment_names(self):
        """MWAA environment names should not appear in telemetry."""
        event = _sample_event()
        payload = _event_to_payload(event)
        payload_str = str(payload)

        assert "my-mwaa-env" not in payload_str

    def test_payload_excludes_dag_content(self):
        """DAG source code should not appear in telemetry."""
        event = _sample_event()
        payload = _event_to_payload(event)
        payload_str = str(payload)

        assert "from airflow.operators" not in payload_str
        assert "def dag_" not in payload_str
