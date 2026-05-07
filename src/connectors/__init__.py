"""Environment connectors for retrieving Airflow environment data."""

from __future__ import annotations

from typing import Protocol

from models import (
    DAGFile,
    EnvironmentMetadata,
    PluginFile,
    SourceType,
)


class EnvironmentConnector(Protocol):
    """Protocol defining the interface for environment connectors.

    Each connector implementation retrieves Airflow environment data
    from a specific source type (API, MWAA, or local filesystem).
    """

    def connect(self) -> None:
        """Establish a connection to the Airflow environment."""
        ...

    def get_dags(self) -> list[DAGFile]:
        """Retrieve all DAG files from the environment."""
        ...

    def get_requirements(self) -> str | None:
        """Retrieve the requirements.txt content, or None if not available."""
        ...

    def get_configuration(self) -> dict[str, dict[str, str]]:
        """Retrieve Airflow configuration as a nested dict of {section: {key: value}}."""
        ...

    def get_plugins(self) -> list[PluginFile]:
        """Retrieve all plugin files from the environment."""
        ...

    def get_metadata(self) -> EnvironmentMetadata:
        """Retrieve metadata about the Airflow environment."""
        ...


def create_connector(source_type: SourceType, **kwargs: object) -> EnvironmentConnector:
    """Create and return the appropriate connector for the given source type.

    Uses lazy imports to avoid circular dependencies.

    Args:
        source_type: The type of source environment to connect to.
        **kwargs: Connector-specific keyword arguments.
            - For SourceType.FILESYSTEM: path (str) - local filesystem path.
            - For SourceType.API: endpoint (str) - Airflow REST API URL,
              token (str) - authentication token.
            - For SourceType.MWAA: environment_name (str) - MWAA environment name,
              region (str) - AWS region.

    Returns:
        An EnvironmentConnector instance for the specified source type.

    Raises:
        ValueError: If the source type is not recognized.
    """
    if source_type == SourceType.FILESYSTEM:
        from connectors.filesystem import FilesystemConnector

        return FilesystemConnector(path=kwargs["path"])  # type: ignore[arg-type]

    if source_type == SourceType.API:
        from connectors.api import ApiConnector

        return ApiConnector(endpoint=kwargs["endpoint"], token=kwargs["token"])  # type: ignore[arg-type]

    if source_type == SourceType.MWAA:
        from connectors.mwaa import MwaaConnector

        return MwaaConnector(
            environment_name=kwargs["environment_name"],  # type: ignore[arg-type]
            region=kwargs["region"],  # type: ignore[arg-type]
        )

    raise ValueError(f"Unknown source type: {source_type}")
