"""Unit tests for the Configuration Analyzer tool.

Tests configuration key compatibility, filesystem path detection,
and individual helper functions.

Requirements: 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

import pytest

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.configuration_analyzer import (
    analyze_configuration,
    classify_config_entry,
    _is_filesystem_path,
)
from data_loader import load_manifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def manifest():
    """Load the 2.10.3 MWAA version manifest."""
    return load_manifest("2.10.3")


@pytest.fixture
def supported_keys(manifest):
    """Get the supported config keys from the manifest."""
    return manifest.supported_config_keys


# ---------------------------------------------------------------------------
# Helper: _is_filesystem_path
# ---------------------------------------------------------------------------


class TestIsFilesystemPath:
    """Tests for the _is_filesystem_path helper function."""

    def test_unix_absolute_path(self):
        assert _is_filesystem_path("/var/log/airflow") is True

    def test_unix_relative_dot_slash(self):
        assert _is_filesystem_path("./dags/my_dag.py") is True

    def test_unix_relative_dot_dot_slash(self):
        assert _is_filesystem_path("../config/settings.cfg") is True

    def test_windows_drive_letter_backslash(self):
        assert _is_filesystem_path("C:\\Users\\airflow\\dags") is True

    def test_windows_drive_letter_forward_slash(self):
        assert _is_filesystem_path("D:/airflow/dags") is True

    def test_plain_string_value(self):
        assert _is_filesystem_path("True") is False

    def test_numeric_value(self):
        assert _is_filesystem_path("32") is False

    def test_s3_path(self):
        assert _is_filesystem_path("s3://my-bucket/logs") is False

    def test_url_value(self):
        assert _is_filesystem_path("https://example.com") is False

    def test_empty_string(self):
        assert _is_filesystem_path("") is False

    def test_whitespace_before_path(self):
        assert _is_filesystem_path("  /tmp/airflow") is True


# ---------------------------------------------------------------------------
# Supported configuration keys
# ---------------------------------------------------------------------------


class TestSupportedConfigKeys:
    """Test analyze_configuration with supported configuration keys."""

    def test_core_parallelism(self):
        """core.parallelism is a supported MWAA config key."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"parallelism": "32"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value
        assert findings[0]["issues"] == []

    def test_scheduler_min_file_process_interval(self):
        """scheduler.min_file_process_interval is supported."""
        result = analyze_configuration._tool_func(
            config_entries={"scheduler": {"min_file_process_interval": "60"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_celery_worker_concurrency(self):
        """celery.worker_concurrency is supported."""
        result = analyze_configuration._tool_func(
            config_entries={"celery": {"worker_concurrency": "16"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.COMPATIBLE.value

    def test_compatible_no_effort(self):
        """Compatible config entries should have no effort level."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"parallelism": "32"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] is None

    def test_finding_has_configuration_category(self):
        """All findings should have the configuration category."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"parallelism": "32"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["category"] == FindingCategory.CONFIGURATION.value


# ---------------------------------------------------------------------------
# Unsupported configuration keys
# ---------------------------------------------------------------------------


class TestUnsupportedConfigKeys:
    """Test analyze_configuration with unsupported configuration keys."""

    def test_webserver_workers(self):
        """webserver.workers is not in the supported keys list."""
        result = analyze_configuration._tool_func(
            config_entries={"webserver": {"workers": "4"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.UNSUPPORTED.value
        assert len(findings[0]["issues"]) > 0

    def test_unknown_section_key(self):
        """A completely unknown section.key should be unsupported."""
        result = analyze_configuration._tool_func(
            config_entries={"custom_section": {"custom_key": "value"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.UNSUPPORTED.value

    def test_unsupported_has_recommendations(self):
        """Unsupported config entries should include recommendations."""
        result = analyze_configuration._tool_func(
            config_entries={"webserver": {"workers": "4"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0

    def test_unsupported_low_effort(self):
        """Unsupported config entries should have LOW effort."""
        result = analyze_configuration._tool_func(
            config_entries={"webserver": {"workers": "4"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "low"


# ---------------------------------------------------------------------------
# Filesystem path detection in values
# ---------------------------------------------------------------------------


class TestFilesystemPathDetection:
    """Test analyze_configuration with filesystem paths in values."""

    def test_unix_absolute_path_in_value(self):
        """A supported key with a Unix absolute path value should require modification."""
        result = analyze_configuration._tool_func(
            config_entries={"logging": {"remote_base_log_folder": "/var/log/airflow"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value
        assert any("filesystem path" in issue for issue in findings[0]["issues"])

    def test_relative_path_in_value(self):
        """A supported key with a relative path value should require modification."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"dags_folder": "./dags"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value

    def test_windows_path_in_value(self):
        """A supported key with a Windows path value should require modification."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"dags_folder": "C:\\airflow\\dags"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value

    def test_path_detection_medium_effort(self):
        """Filesystem path findings should have MEDIUM effort."""
        result = analyze_configuration._tool_func(
            config_entries={"logging": {"remote_base_log_folder": "/var/log/airflow"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert findings[0]["effort"] == "medium"

    def test_path_detection_has_recommendations(self):
        """Filesystem path findings should include recommendations."""
        result = analyze_configuration._tool_func(
            config_entries={"logging": {"remote_base_log_folder": "/var/log/airflow"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings[0]["recommendations"]) > 0


# ---------------------------------------------------------------------------
# Unsupported key takes precedence over path detection
# ---------------------------------------------------------------------------


class TestUnsupportedKeyPrecedence:
    """Test that unsupported keys are flagged as unsupported even if value has a path."""

    def test_unsupported_key_with_path_value(self):
        """An unsupported key with a filesystem path value should be UNSUPPORTED."""
        result = analyze_configuration._tool_func(
            config_entries={"custom_section": {"log_dir": "/var/log/custom"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1
        assert findings[0]["status"] == CompatibilityStatus.UNSUPPORTED.value


# ---------------------------------------------------------------------------
# Empty and edge case inputs
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test analyze_configuration with edge cases."""

    def test_empty_config(self):
        """Empty config_entries should produce no findings."""
        result = analyze_configuration._tool_func(
            config_entries={},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_empty_section(self):
        """A section with no keys should produce no findings."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 0

    def test_non_dict_section_skipped(self):
        """A non-dict section value should be skipped gracefully."""
        result = analyze_configuration._tool_func(
            config_entries={"core": "not_a_dict"},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Multiple configuration entries
# ---------------------------------------------------------------------------


class TestMultipleEntries:
    """Test analyze_configuration with multiple configuration entries."""

    def test_mixed_statuses(self):
        """Config with mixed statuses should produce correct findings."""
        config = {
            "core": {
                "parallelism": "32",
                "dags_folder": "/opt/airflow/dags",
            },
            "webserver": {
                "workers": "4",
            },
        }
        result = analyze_configuration._tool_func(
            config_entries=config,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 3

        statuses = [f["status"] for f in findings]
        assert CompatibilityStatus.COMPATIBLE.value in statuses
        assert CompatibilityStatus.REQUIRES_MODIFICATION.value in statuses
        assert CompatibilityStatus.UNSUPPORTED.value in statuses

    def test_all_supported(self):
        """All supported keys with normal values should be compatible."""
        config = {
            "core": {
                "parallelism": "32",
                "load_examples": "False",
            },
            "scheduler": {
                "min_file_process_interval": "60",
            },
        }
        result = analyze_configuration._tool_func(
            config_entries=config,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 3
        assert all(
            f["status"] == CompatibilityStatus.COMPATIBLE.value
            for f in findings
        )

    def test_multiple_sections(self):
        """Entries from multiple sections should all be analyzed."""
        config = {
            "core": {"parallelism": "32"},
            "scheduler": {"min_file_process_interval": "60"},
            "celery": {"worker_concurrency": "16"},
            "logging": {"logging_level": "INFO"},
        }
        result = analyze_configuration._tool_func(
            config_entries=config,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 4


# ---------------------------------------------------------------------------
# Identifier format
# ---------------------------------------------------------------------------


class TestIdentifierFormat:
    """Test that finding identifiers include section, key, and value."""

    def test_identifier_contains_section_and_key(self):
        """The identifier should contain the section.key = value format."""
        result = analyze_configuration._tool_func(
            config_entries={"core": {"parallelism": "32"}},
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert "core.parallelism" in findings[0]["identifier"]
        assert "32" in findings[0]["identifier"]
