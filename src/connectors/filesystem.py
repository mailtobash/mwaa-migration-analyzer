"""Filesystem-based environment connector for local Airflow projects."""

from __future__ import annotations

import configparser
from pathlib import Path

from models import (
    DAGFile,
    EnvironmentMetadata,
    PluginFile,
    SourceType,
)


class FilesystemConnector:
    """Reads Airflow environment data from a local filesystem path.

    Expects the following directory structure at the given path:
        dags/           - Python DAG files
        plugins/        - Python plugin files
        requirements.txt - Python dependencies
        airflow.cfg      - Airflow configuration
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def connect(self) -> None:
        """Validate that the root path exists and is a directory.

        Raises:
            FileNotFoundError: If the path does not exist.
            NotADirectoryError: If the path is not a directory.
        """
        if not self._path.exists():
            raise FileNotFoundError(f"Path does not exist: {self._path}")
        if not self._path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {self._path}")

    def get_dags(self) -> list[DAGFile]:
        """Read all .py files from the ``dags/`` directory.

        Returns:
            A list of :class:`DAGFile` instances. Returns an empty list if the
            ``dags/`` directory does not exist.
        """
        dags_dir = self._path / "dags"
        if not dags_dir.is_dir():
            return []

        dag_files: list[DAGFile] = []
        for py_file in sorted(dags_dir.glob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            dag_files.append(DAGFile(filename=py_file.name, content=content))
        return dag_files

    def get_requirements(self) -> str | None:
        """Read ``requirements.txt`` from the project root.

        Returns:
            The file content as a string, or ``None`` if the file does not exist.
        """
        req_path = self._path / "requirements.txt"
        if not req_path.is_file():
            return None
        return req_path.read_text(encoding="utf-8")

    def get_configuration(self) -> dict[str, dict[str, str]]:
        """Parse ``airflow.cfg`` into a nested dict structure.

        Uses :mod:`configparser` to parse the INI-style configuration file.

        Returns:
            A dict of ``{section: {key: value}}``. Returns an empty dict if
            ``airflow.cfg`` does not exist.
        """
        cfg_path = self._path / "airflow.cfg"
        if not cfg_path.is_file():
            return {}

        parser = configparser.ConfigParser()
        parser.read(str(cfg_path), encoding="utf-8")

        config: dict[str, dict[str, str]] = {}
        for section in parser.sections():
            config[section] = dict(parser.items(section))
        return config

    def get_plugins(self) -> list[PluginFile]:
        """Read all .py files from the ``plugins/`` directory.

        Returns:
            A list of :class:`PluginFile` instances. Returns an empty list if
            the ``plugins/`` directory does not exist.
        """
        plugins_dir = self._path / "plugins"
        if not plugins_dir.is_dir():
            return []

        plugin_files: list[PluginFile] = []
        for py_file in sorted(plugins_dir.glob("*.py")):
            content = py_file.read_text(encoding="utf-8")
            plugin_files.append(PluginFile(filename=py_file.name, content=content))
        return plugin_files

    def get_metadata(self) -> EnvironmentMetadata:
        """Build metadata from the current filesystem state.

        Returns:
            An :class:`EnvironmentMetadata` populated with file counts and
            source type.
        """
        dags = self.get_dags()
        plugins = self.get_plugins()
        has_requirements = (self._path / "requirements.txt").is_file()
        has_configuration = (self._path / "airflow.cfg").is_file()

        return EnvironmentMetadata(
            source_type=SourceType.FILESYSTEM,
            dag_count=len(dags),
            plugin_count=len(plugins),
            has_requirements=has_requirements,
            has_configuration=has_configuration,
        )
