"""MWAA-based environment connector for Amazon Managed Workflows for Apache Airflow."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from connectors.api import ApiConnector
from models import (
    DAGFile,
    EnvironmentMetadata,
    PluginFile,
    SourceType,
)

logger = logging.getLogger(__name__)


class MwaaConnector:
    """Connects to an Airflow environment managed by Amazon MWAA.

    Uses the AWS MWAA API to verify the environment, retrieve its
    configuration details, and obtain a CLI token.  The CLI token is
    then used to authenticate against the Airflow REST API (via an
    internal :class:`ApiConnector`) for DAG and metadata retrieval.

    Args:
        environment_name: The name of the MWAA environment.
        region: The AWS region where the environment is deployed.
    """

    def __init__(self, environment_name: str, region: str) -> None:
        self._environment_name = environment_name
        self._region = region
        self._api_connector: ApiConnector | None = None
        self._environment_details: dict | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Establish a connection to the MWAA environment.

        Performs the following steps:

        1. Creates a ``boto3`` MWAA client in the configured region.
        2. Calls ``GetEnvironment`` to verify the environment exists and
           retrieve its details (webserver URL, Airflow version, etc.).
        3. Calls ``CreateCliToken`` to obtain a short-lived CLI token.
        4. Initialises an internal :class:`ApiConnector` using the
           webserver URL and CLI token for subsequent REST API calls.

        Raises:
            ValueError: If the environment does not exist.
            PermissionError: If the caller lacks the required IAM
                permissions.
            RuntimeError: For any other unexpected AWS API error.
        """
        try:
            client = boto3.client("mwaa", region_name=self._region)
        except ClientError as exc:
            raise RuntimeError(
                f"Failed to create MWAA client in region {self._region}: {exc}"
            ) from exc

        # Step 1 – Verify the environment and retrieve its details.
        self._environment_details = self._get_environment(client)

        # Step 2 – Obtain a CLI token for REST API access.
        webserver_url, cli_token = self._create_cli_token(client)

        # Step 3 – Build the internal API connector.
        # The MWAA webserver URL does not include a scheme; add https://.
        if not webserver_url.startswith("https://"):
            webserver_url = f"https://{webserver_url}"

        self._api_connector = ApiConnector(
            endpoint=webserver_url,
            token=cli_token,
        )

        logger.info(
            "Successfully connected to MWAA environment '%s' in %s",
            self._environment_name,
            self._region,
        )

    # ------------------------------------------------------------------
    # Delegated data retrieval
    # ------------------------------------------------------------------

    def get_dags(self) -> list[DAGFile]:
        """Retrieve all DAG files via the Airflow REST API.

        Returns:
            A list of :class:`DAGFile` instances.

        Raises:
            RuntimeError: If :meth:`connect` has not been called.
        """
        self._ensure_connected()
        assert self._api_connector is not None
        return self._api_connector.get_dags()

    def get_requirements(self) -> str | None:
        """Retrieve requirements — delegates to the Airflow REST API.

        Returns:
            The requirements content, or ``None`` if unavailable.

        Raises:
            RuntimeError: If :meth:`connect` has not been called.
        """
        self._ensure_connected()
        assert self._api_connector is not None
        return self._api_connector.get_requirements()

    def get_configuration(self) -> dict[str, dict[str, str]]:
        """Retrieve Airflow configuration via the REST API.

        Returns:
            A nested dict of ``{section: {key: value}}``.

        Raises:
            RuntimeError: If :meth:`connect` has not been called.
        """
        self._ensure_connected()
        assert self._api_connector is not None
        return self._api_connector.get_configuration()

    def get_plugins(self) -> list[PluginFile]:
        """Retrieve plugin information via the Airflow REST API.

        Returns:
            A list of :class:`PluginFile` instances.

        Raises:
            RuntimeError: If :meth:`connect` has not been called.
        """
        self._ensure_connected()
        assert self._api_connector is not None
        return self._api_connector.get_plugins()

    def get_metadata(self) -> EnvironmentMetadata:
        """Return environment metadata sourced from the MWAA API.

        The Airflow version is taken directly from the MWAA environment
        details rather than querying the REST API, ensuring accuracy
        even when the REST API version endpoint is unavailable.

        Returns:
            An :class:`EnvironmentMetadata` populated with MWAA-sourced
            data.

        Raises:
            RuntimeError: If :meth:`connect` has not been called.
        """
        self._ensure_connected()
        assert self._api_connector is not None
        assert self._environment_details is not None

        airflow_version = self._environment_details.get("AirflowVersion")

        dags = self._api_connector.get_dags()
        plugins = self._api_connector.get_plugins()
        config = self._api_connector.get_configuration()

        return EnvironmentMetadata(
            airflow_version=airflow_version,
            source_type=SourceType.MWAA,
            dag_count=len(dags),
            plugin_count=len(plugins),
            has_requirements=False,
            has_configuration=bool(config),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        """Raise if :meth:`connect` has not been called yet."""
        if self._api_connector is None:
            raise RuntimeError(
                "MwaaConnector is not connected. Call connect() before "
                "retrieving environment data."
            )

    def _get_environment(self, client: object) -> dict:
        """Call ``GetEnvironment`` and return the environment details.

        Args:
            client: A ``boto3`` MWAA client.

        Returns:
            The ``Environment`` dict from the API response.

        Raises:
            ValueError: If the environment does not exist.
            PermissionError: If the caller lacks required permissions.
            RuntimeError: For any other AWS API error.
        """
        try:
            response = client.get_environment(Name=self._environment_name)  # type: ignore[union-attr]
            return response.get("Environment", {})
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                raise ValueError(
                    f"MWAA environment '{self._environment_name}' not found "
                    f"in region {self._region}. Please verify the environment "
                    "name and region."
                ) from exc
            if error_code in ("AccessDeniedException", "UnauthorizedAccess"):
                raise PermissionError(
                    f"Access denied when retrieving MWAA environment "
                    f"'{self._environment_name}' in region {self._region}. "
                    "Please verify your IAM permissions include "
                    "airflow:GetEnvironment."
                ) from exc
            raise RuntimeError(
                f"Failed to retrieve MWAA environment "
                f"'{self._environment_name}': {exc}"
            ) from exc

    def _create_cli_token(self, client: object) -> tuple[str, str]:
        """Call ``CreateCliToken`` and return the webserver URL and token.

        Args:
            client: A ``boto3`` MWAA client.

        Returns:
            A tuple of ``(webserver_hostname, cli_token)``.

        Raises:
            PermissionError: If the caller lacks required permissions.
            RuntimeError: For any other AWS API error.
        """
        try:
            response = client.create_cli_token(Name=self._environment_name)  # type: ignore[union-attr]
            webserver_hostname: str = response.get("WebServerHostname", "")
            cli_token: str = response.get("CliToken", "")

            if not webserver_hostname or not cli_token:
                raise RuntimeError(
                    f"MWAA CreateCliToken returned incomplete data for "
                    f"environment '{self._environment_name}'. "
                    f"WebServerHostname={'present' if webserver_hostname else 'missing'}, "
                    f"CliToken={'present' if cli_token else 'missing'}."
                )

            return webserver_hostname, cli_token
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("AccessDeniedException", "UnauthorizedAccess"):
                raise PermissionError(
                    f"Access denied when creating CLI token for MWAA "
                    f"environment '{self._environment_name}' in region "
                    f"{self._region}. Please verify your IAM permissions "
                    "include airflow:CreateCliToken."
                ) from exc
            raise RuntimeError(
                f"Failed to create CLI token for MWAA environment "
                f"'{self._environment_name}': {exc}"
            ) from exc
