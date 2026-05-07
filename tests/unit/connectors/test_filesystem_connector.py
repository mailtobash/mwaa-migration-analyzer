"""Unit tests for FilesystemConnector.

Validates: Requirements 1.3
"""

from __future__ import annotations

import pytest

from connectors.filesystem import FilesystemConnector
from models import SourceType


class TestConnect:
    """Tests for FilesystemConnector.connect()."""

    def test_connect_valid_directory(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        connector.connect()  # Should not raise

    def test_connect_nonexistent_path(self, tmp_path):
        connector = FilesystemConnector(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError, match="Path does not exist"):
            connector.connect()

    def test_connect_file_instead_of_directory(self, tmp_path):
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("hello")
        connector = FilesystemConnector(file_path)
        with pytest.raises(NotADirectoryError, match="Path is not a directory"):
            connector.connect()


class TestGetDags:
    """Tests for FilesystemConnector.get_dags()."""

    def test_get_dags_with_py_files(self, tmp_path):
        dags_dir = tmp_path / "dags"
        dags_dir.mkdir()
        (dags_dir / "dag_a.py").write_text("# DAG A")
        (dags_dir / "dag_b.py").write_text("# DAG B")
        # Non-py file should be ignored
        (dags_dir / "readme.txt").write_text("not a dag")

        connector = FilesystemConnector(tmp_path)
        dags = connector.get_dags()

        assert len(dags) == 2
        assert dags[0].filename == "dag_a.py"
        assert dags[0].content == "# DAG A"
        assert dags[1].filename == "dag_b.py"
        assert dags[1].content == "# DAG B"

    def test_get_dags_empty_directory(self, tmp_path):
        dags_dir = tmp_path / "dags"
        dags_dir.mkdir()

        connector = FilesystemConnector(tmp_path)
        dags = connector.get_dags()

        assert dags == []

    def test_get_dags_missing_directory(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        dags = connector.get_dags()

        assert dags == []


class TestGetRequirements:
    """Tests for FilesystemConnector.get_requirements()."""

    def test_get_requirements_existing_file(self, tmp_path):
        req_content = "boto3==1.34.0\nrequests>=2.31"
        (tmp_path / "requirements.txt").write_text(req_content)

        connector = FilesystemConnector(tmp_path)
        result = connector.get_requirements()

        assert result == req_content

    def test_get_requirements_missing_file(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        result = connector.get_requirements()

        assert result is None


class TestGetConfiguration:
    """Tests for FilesystemConnector.get_configuration()."""

    def test_get_configuration_valid_cfg(self, tmp_path):
        cfg_content = "[core]\nexecutor = LocalExecutor\n\n[webserver]\nweb_server_port = 8080\n"
        (tmp_path / "airflow.cfg").write_text(cfg_content)

        connector = FilesystemConnector(tmp_path)
        config = connector.get_configuration()

        assert "core" in config
        assert config["core"]["executor"] == "LocalExecutor"
        assert "webserver" in config
        assert config["webserver"]["web_server_port"] == "8080"

    def test_get_configuration_missing_file(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        config = connector.get_configuration()

        assert config == {}


class TestGetPlugins:
    """Tests for FilesystemConnector.get_plugins()."""

    def test_get_plugins_with_py_files(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        (plugins_dir / "my_plugin.py").write_text("# plugin code")
        (plugins_dir / "another.py").write_text("# another plugin")

        connector = FilesystemConnector(tmp_path)
        plugins = connector.get_plugins()

        assert len(plugins) == 2
        assert plugins[0].filename == "another.py"
        assert plugins[1].filename == "my_plugin.py"

    def test_get_plugins_missing_directory(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        plugins = connector.get_plugins()

        assert plugins == []


class TestGetMetadata:
    """Tests for FilesystemConnector.get_metadata()."""

    def test_get_metadata_full_project(self, tmp_path):
        # Set up a complete project structure
        (tmp_path / "dags").mkdir()
        (tmp_path / "dags" / "dag1.py").write_text("# dag")
        (tmp_path / "dags" / "dag2.py").write_text("# dag")
        (tmp_path / "plugins").mkdir()
        (tmp_path / "plugins" / "plug.py").write_text("# plug")
        (tmp_path / "requirements.txt").write_text("boto3")
        (tmp_path / "airflow.cfg").write_text("[core]\nexecutor = Local\n")

        connector = FilesystemConnector(tmp_path)
        metadata = connector.get_metadata()

        assert metadata.source_type == SourceType.FILESYSTEM
        assert metadata.dag_count == 2
        assert metadata.plugin_count == 1
        assert metadata.has_requirements is True
        assert metadata.has_configuration is True

    def test_get_metadata_empty_project(self, tmp_path):
        connector = FilesystemConnector(tmp_path)
        metadata = connector.get_metadata()

        assert metadata.source_type == SourceType.FILESYSTEM
        assert metadata.dag_count == 0
        assert metadata.plugin_count == 0
        assert metadata.has_requirements is False
        assert metadata.has_configuration is False
