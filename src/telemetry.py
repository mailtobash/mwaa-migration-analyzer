"""Telemetry Collector for anonymous usage statistics.

Collects and transmits anonymous usage events to help maintainers
understand adoption patterns and prioritize improvements.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from pathlib import Path

import httpx

from models import TelemetryEvent

logger = logging.getLogger(__name__)

_TELEMETRY_OPT_OUT_ENV = "MWAA_ANALYZER_TELEMETRY_OPT_OUT"
_MARKER_FILENAME = ".mwaa-analyzer-telemetry-notice"

_FIRST_RUN_NOTICE = """
────────────────────────────────────────────────────────────────
  MWAA Analyzer Agent — Telemetry Notice

  This tool collects anonymous usage statistics to help the
  maintainers understand adoption patterns and prioritize
  improvements. No personally identifiable information,
  credentials, DAG content, environment names, or IP addresses
  are collected.

  To opt out, set the environment variable:
    export MWAA_ANALYZER_TELEMETRY_OPT_OUT=true

────────────────────────────────────────────────────────────────
""".strip()


def _event_to_payload(event: TelemetryEvent) -> dict:
    """Convert a TelemetryEvent to the JSON payload dict for transmission.

    This function ensures only the defined TelemetryEvent fields are included
    in the payload — no PII, credentials, or environment-specific data.

    Args:
        event: The telemetry event to convert.

    Returns:
        A plain dict suitable for JSON serialization.
    """
    return asdict(event)


class TelemetryCollector:
    """Collects and transmits anonymous telemetry events.

    Checks the ``MWAA_ANALYZER_TELEMETRY_OPT_OUT`` environment variable on
    construction. When set to ``"true"`` (case-insensitive), all telemetry
    collection and transmission is disabled.

    Events are buffered internally via :meth:`record_event` and sent to the
    configured endpoint when :meth:`flush` is called. Network failures are
    silently discarded so that telemetry never disrupts the analysis workflow.
    """

    def __init__(self, endpoint: str, enabled: bool = True) -> None:
        opt_out = os.environ.get(_TELEMETRY_OPT_OUT_ENV, "").lower() == "true"
        self.endpoint = endpoint
        self.enabled = enabled and not opt_out
        self._buffer: list[TelemetryEvent] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_event(self, event: TelemetryEvent) -> None:
        """Record a telemetry event to the internal buffer.

        If telemetry is disabled (via constructor flag or environment variable),
        the event is silently discarded.

        Args:
            event: The telemetry event to record.
        """
        if not self.enabled:
            return
        self._buffer.append(event)

    def flush(self) -> None:
        """Send all buffered events to the telemetry endpoint via HTTPS POST.

        On any network or HTTP error the events are silently discarded and
        normal operation continues. The buffer is cleared after a flush
        attempt regardless of success or failure.
        """
        if not self.enabled or not self._buffer:
            return

        payloads = [_event_to_payload(e) for e in self._buffer]
        self._buffer.clear()

        try:
            with httpx.Client(timeout=10.0) as client:
                client.post(self.endpoint, json=payloads)
        except Exception:  # noqa: BLE001
            # Silently discard on any failure (Requirement 9.5)
            logger.debug("Telemetry flush failed; events discarded")

    def show_first_run_notice(self) -> None:
        """Display a first-run telemetry notice if not previously shown.

        Creates a marker file ``~/.mwaa-analyzer-telemetry-notice`` after
        displaying the notice so it is only shown once per user.
        """
        marker_path = Path.home() / _MARKER_FILENAME
        if marker_path.exists():
            return

        print(_FIRST_RUN_NOTICE)  # noqa: T201

        try:
            marker_path.touch()
        except OSError:
            # If we cannot create the marker, the notice will show again
            # next time — acceptable degradation.
            logger.debug("Could not create telemetry notice marker file")
