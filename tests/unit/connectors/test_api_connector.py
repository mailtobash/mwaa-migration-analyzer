"""Unit tests for ApiConnector.

Validates: Requirements 1.1, 1.4, 1.5
"""

from __future__ import annotations

import httpx
import pytest

from connectors.api import ApiConnector
from models import SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transport(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    """Build a MockTransport that returns canned responses by path."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.raw_path.decode()
        if path in routes:
            return routes[path]
        return httpx.Response(status_code=404, json={"detail": "Not found"})

    return httpx.MockTransport(handler)


def _connector_with_transport(transport: httpx.MockTransport) -> ApiConnector:
    """Create an ApiConnector and swap its internal client transport."""
    connector = ApiConnector(endpoint="https://airflow.example.com", token="test-token")
    connector._client = httpx.Client(
        base_url="https://airflow.example.com",
        headers={"Authorization": "Bearer test-token"},
        transport=transport,
    )
    return connector


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for ApiConnector.connect()."""

    def test_connect_success_v2(self):
        transport = _make_transport(
            {
                "/api/v2/monitor/health": httpx.Response(
                    200, json={"metadatabase": {"status": "healthy"}}
                ),
            }
        )
        connector = _connector_with_transport(transport)
        connector.connect()  # Should not raise

    def test_connect_success_v1_fallback(self):
        transport = _make_transport(
            {
                "/api/v1/health": httpx.Response(
                    200, json={"metadatabase": {"status": "healthy"}}
                ),
            }
        )
        connector = _connector_with_transport(transport)
        connector.connect()  # Should not raise (falls back to v1)

    def test_connect_auth_failure_401(self):
        transport = _make_transport(
            {
                "/api/v2/monitor/health": httpx.Response(401, json={"detail": "Unauthorized"}),
            }
        )
        connector = _connector_with_transport(transport)
        with pytest.raises(ConnectionError, match="Authentication failed.*401"):
            connector.connect()

    def test_connect_auth_failure_403(self):
        transport = _make_transport(
            {
                "/api/v2/monitor/health": httpx.Response(403, json={"detail": "Forbidden"}),
            }
        )
        connector = _connector_with_transport(transport)
        with pytest.raises(ConnectionError, match="Authentication failed.*403"):
            connector.connect()

    def test_connect_timeout(self):
        def timeout_handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("Connection timed out")

        transport = httpx.MockTransport(timeout_handler)
        connector = _connector_with_transport(transport)
        with pytest.raises(TimeoutError, match="timed out"):
            connector.connect()


# ---------------------------------------------------------------------------
# get_dags()
# ---------------------------------------------------------------------------


class TestGetDags:
    """Tests for ApiConnector.get_dags()."""

    def test_get_dags_with_results(self):
        transport = _make_transport(
            {
                "/api/v2/dags": httpx.Response(
                    200,
                    json={
                        "dags": [
                            {
                                "dag_id": "example_dag",
                                "fileloc": "/opt/airflow/dags/example_dag.py",
                                "file_token": "abc123",
                            },
                        ]
                    },
                ),
                "/api/v2/dagSources/abc123": httpx.Response(
                    200,
                    text="# example dag content",
                    headers={"content-type": "text/plain"},
                ),
            }
        )
        connector = _connector_with_transport(transport)
        dags = connector.get_dags()

        assert len(dags) == 1
        assert dags[0].filename == "example_dag.py"
        assert dags[0].content == "# example dag content"

    def test_get_dags_empty(self):
        transport = _make_transport(
            {
                "/api/v2/dags": httpx.Response(200, json={"dags": []}),
            }
        )
        connector = _connector_with_transport(transport)
        dags = connector.get_dags()

        assert dags == []

    def test_get_dags_both_endpoints_404(self):
        """When both v2 and v1 return 404, get_dags returns empty list."""
        transport = _make_transport({})  # No routes → all 404
        connector = _connector_with_transport(transport)
        dags = connector.get_dags()

        assert dags == []


# ---------------------------------------------------------------------------
# get_configuration()
# ---------------------------------------------------------------------------


class TestGetConfiguration:
    """Tests for ApiConnector.get_configuration()."""

    def test_get_configuration_success(self):
        transport = _make_transport(
            {
                "/api/v2/config": httpx.Response(
                    200,
                    json={
                        "sections": [
                            {
                                "name": "core",
                                "options": [
                                    {"key": "executor", "value": "CeleryExecutor"},
                                ],
                            }
                        ]
                    },
                ),
            }
        )
        connector = _connector_with_transport(transport)
        config = connector.get_configuration()

        assert config == {"core": {"executor": "CeleryExecutor"}}

    def test_get_configuration_403_returns_empty(self):
        transport = _make_transport(
            {
                "/api/v2/config": httpx.Response(403, json={"detail": "Forbidden"}),
            }
        )
        connector = _connector_with_transport(transport)
        config = connector.get_configuration()

        assert config == {}


# ---------------------------------------------------------------------------
# get_plugins()
# ---------------------------------------------------------------------------


class TestGetPlugins:
    """Tests for ApiConnector.get_plugins()."""

    def test_get_plugins_success(self):
        transport = _make_transport(
            {
                "/api/v2/plugins": httpx.Response(
                    200,
                    json={
                        "plugins": [
                            {
                                "name": "my_plugin",
                                "hooks": ["MyHook"],
                                "executors": [],
                                "macros": [],
                                "flask_blueprints": [],
                                "appbuilder_views": [],
                            }
                        ]
                    },
                ),
            }
        )
        connector = _connector_with_transport(transport)
        plugins = connector.get_plugins()

        assert len(plugins) == 1
        assert plugins[0].filename == "my_plugin.py"
        assert "my_plugin" in plugins[0].content

    def test_get_plugins_empty(self):
        transport = _make_transport(
            {
                "/api/v2/plugins": httpx.Response(200, json={"plugins": []}),
            }
        )
        connector = _connector_with_transport(transport)
        plugins = connector.get_plugins()

        assert plugins == []


# ---------------------------------------------------------------------------
# get_metadata()
# ---------------------------------------------------------------------------


class TestGetMetadata:
    """Tests for ApiConnector.get_metadata()."""

    def test_get_metadata_returns_api_source_type(self):
        transport = _make_transport(
            {
                "/api/v2/version": httpx.Response(200, json={"version": "2.10.3"}),
                "/api/v2/dags": httpx.Response(200, json={"dags": []}),
                "/api/v2/plugins": httpx.Response(200, json={"plugins": []}),
                "/api/v2/config": httpx.Response(200, json={"sections": []}),
            }
        )
        connector = _connector_with_transport(transport)
        metadata = connector.get_metadata()

        assert metadata.source_type == SourceType.API
        assert metadata.airflow_version == "2.10.3"
        assert metadata.dag_count == 0
        assert metadata.plugin_count == 0
