"""Unit tests for core data models and enums.

Validates: Requirements 2.6, 3.5, 4.4, 5.4
"""

import pytest

from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    DAGFile,
    EffortLevel,
    EnvironmentData,
    EnvironmentMetadata,
    FindingCategory,
    MigrationRecommendation,
    MWAAVersionManifest,
    PluginFile,
    SourceType,
)


# ---------------------------------------------------------------------------
# Enum value tests
# ---------------------------------------------------------------------------


class TestSourceType:
    def test_values(self):
        assert SourceType.API.value == "api"
        assert SourceType.MWAA.value == "mwaa"
        assert SourceType.FILESYSTEM.value == "filesystem"

    def test_member_count(self):
        assert len(SourceType) == 3


class TestCompatibilityStatus:
    def test_values(self):
        assert CompatibilityStatus.COMPATIBLE.value == "compatible"
        assert CompatibilityStatus.REQUIRES_MODIFICATION.value == "requires_modification"
        assert CompatibilityStatus.INCOMPATIBLE.value == "incompatible"
        assert CompatibilityStatus.VERSION_CONFLICT.value == "version_conflict"
        assert CompatibilityStatus.UNSUPPORTED.value == "unsupported"
        assert CompatibilityStatus.UNAVAILABLE.value == "unavailable"

    def test_member_count(self):
        assert len(CompatibilityStatus) == 6


class TestMigrationRecommendation:
    def test_values(self):
        assert MigrationRecommendation.LIFT_AND_SHIFT.value == "lift_and_shift"
        assert MigrationRecommendation.LIFT_AND_MODERNIZE.value == "lift_and_modernize"
        assert MigrationRecommendation.NOT_POSSIBLE.value == "not_possible"

    def test_member_count(self):
        assert len(MigrationRecommendation) == 3


class TestFindingCategory:
    def test_values(self):
        assert FindingCategory.DAG.value == "dag"
        assert FindingCategory.DEPENDENCY.value == "dependency"
        assert FindingCategory.CONFIGURATION.value == "configuration"
        assert FindingCategory.PLUGIN.value == "plugin"

    def test_member_count(self):
        assert len(FindingCategory) == 4


class TestEffortLevel:
    def test_values(self):
        assert EffortLevel.LOW.value == "low"
        assert EffortLevel.MEDIUM.value == "medium"
        assert EffortLevel.HIGH.value == "high"

    def test_member_count(self):
        assert len(EffortLevel) == 3


# ---------------------------------------------------------------------------
# Dataclass instantiation tests
# ---------------------------------------------------------------------------


class TestCompatibilityFinding:
    def test_required_fields(self):
        finding = CompatibilityFinding(
            category=FindingCategory.DAG,
            identifier="my_dag",
            status=CompatibilityStatus.COMPATIBLE,
        )
        assert finding.category == FindingCategory.DAG
        assert finding.identifier == "my_dag"
        assert finding.status == CompatibilityStatus.COMPATIBLE

    def test_default_values(self):
        finding = CompatibilityFinding(
            category=FindingCategory.DEPENDENCY,
            identifier="boto3",
            status=CompatibilityStatus.VERSION_CONFLICT,
        )
        assert finding.issues == []
        assert finding.recommendations == []
        assert finding.effort is None

    def test_custom_optional_fields(self):
        finding = CompatibilityFinding(
            category=FindingCategory.PLUGIN,
            identifier="my_plugin",
            status=CompatibilityStatus.REQUIRES_MODIFICATION,
            issues=["uses subprocess"],
            recommendations=["remove subprocess calls"],
            effort=EffortLevel.MEDIUM,
        )
        assert finding.issues == ["uses subprocess"]
        assert finding.recommendations == ["remove subprocess calls"]
        assert finding.effort == EffortLevel.MEDIUM

    def test_default_lists_are_independent(self):
        """Each instance should get its own default list, not a shared one."""
        a = CompatibilityFinding(
            category=FindingCategory.DAG,
            identifier="a",
            status=CompatibilityStatus.COMPATIBLE,
        )
        b = CompatibilityFinding(
            category=FindingCategory.DAG,
            identifier="b",
            status=CompatibilityStatus.COMPATIBLE,
        )
        a.issues.append("issue")
        assert b.issues == []


class TestDAGFile:
    def test_instantiation(self):
        dag = DAGFile(filename="my_dag.py", content="print('hello')")
        assert dag.filename == "my_dag.py"
        assert dag.content == "print('hello')"


class TestPluginFile:
    def test_instantiation(self):
        plugin = PluginFile(filename="my_plugin.py", content="class MyPlugin: pass")
        assert plugin.filename == "my_plugin.py"
        assert plugin.content == "class MyPlugin: pass"


class TestEnvironmentMetadata:
    def test_defaults(self):
        meta = EnvironmentMetadata()
        assert meta.airflow_version is None
        assert meta.source_type == SourceType.FILESYSTEM
        assert meta.dag_count == 0
        assert meta.plugin_count == 0
        assert meta.has_requirements is False
        assert meta.has_configuration is False

    def test_custom_values(self):
        meta = EnvironmentMetadata(
            airflow_version="2.10.3",
            source_type=SourceType.MWAA,
            dag_count=5,
            plugin_count=2,
            has_requirements=True,
            has_configuration=True,
        )
        assert meta.airflow_version == "2.10.3"
        assert meta.source_type == SourceType.MWAA
        assert meta.dag_count == 5
        assert meta.plugin_count == 2
        assert meta.has_requirements is True
        assert meta.has_configuration is True


class TestEnvironmentData:
    def test_defaults(self):
        data = EnvironmentData()
        assert data.dags == []
        assert data.requirements_content is None
        assert data.configuration == {}
        assert data.plugins == []
        assert isinstance(data.metadata, EnvironmentMetadata)

    def test_default_collections_are_independent(self):
        a = EnvironmentData()
        b = EnvironmentData()
        a.dags.append(DAGFile(filename="dag.py", content=""))
        assert b.dags == []

    def test_custom_values(self):
        dag = DAGFile(filename="dag.py", content="dag code")
        plugin = PluginFile(filename="plugin.py", content="plugin code")
        meta = EnvironmentMetadata(airflow_version="2.10.3")
        data = EnvironmentData(
            dags=[dag],
            requirements_content="boto3==1.34.0",
            configuration={"core": {"executor": "CeleryExecutor"}},
            plugins=[plugin],
            metadata=meta,
        )
        assert len(data.dags) == 1
        assert data.requirements_content == "boto3==1.34.0"
        assert data.configuration["core"]["executor"] == "CeleryExecutor"
        assert len(data.plugins) == 1
        assert data.metadata.airflow_version == "2.10.3"


class TestMWAAVersionManifest:
    def test_instantiation(self):
        manifest = MWAAVersionManifest(
            airflow_version="2.10.3",
            pre_installed_packages={"boto3": "1.35.36"},
            supported_config_keys={"core.executor"},
            supported_operators={"airflow.operators.python.PythonOperator"},
            known_incompatible_packages={"pyodbc"},
        )
        assert manifest.airflow_version == "2.10.3"
        assert manifest.pre_installed_packages == {"boto3": "1.35.36"}
        assert "core.executor" in manifest.supported_config_keys
        assert "airflow.operators.python.PythonOperator" in manifest.supported_operators
        assert "pyodbc" in manifest.known_incompatible_packages
