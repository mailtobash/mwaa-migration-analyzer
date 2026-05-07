"""REST API-based environment connector for Airflow instances."""

from __future__ import annotations

import logging

import httpx

from models import (
    DAGFile,
    EnvironmentMetadata,
    PluginFile,
    SourceType,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0  # seconds


class ApiConnector:
    """Connects to an Airflow environment via the REST API.

    Supports both Airflow 2.x (``/api/v1``) and 3.x (``/api/v2``) endpoints.
    The connector tries the 3.x endpoint first and falls back to 2.x when
    the newer endpoint is not available.

    Args:
        endpoint: Base URL of the Airflow webserver (e.g. ``https://airflow.example.com``).
        token: Bearer token used for authentication.
    """

    def __init__(self, endpoint: str, token: str) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._token = token
        self._client = httpx.Client(
            base_url=self._endpoint,
            headers={"Authorization": f"Bearer {token}"},
            timeout=httpx.Timeout(_TIMEOUT),
        )
        self._airflow_version: str | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Test the connection by hitting the health endpoint.

        Tries ``/api/v2/monitor/health`` first, then ``/api/v1/health``.

        Raises:
            ConnectionError: If authentication fails (HTTP 401/403).
            TimeoutError: If the endpoint does not respond within 30 seconds.
            RuntimeError: For any other unexpected HTTP error.
        """
        try:
            response = self._try_health()
            data = response.json()
            # Airflow health response may include a "metadatabase" or
            # "metadata_database" key depending on version.
            logger.info("Successfully connected to Airflow at %s", self._endpoint)
            logger.debug("Health response: %s", data)
        except httpx.ConnectTimeout:
            raise TimeoutError(
                f"Connection to {self._endpoint} timed out after {_TIMEOUT:.0f} seconds. "
                "Please verify network connectivity and the endpoint URL."
            )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (401, 403):
                raise ConnectionError(
                    f"Authentication failed (HTTP {status}) when connecting to "
                    f"{self._endpoint}. Please verify your bearer token is valid "
                    "and has the required permissions."
                ) from exc
            raise RuntimeError(
                f"Unexpected HTTP {status} from {self._endpoint}: {exc.response.text}"
            ) from exc

    # ------------------------------------------------------------------
    # DAGs
    # ------------------------------------------------------------------

    def get_dags(self) -> list[DAGFile]:
        """Retrieve all DAG files via the REST API.

        Fetches the DAG list and then attempts to retrieve the source code
        for each DAG using the ``dag_sources`` endpoint.

        Returns:
            A list of :class:`DAGFile` instances with filename and content.
        """
        dags_data = self._get_with_fallback("/api/v2/dags", "/api/v1/dags")
        if dags_data is None:
            return []

        dag_list = dags_data.get("dags", [])
        dag_files: list[DAGFile] = []

        for dag in dag_list:
            dag_id: str = dag.get("dag_id", "unknown")
            file_token: str | None = dag.get("file_token")
            filename: str = dag.get("fileloc", dag_id)
            # Use just the basename for the filename.
            if "/" in filename:
                filename = filename.rsplit("/", 1)[-1]

            content = ""
            if file_token:
                content = self._get_dag_source(file_token)

            dag_files.append(DAGFile(filename=filename, content=content))

        return dag_files

    # ------------------------------------------------------------------
    # Requirements
    # ------------------------------------------------------------------

    def get_requirements(self) -> str | None:
        """Return ``None`` — requirements are not available via the REST API."""
        return None

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def get_configuration(self) -> dict[str, dict[str, str]]:
        """Retrieve Airflow configuration via the REST API.

        Returns:
            A nested dict of ``{section: {key: value}}``.
            Returns an empty dict if the endpoint returns 403 (config
            exposure disabled).
        """
        try:
            data = self._get_with_fallback("/api/v2/config", "/api/v1/config")
        except ConnectionError:
            # 403 means config exposure is disabled — return empty.
            return {}

        if data is None:
            return {}

        return self._parse_config_response(data)

    # ------------------------------------------------------------------
    # Plugins
    # ------------------------------------------------------------------

    def get_plugins(self) -> list[PluginFile]:
        """Retrieve plugin information via the REST API.

        The API exposes plugin metadata but not full source code, so the
        returned :class:`PluginFile` instances have limited content.

        Returns:
            A list of :class:`PluginFile` instances.
        """
        data = self._get_with_fallback("/api/v2/plugins", "/api/v1/plugins")
        if data is None:
            return []

        plugins = data.get("plugins", [])
        plugin_files: list[PluginFile] = []
        for plugin in plugins:
            name: str = plugin.get("name", "unknown")
            # Build a summary from available metadata since the API does
            # not expose full plugin source code.
            hooks = plugin.get("hooks", [])
            executors = plugin.get("executors", [])
            macros = plugin.get("macros", [])
            flask_blueprints = plugin.get("flask_blueprints", [])
            appbuilder_views = plugin.get("appbuilder_views", [])

            content_lines = [f"# Plugin: {name}"]
            if hooks:
                content_lines.append(f"# Hooks: {', '.join(str(h) for h in hooks)}")
            if executors:
                content_lines.append(f"# Executors: {', '.join(str(e) for e in executors)}")
            if macros:
                content_lines.append(f"# Macros: {', '.join(str(m) for m in macros)}")
            if flask_blueprints:
                content_lines.append(f"# Flask Blueprints: {len(flask_blueprints)}")
            if appbuilder_views:
                content_lines.append(f"# AppBuilder Views: {len(appbuilder_views)}")

            plugin_files.append(
                PluginFile(filename=f"{name}.py", content="\n".join(content_lines))
            )

        return plugin_files

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self) -> EnvironmentMetadata:
        """Retrieve environment metadata from the API.

        Fetches the Airflow version from the ``version`` endpoint and
        counts DAGs and plugins.

        Returns:
            An :class:`EnvironmentMetadata` populated with API-sourced data.
        """
        version = self._get_airflow_version()
        dags = self.get_dags()
        plugins = self.get_plugins()
        config = self.get_configuration()

        return EnvironmentMetadata(
            airflow_version=version,
            source_type=SourceType.API,
            dag_count=len(dags),
            plugin_count=len(plugins),
            has_requirements=False,
            has_configuration=bool(config),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_health(self) -> httpx.Response:
        """Hit the health endpoint, trying v2 first then v1.

        Returns:
            The successful :class:`httpx.Response`.

        Raises:
            httpx.ConnectTimeout: On connection timeout.
            httpx.HTTPStatusError: On non-2xx responses.
        """
        try:
            response = self._client.get("/api/v2/monitor/health")
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                # v2 not available — try v1.
                response = self._client.get("/api/v1/health")
                response.raise_for_status()
                return response
            raise

    def _get_with_fallback(
        self, v2_path: str, v1_path: str
    ) -> dict | None:
        """GET a JSON endpoint, trying the v2 path first then v1.

        Args:
            v2_path: Airflow 3.x API path.
            v1_path: Airflow 2.x API path.

        Returns:
            Parsed JSON as a dict, or ``None`` if both endpoints return 404.

        Raises:
            ConnectionError: On 401/403 responses.
            TimeoutError: On connection timeout.
            RuntimeError: On other HTTP errors.
        """
        for path in (v2_path, v1_path):
            try:
                response = self._client.get(path)
                response.raise_for_status()
                return response.json()
            except httpx.ConnectTimeout:
                raise TimeoutError(
                    f"Connection to {self._endpoint} timed out after "
                    f"{_TIMEOUT:.0f} seconds. Please verify network connectivity "
                    "and the endpoint URL."
                )
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 404 and path == v2_path:
                    # v2 not available — fall through to v1.
                    continue
                if status in (401, 403):
                    raise ConnectionError(
                        f"Authentication failed (HTTP {status}) when accessing "
                        f"{self._endpoint}{path}. Please verify your bearer token "
                        "is valid and has the required permissions."
                    ) from exc
                if status == 404:
                    # Both v2 and v1 returned 404.
                    return None
                raise RuntimeError(
                    f"Unexpected HTTP {status} from {self._endpoint}{path}: "
                    f"{exc.response.text}"
                ) from exc
        return None

    def _get_dag_source(self, file_token: str) -> str:
        """Retrieve DAG source code using the file token.

        Tries ``/api/v2/dagSources/{file_token}`` first, then
        ``/api/v1/dagSources/{file_token}``.

        Args:
            file_token: The file token from the DAG list response.

        Returns:
            The DAG source code as a string, or an empty string on failure.
        """
        for prefix in ("/api/v2", "/api/v1"):
            path = f"{prefix}/dagSources/{file_token}"
            try:
                response = self._client.get(path)
                response.raise_for_status()
                # The dagSources endpoint returns plain text.
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    data = response.json()
                    return data.get("content", response.text)
                return response.text
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404 and prefix == "/api/v2":
                    continue
                logger.warning(
                    "Failed to retrieve source for file_token=%s: HTTP %d",
                    file_token,
                    exc.response.status_code,
                )
                return ""
            except httpx.ConnectTimeout:
                logger.warning(
                    "Timeout retrieving source for file_token=%s", file_token
                )
                return ""
        return ""

    def _get_airflow_version(self) -> str | None:
        """Retrieve the Airflow version from the version endpoint.

        Returns:
            The version string, or ``None`` if it cannot be determined.
        """
        if self._airflow_version is not None:
            return self._airflow_version

        for path in ("/api/v2/version", "/api/v1/version"):
            try:
                response = self._client.get(path)
                response.raise_for_status()
                data = response.json()
                self._airflow_version = data.get("version")
                return self._airflow_version
            except (httpx.HTTPStatusError, httpx.ConnectTimeout):
                continue

        return None

    @staticmethod
    def _parse_config_response(data: dict) -> dict[str, dict[str, str]]:
        """Parse the Airflow config API response into a nested dict.

        The API returns config in the format::

            {"sections": [{"name": "core", "options": [{"key": "k", "value": "v"}]}]}

        Args:
            data: Raw JSON response from the config endpoint.

        Returns:
            A dict of ``{section: {key: value}}``.
        """
        config: dict[str, dict[str, str]] = {}
        sections = data.get("sections", [])
        for section in sections:
            section_name = section.get("name", "")
            options = section.get("options", [])
            section_dict: dict[str, str] = {}
            for option in options:
                key = option.get("key", "")
                value = option.get("value", "")
                if key:
                    section_dict[key] = value
            if section_name:
                config[section_name] = section_dict
        return config
