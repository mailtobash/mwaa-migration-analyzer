"""Property-based tests for the Configuration Analyzer tool.

Tests Properties 7, 8, and 4 as they relate to the Configuration Analyzer:
- Property 7: Configuration key compatibility check
- Property 8: Filesystem path detection in configuration values
- Property 4: Compatibility finding structural invariant (Configuration Analyzer)
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume

from models import (
    CompatibilityStatus,
    FindingCategory,
)
from tools.configuration_analyzer import (
    analyze_configuration,
    classify_config_entry,
)
from data_loader import load_manifest


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating config section names
_config_section = st.sampled_from([
    "core", "webserver", "scheduler", "celery", "logging",
    "operators", "email", "smtp", "secrets", "api",
])

# Strategy for generating config key names (lowercase letters and underscores)
_config_key = st.from_regex(r"[a-z][a-z_]{1,30}", fullmatch=True)

# Strategy for generating non-path config values (simple strings that don't
# look like filesystem paths)
_non_path_value = st.from_regex(r"[a-zA-Z0-9][a-zA-Z0-9_.@:, ]{0,50}", fullmatch=True)

# Strategy for generating Unix absolute filesystem paths
_unix_absolute_path = st.from_regex(
    r"/[a-z][a-z0-9_/.\-]{1,50}", fullmatch=True
)

# Strategy for generating Unix relative filesystem paths (./ or ../)
_unix_relative_path = st.from_regex(
    r"\.\.?/[a-z][a-z0-9_/.\-]{0,50}", fullmatch=True
)

# Strategy for generating Windows drive letter paths
_windows_path = st.from_regex(
    r"[A-Z]:\\[a-zA-Z0-9_\\.\-]{1,50}", fullmatch=True
)

# Combined strategy for any filesystem path
_filesystem_path = st.one_of(
    _unix_absolute_path,
    _unix_relative_path,
    _windows_path,
)


# ---------------------------------------------------------------------------
# Property 7: Configuration key compatibility check
# ---------------------------------------------------------------------------

class TestProperty7ConfigKeyCompatibilityCheck:
    """Feature: mwaa-analyzer-agent, Property 7: Configuration key compatibility check

    For any Airflow configuration key (in "section.key" format) and a given
    MWAA version manifest, if the key is not in the manifest's supported
    config keys set, the Configuration_Analyzer SHALL flag it as unsupported;
    if the key is in the supported set, it SHALL be flagged as supported
    (unless the value triggers a separate issue).

    Validates: Requirements 4.2
    """

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        self.manifest = load_manifest("2.10.3")

    @settings(max_examples=100)
    @given(
        section=_config_section,
        key=_config_key,
        value=_non_path_value,
    )
    def test_unsupported_key_flagged(self, section, key, value):
        """Feature: mwaa-analyzer-agent, Property 7: Configuration key compatibility check

        **Validates: Requirements 4.2**
        """
        config_key = f"{section}.{key}"
        assume(config_key not in self.manifest.supported_config_keys)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status == CompatibilityStatus.UNSUPPORTED, (
            f"Unsupported config key '{config_key}' should be flagged as "
            f"unsupported, got {finding.status}"
        )
        assert len(finding.issues) > 0, (
            f"Unsupported config key '{config_key}' should have at least one issue"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_supported_key_not_flagged_unsupported(self, data):
        """Feature: mwaa-analyzer-agent, Property 7: Configuration key compatibility check

        **Validates: Requirements 4.2**
        """
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        # Use a non-path value so only the key support check matters
        value = data.draw(_non_path_value)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status != CompatibilityStatus.UNSUPPORTED, (
            f"Supported config key '{config_key}' should not be flagged as "
            f"unsupported, got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_supported_key_with_non_path_value_is_compatible(self, data):
        """Feature: mwaa-analyzer-agent, Property 7: Configuration key compatibility check

        **Validates: Requirements 4.2**
        """
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        value = data.draw(_non_path_value)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status == CompatibilityStatus.COMPATIBLE, (
            f"Supported config key '{config_key}' with non-path value "
            f"'{value}' should be compatible, got {finding.status}"
        )

    @settings(max_examples=100)
    @given(
        section=_config_section,
        key=_config_key,
        value=_non_path_value,
    )
    def test_unsupported_key_via_analyze_configuration(self, section, key, value):
        """Feature: mwaa-analyzer-agent, Property 7: Configuration key compatibility check

        **Validates: Requirements 4.2**

        Integration test using the full analyze_configuration tool function.
        """
        config_key = f"{section}.{key}"
        assume(config_key not in self.manifest.supported_config_keys)

        config_entries = {section: {key: value}}
        result = analyze_configuration._tool_func(
            config_entries=config_entries,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["status"] == CompatibilityStatus.UNSUPPORTED.value, (
            f"Unsupported config key '{config_key}' should be flagged as "
            f"unsupported via analyze_configuration, got {finding['status']}"
        )


# ---------------------------------------------------------------------------
# Property 8: Filesystem path detection in configuration values
# ---------------------------------------------------------------------------

class TestProperty8FilesystemPathDetection:
    """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

    For any configuration value string containing a Unix or Windows filesystem
    path pattern (e.g., starting with `/`, `./`, `../`, or a drive letter),
    the Configuration_Analyzer SHALL flag the entry as requiring modification.

    Validates: Requirements 4.3
    """

    @pytest.fixture(autouse=True)
    def _load_manifest(self):
        self.manifest = load_manifest("2.10.3")

    @settings(max_examples=100)
    @given(data=st.data())
    def test_unix_absolute_path_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

        **Validates: Requirements 4.3**
        """
        # Use a supported key so the path detection is the only trigger
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        value = data.draw(_unix_absolute_path)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status == CompatibilityStatus.REQUIRES_MODIFICATION, (
            f"Unix absolute path '{value}' should trigger requires_modification, "
            f"got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_unix_relative_path_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

        **Validates: Requirements 4.3**
        """
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        value = data.draw(_unix_relative_path)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status == CompatibilityStatus.REQUIRES_MODIFICATION, (
            f"Unix relative path '{value}' should trigger requires_modification, "
            f"got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_windows_path_detected(self, data):
        """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

        **Validates: Requirements 4.3**
        """
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        value = data.draw(_windows_path)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=value,
            supported_keys=self.manifest.supported_config_keys,
        )

        assert finding.status == CompatibilityStatus.REQUIRES_MODIFICATION, (
            f"Windows path '{value}' should trigger requires_modification, "
            f"got {finding.status}"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_filesystem_path_via_analyze_configuration(self, data):
        """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

        **Validates: Requirements 4.3**

        Integration test using the full analyze_configuration tool function.
        """
        assume(len(self.manifest.supported_config_keys) > 0)
        config_key = data.draw(
            st.sampled_from(sorted(self.manifest.supported_config_keys))
        )
        section, key = config_key.split(".", 1)
        value = data.draw(_filesystem_path)

        config_entries = {section: {key: value}}
        result = analyze_configuration._tool_func(
            config_entries=config_entries,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["status"] == CompatibilityStatus.REQUIRES_MODIFICATION.value, (
            f"Filesystem path value '{value}' should trigger requires_modification "
            f"via analyze_configuration, got {finding['status']}"
        )

    @settings(max_examples=100)
    @given(
        section=_config_section,
        key=_config_key,
        path_value=_filesystem_path,
    )
    def test_unsupported_key_with_path_still_unsupported(self, section, key, path_value):
        """Feature: mwaa-analyzer-agent, Property 8: Filesystem path detection in configuration values

        **Validates: Requirements 4.3**

        When a key is unsupported, the unsupported status takes precedence
        over the path detection.
        """
        config_key = f"{section}.{key}"
        assume(config_key not in self.manifest.supported_config_keys)

        finding = classify_config_entry(
            section=section,
            key=key,
            value=path_value,
            supported_keys=self.manifest.supported_config_keys,
        )

        # Unsupported key check happens first, so status should be UNSUPPORTED
        assert finding.status == CompatibilityStatus.UNSUPPORTED, (
            f"Unsupported config key '{config_key}' should remain unsupported "
            f"even with a path value, got {finding.status}"
        )


# ---------------------------------------------------------------------------
# Property 4: Compatibility finding structural invariant (Configuration Analyzer)
# ---------------------------------------------------------------------------

class TestProperty4FindingStructuralInvariantConfigurationAnalyzer:
    """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Configuration Analyzer)

    For any input to analyze_configuration, every produced finding SHALL
    contain a non-empty identifier, a valid CompatibilityStatus enum value,
    and an issues list.

    Validates: Requirements 4.4
    """

    @settings(max_examples=100)
    @given(
        section=_config_section,
        key=_config_key,
        value=st.one_of(_non_path_value, _filesystem_path),
    )
    def test_single_entry_finding_structure(self, section, key, value):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Configuration Analyzer)

        **Validates: Requirements 4.4**
        """
        config_entries = {section: {key: value}}
        result = analyze_configuration._tool_func(
            config_entries=config_entries,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1, (
            f"analyze_configuration should produce exactly one finding for "
            f"a single config entry, got {len(findings)}"
        )

        valid_statuses = {s.value for s in CompatibilityStatus}
        finding = findings[0]

        # Non-empty identifier
        assert "identifier" in finding
        assert isinstance(finding["identifier"], str)
        assert len(finding["identifier"]) > 0, (
            "Finding identifier must be non-empty"
        )

        # Valid status
        assert "status" in finding
        assert finding["status"] in valid_statuses, (
            f"Status '{finding['status']}' is not a valid CompatibilityStatus"
        )

        # Issues list present
        assert "issues" in finding
        assert isinstance(finding["issues"], list), (
            "Issues must be a list"
        )

    @settings(max_examples=100)
    @given(data=st.data())
    def test_multiple_entries_all_have_valid_findings(self, data):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Configuration Analyzer)

        **Validates: Requirements 4.4**
        """
        num_entries = data.draw(st.integers(min_value=1, max_value=5))
        config_entries: dict[str, dict[str, str]] = {}
        total_keys = 0

        for _ in range(num_entries):
            section = data.draw(_config_section)
            key = data.draw(_config_key)
            value = data.draw(st.one_of(_non_path_value, _filesystem_path))

            if section not in config_entries:
                config_entries[section] = {}
            # Only count if this is a new key in the section
            if key not in config_entries[section]:
                total_keys += 1
            config_entries[section][key] = value

        result = analyze_configuration._tool_func(
            config_entries=config_entries,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]

        # Should have one finding per unique config entry
        assert len(findings) == total_keys, (
            f"Expected {total_keys} findings, got {len(findings)}"
        )

        valid_statuses = {s.value for s in CompatibilityStatus}

        for finding in findings:
            # Non-empty identifier
            assert finding["identifier"], "Finding identifier must be non-empty"

            # Valid status
            assert finding["status"] in valid_statuses, (
                f"Status '{finding['status']}' is not a valid CompatibilityStatus"
            )

            # Issues list present
            assert isinstance(finding["issues"], list), (
                "Issues must be a list"
            )

    @settings(max_examples=100)
    @given(
        section=_config_section,
        key=_config_key,
        value=st.one_of(_non_path_value, _filesystem_path),
    )
    def test_finding_category_is_configuration(self, section, key, value):
        """Feature: mwaa-analyzer-agent, Property 4: Compatibility finding structural invariant (Configuration Analyzer)

        **Validates: Requirements 4.4**
        """
        config_entries = {section: {key: value}}
        result = analyze_configuration._tool_func(
            config_entries=config_entries,
            target_mwaa_version="2.10.3",
        )
        findings = result["findings"]
        assert len(findings) == 1

        finding = findings[0]
        assert finding["category"] == FindingCategory.CONFIGURATION.value, (
            f"Finding category should be 'configuration', got '{finding['category']}'"
        )
