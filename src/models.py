"""Core data models and enums for the MWAA Analyzer Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SourceType(Enum):
    """Source type for the Airflow environment being analyzed."""

    API = "api"
    MWAA = "mwaa"
    FILESYSTEM = "filesystem"


class CompatibilityStatus(Enum):
    """Compatibility status for a finding."""

    COMPATIBLE = "compatible"
    REQUIRES_MODIFICATION = "requires_modification"
    INCOMPATIBLE = "incompatible"
    VERSION_CONFLICT = "version_conflict"
    UNSUPPORTED = "unsupported"
    UNAVAILABLE = "unavailable"


class MigrationRecommendation(Enum):
    """Overall migration recommendation outcome."""

    LIFT_AND_SHIFT = "lift_and_shift"
    LIFT_AND_MODERNIZE = "lift_and_modernize"
    NOT_POSSIBLE = "not_possible"


class FindingCategory(Enum):
    """Category of a compatibility finding."""

    DAG = "dag"
    DEPENDENCY = "dependency"
    CONFIGURATION = "configuration"
    PLUGIN = "plugin"


class EffortLevel(Enum):
    """Estimated effort level for a required modification."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class CompatibilityFinding:
    """A single compatibility finding from an analysis tool."""

    category: FindingCategory
    identifier: str
    status: CompatibilityStatus
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    effort: EffortLevel | None = None


@dataclass
class DAGFile:
    """Represents a DAG file with its filename and content."""

    filename: str
    content: str


@dataclass
class PluginFile:
    """Represents a plugin file with its filename and content."""

    filename: str
    content: str


@dataclass
class EnvironmentMetadata:
    """Metadata about the source Airflow environment."""

    airflow_version: str | None = None
    source_type: SourceType = SourceType.FILESYSTEM
    dag_count: int = 0
    plugin_count: int = 0
    has_requirements: bool = False
    has_configuration: bool = False


@dataclass
class EnvironmentData:
    """All data retrieved from the source Airflow environment."""

    dags: list[DAGFile] = field(default_factory=list)
    requirements_content: str | None = None
    configuration: dict[str, dict[str, str]] = field(default_factory=dict)
    plugins: list[PluginFile] = field(default_factory=list)
    metadata: EnvironmentMetadata = field(default_factory=EnvironmentMetadata)


@dataclass
class ReportMetadata:
    """Metadata included in the migration report."""

    timestamp: datetime
    source_type: SourceType
    target_mwaa_version: str
    tool_version: str
    run_id: str


@dataclass
class MigrationReport:
    """The complete migration assessment report."""

    metadata: ReportMetadata
    recommendation: MigrationRecommendation
    findings: list[CompatibilityFinding]
    executive_summary: str
    action_items: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    workarounds: list[str] = field(default_factory=list)


@dataclass
class MWAAVersionManifest:
    """Compatibility manifest for a specific MWAA Airflow version."""

    airflow_version: str
    pre_installed_packages: dict[str, str]
    supported_config_keys: set[str]
    supported_operators: set[str]
    known_incompatible_packages: set[str]
