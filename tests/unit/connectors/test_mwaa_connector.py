"""Unit tests for MwaaConnector.

Validates: Requirements 1.2
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from connectors.mwaa import MwaaConnector
from models import SourceType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_error(code: str, message: str = "error") -> ClientError:
    """Build a botocore ClientError with the given error code."""
    return ClientError(
        {"Error": {"Code": code, "Message": message}},
        "TestOperation",
    )


def _mock_boto3_client(
    *,
    env_details: dict | None = None,
    cli_token: str = "mock-cli-token",
    webserver_hostname: str = "abc123.us-east-1.airflow.amazonaws.com",
    get_env_error: ClientError | None = None,
    create_token_error: ClientError | None = None,
):
    """Create a mock boto3 MWAA client with canned responses."""
    mock_client = MagicMock()

    if get_env_error:
        mock_client.get_environment.side_effect = get_env_error
    else:
        mock_client.get_environment.return_value = {
            "Environment": env_details
            or {
                "Name": "test-env",
                "AirflowVersion": "2.10.3",
                "Status": "AVAILABLE",
                "WebserverUrl": webserver_hostname,
            }
        }

    if create_token_error:
        mock_client.create_cli_token.side_effect = create_token_error
    else:
        mock_client.create_cli_token.return_value = {
            "WebServerHostname": webserver_hostname,
            "CliToken": cli_token,
        }

    return mock_client


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    """Tests for MwaaConnector.connect()."""

    @patch("connectors.mwaa.boto3.client")
    def test_connect_success(self, mock_boto3_client_fn):
        mock_client = _mock_boto3_client()
        mock_boto3_client_fn.return_value = mock_client

        connector = MwaaConnector(environment_name="test-env", region="us-east-1")
        connector.connect()

        mock_client.get_environment.assert_called_once_with(Name="test-env")
        mock_client.create_cli_token.assert_called_once_with(Name="test-env")
        assert connector._api_connector is not None

    @patch("connectors.mwaa.boto3.client")
    def test_connect_resource_not_found(self, mock_boto3_client_fn):
        mock_client = _mock_boto3_client(
            get_env_error=_client_error("ResourceNotFoundException")
        )
        mock_boto3_client_fn.return_value = mock_client

        connector = MwaaConnector(environment_name="missing-env", region="us-east-1")
        with pytest.raises(ValueError, match="not found"):
            connector.connect()

    @patch("connectors.mwaa.boto3.client")
    def test_connect_access_denied(self, mock_boto3_client_fn):
        mock_client = _mock_boto3_client(
            get_env_error=_client_error("AccessDeniedException")
        )
        mock_boto3_client_fn.return_value = mock_client

        connector = MwaaConnector(environment_name="test-env", region="us-east-1")
        with pytest.raises(PermissionError, match="Access denied"):
            connector.connect()


# ---------------------------------------------------------------------------
# get_dags() delegation
# ---------------------------------------------------------------------------


class TestGetDags:
    """Tests for MwaaConnector.get_dags() delegation."""

    def test_get_dags_delegates_to_api_connector(self):
        connector = MwaaConnector(environment_name="test-env", region="us-east-1")
        mock_api = MagicMock()
        mock_api.get_dags.return_value = []
        connector._api_connector = mock_api

        result = connector.get_dags()

        mock_api.get_dags.assert_called_once()
        assert result == []

    def test_get_dags_raises_when_not_connected(self):
        connector = MwaaConnector(environment_name="test-env", region="us-east-1")
        with pytest.raises(RuntimeError, match="not connected"):
            connector.get_dags()


# ---------------------------------------------------------------------------
# get_metadata()
# ---------------------------------------------------------------------------


class TestGetMetadata:
    """Tests for MwaaConnector.get_metadata()."""

    def test_get_metadata_returns_mwaa_source_type(self):
        connector = MwaaConnector(environment_name="test-env", region="us-east-1")
        connector._environment_details = {
            "AirflowVersion": "2.10.3",
        }
        mock_api = MagicMock()
        mock_api.get_dags.return_value = []
        mock_api.get_plugins.return_value = []
        mock_api.get_configuration.return_value = {}
        connector._api_connector = mock_api

        metadata = connector.get_metadata()

        assert metadata.source_type == SourceType.MWAA
        assert metadata.airflow_version == "2.10.3"
        assert metadata.dag_count == 0
        assert metadata.plugin_count == 0
