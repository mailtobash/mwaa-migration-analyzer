"""Unit tests for the MWAA version manifest loader.

Validates: Requirements 2.6, 3.5, 4.4, 5.4
"""

import pytest

from data_loader import load_manifest
from models import MWAAVersionManifest


class TestLoadManifestValid:
    """Tests for loading a valid manifest (version 2.10.3)."""

    def test_returns_manifest_instance(self):
        manifest = load_manifest("2.10.3")
        assert isinstance(manifest, MWAAVersionManifest)

    def test_airflow_version(self):
        manifest = load_manifest("2.10.3")
        assert manifest.airflow_version == "2.10.3"

    def test_pre_installed_packages_is_dict(self):
        manifest = load_manifest("2.10.3")
        assert isinstance(manifest.pre_installed_packages, dict)
        assert len(manifest.pre_installed_packages) > 0

    def test_pre_installed_packages_contains_known_package(self):
        manifest = load_manifest("2.10.3")
        assert "boto3" in manifest.pre_installed_packages
        assert "apache-airflow" in manifest.pre_installed_packages

    def test_supported_config_keys_is_set(self):
        manifest = load_manifest("2.10.3")
        assert isinstance(manifest.supported_config_keys, set)
        assert len(manifest.supported_config_keys) > 0

    def test_supported_config_keys_contains_known_key(self):
        manifest = load_manifest("2.10.3")
        assert "core.executor" in manifest.supported_config_keys

    def test_supported_operators_is_set(self):
        manifest = load_manifest("2.10.3")
        assert isinstance(manifest.supported_operators, set)
        assert len(manifest.supported_operators) > 0

    def test_supported_operators_contains_known_operator(self):
        manifest = load_manifest("2.10.3")
        assert "airflow.operators.python.PythonOperator" in manifest.supported_operators

    def test_known_incompatible_packages_is_set(self):
        manifest = load_manifest("2.10.3")
        assert isinstance(manifest.known_incompatible_packages, set)
        assert len(manifest.known_incompatible_packages) > 0

    def test_known_incompatible_packages_contains_known_entry(self):
        manifest = load_manifest("2.10.3")
        assert "pyodbc" in manifest.known_incompatible_packages


class TestLoadManifestInvalid:
    """Tests for loading a manifest with an unsupported version."""

    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported MWAA version"):
            load_manifest("99.99.99")

    def test_error_message_includes_version(self):
        with pytest.raises(ValueError, match="99.99.99"):
            load_manifest("99.99.99")

    def test_error_message_lists_available_versions(self):
        with pytest.raises(ValueError, match="Available versions"):
            load_manifest("0.0.0")
