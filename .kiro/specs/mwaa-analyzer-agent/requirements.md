# Requirements Document

## Introduction

The MWAA Analyzer Agent is an open-source, AI-powered command-line tool that analyzes Apache Airflow environments and produces a migration recommendation report. The tool connects to a source Airflow environment (self-managed, another vendor, or an existing Amazon MWAA environment), inspects DAGs, plugins, configurations, dependencies, and metadata, and uses an AI agent (built on the Strands Agents SDK with Amazon Bedrock AgentCore) to determine one of three migration outcomes: **Lift and Shift** (direct migration with minimal changes), **Lift and Modernize** (migration requiring refactoring or adaptation), or **Not Possible** (migration blocked by incompatible features). The tool generates a detailed report with findings, blockers, and actionable recommendations. Built-in telemetry collects anonymous usage statistics to help the maintainers understand adoption patterns.

## Glossary

- **Analyzer_Agent**: The top-level AI agent orchestrating the migration analysis workflow, built using the Strands Agents SDK.
- **Environment_Connector**: The component responsible for establishing a connection to the target Airflow environment and retrieving data for analysis.
- **DAG_Inspector**: The tool that parses and analyzes Directed Acyclic Graph (DAG) files for compatibility with Amazon MWAA.
- **Dependency_Analyzer**: The tool that examines Python package dependencies (requirements.txt, constraints) for MWAA compatibility.
- **Configuration_Analyzer**: The tool that inspects Airflow configuration overrides and settings for MWAA support.
- **Plugin_Analyzer**: The tool that examines custom Airflow plugins for MWAA compatibility.
- **Report_Generator**: The component that produces the final migration assessment report.
- **Telemetry_Collector**: The component that gathers and transmits anonymous usage statistics.
- **Migration_Recommendation**: The final assessment output, one of: Lift_and_Shift, Lift_and_Modernize, or Not_Possible.
- **MWAA**: Amazon Managed Workflows for Apache Airflow, the target managed service.
- **Source_Environment**: The existing Apache Airflow deployment being analyzed (self-managed, vendor-managed, or existing MWAA).
- **Compatibility_Finding**: A single observation about a DAG, plugin, dependency, or configuration item and its compatibility status with MWAA.
- **Strands_Agents_SDK**: The open-source, model-driven Python SDK for building AI agents, used as the agent framework.
- **Bedrock_AgentCore**: Amazon Bedrock AgentCore, the managed platform for deploying and operating AI agents at scale.

## Requirements

### Requirement 1: Environment Connection and Data Retrieval

**User Story:** As a platform engineer, I want the Analyzer_Agent to connect to my existing Airflow environment and retrieve the data needed for analysis, so that I can get a migration assessment without manually gathering information.

#### Acceptance Criteria

1. WHEN the user provides Airflow REST API credentials and endpoint URL, THE Environment_Connector SHALL authenticate and retrieve DAG definitions, DAG run history, connection metadata, variable metadata, and pool configurations via the Airflow REST API.
2. WHEN the user provides an Amazon MWAA environment name and AWS region, THE Environment_Connector SHALL use the AWS SDK to retrieve environment configuration, and use the MWAA-provided Airflow REST API to retrieve DAG and metadata information.
3. WHEN the user provides a local filesystem path containing Airflow project files (dags/, plugins/, requirements.txt, airflow.cfg), THE Environment_Connector SHALL read and parse the files directly from the filesystem.
4. IF the Environment_Connector fails to authenticate with the provided credentials, THEN THE Environment_Connector SHALL return a descriptive error message identifying the authentication failure reason.
5. IF the Environment_Connector cannot reach the specified endpoint within 30 seconds, THEN THE Environment_Connector SHALL return a timeout error with the endpoint URL and a suggestion to verify network connectivity.
6. THE Environment_Connector SHALL support connecting to Airflow versions 2.x and 3.x REST APIs.

### Requirement 2: DAG Compatibility Analysis

**User Story:** As a platform engineer, I want the Analyzer_Agent to analyze my DAG files for MWAA compatibility, so that I understand which DAGs can migrate without changes and which need modification.

#### Acceptance Criteria

1. WHEN DAG files are retrieved, THE DAG_Inspector SHALL parse each DAG file and identify operators, hooks, sensors, and provider packages used.
2. WHEN DAG files are retrieved, THE DAG_Inspector SHALL flag operators and hooks that are not supported by Amazon MWAA, including custom operators that depend on local system resources.
3. WHEN a DAG uses direct metadata database access (e.g., querying the Airflow metadata database directly via SQLAlchemy), THE DAG_Inspector SHALL flag the DAG as requiring modernization because MWAA does not expose direct database access.
4. WHEN a DAG uses SubDAGs, THE DAG_Inspector SHALL flag the DAG as requiring modernization and recommend migration to TaskGroups.
5. WHEN a DAG uses local filesystem paths for data exchange between tasks, THE DAG_Inspector SHALL flag the DAG as requiring modernization and recommend using S3 or XCom.
6. FOR EACH analyzed DAG, THE DAG_Inspector SHALL produce a Compatibility_Finding that includes the DAG identifier, a compatibility status (compatible, requires_modification, incompatible), and a list of specific issues found.

### Requirement 3: Dependency Compatibility Analysis

**User Story:** As a platform engineer, I want the Analyzer_Agent to check my Python dependencies against MWAA-supported packages, so that I know if my requirements.txt will work on MWAA.

#### Acceptance Criteria

1. WHEN a requirements.txt file is provided, THE Dependency_Analyzer SHALL parse each dependency entry including package name and version constraint.
2. WHEN a requirements.txt file is provided, THE Dependency_Analyzer SHALL compare each dependency against the set of packages pre-installed in the target MWAA Airflow version.
3. WHEN a dependency requires system-level libraries (e.g., compiled C extensions not available in the MWAA runtime), THE Dependency_Analyzer SHALL flag the dependency as incompatible and suggest alternatives or custom container approaches.
4. WHEN a dependency has a version conflict with the MWAA-provided version of the same package, THE Dependency_Analyzer SHALL report the conflict with both the required version and the MWAA-provided version.
5. FOR EACH analyzed dependency, THE Dependency_Analyzer SHALL produce a Compatibility_Finding that includes the package name, the version constraint, and a compatibility status (compatible, version_conflict, unavailable).

### Requirement 4: Configuration Compatibility Analysis

**User Story:** As a platform engineer, I want the Analyzer_Agent to evaluate my Airflow configuration overrides, so that I know which settings are supported by MWAA and which need adjustment.

#### Acceptance Criteria

1. WHEN an airflow.cfg file or a set of Airflow configuration overrides is provided, THE Configuration_Analyzer SHALL parse each configuration key-value pair.
2. WHEN a configuration key is not supported by Amazon MWAA (e.g., settings in the [webserver] section that MWAA manages internally), THE Configuration_Analyzer SHALL flag the key as unsupported and explain why.
3. WHEN a configuration value references a local filesystem path, THE Configuration_Analyzer SHALL flag the value as requiring modification for MWAA.
4. FOR EACH analyzed configuration entry, THE Configuration_Analyzer SHALL produce a Compatibility_Finding that includes the configuration section, key, current value, and a compatibility status (supported, unsupported, requires_modification).

### Requirement 5: Plugin Compatibility Analysis

**User Story:** As a platform engineer, I want the Analyzer_Agent to analyze my custom Airflow plugins for MWAA compatibility, so that I know which plugins will work and which need changes.

#### Acceptance Criteria

1. WHEN a plugins directory is provided, THE Plugin_Analyzer SHALL enumerate and parse each plugin module.
2. WHEN a plugin imports packages that are not available in the MWAA runtime, THE Plugin_Analyzer SHALL flag the plugin as requiring modification and list the missing imports.
3. WHEN a plugin accesses local system resources (e.g., subprocess calls, local file I/O outside the DAGs folder, network sockets), THE Plugin_Analyzer SHALL flag the plugin as requiring modernization.
4. FOR EACH analyzed plugin, THE Plugin_Analyzer SHALL produce a Compatibility_Finding that includes the plugin name, a compatibility status (compatible, requires_modification, incompatible), and a list of specific issues found.

### Requirement 6: Migration Recommendation Engine

**User Story:** As a platform engineer, I want the Analyzer_Agent to synthesize all findings into a clear migration recommendation, so that I can make an informed decision about my migration approach.

#### Acceptance Criteria

1. WHEN all analysis tools have completed, THE Analyzer_Agent SHALL aggregate all Compatibility_Findings and produce a single Migration_Recommendation of Lift_and_Shift, Lift_and_Modernize, or Not_Possible.
2. WHEN all Compatibility_Findings have a status of compatible, THE Analyzer_Agent SHALL recommend Lift_and_Shift.
3. WHEN one or more Compatibility_Findings have a status of requires_modification and no findings have a status of incompatible, THE Analyzer_Agent SHALL recommend Lift_and_Modernize and list the required modifications.
4. WHEN one or more Compatibility_Findings have a status of incompatible, THE Analyzer_Agent SHALL recommend Not_Possible and list the blocking incompatibilities along with potential workarounds where applicable.
5. THE Analyzer_Agent SHALL use the Strands_Agents_SDK agent loop to reason over the collected findings, apply MWAA migration knowledge, and generate the recommendation with natural-language justification.

### Requirement 7: Report Generation

**User Story:** As a platform engineer, I want the Analyzer_Agent to produce a detailed, readable migration report, so that I can share the findings with my team and plan the migration.

#### Acceptance Criteria

1. THE Report_Generator SHALL produce a report containing: an executive summary, the Migration_Recommendation, a detailed findings section organized by category (DAGs, dependencies, configuration, plugins), and an action items section.
2. THE Report_Generator SHALL output the report in Markdown format by default.
3. WHERE the user requests JSON output format, THE Report_Generator SHALL output the report as a structured JSON document with the same content sections.
4. WHERE the user requests HTML output format, THE Report_Generator SHALL output the report as a self-contained HTML document with inline styling.
5. WHEN the Migration_Recommendation is Lift_and_Modernize, THE Report_Generator SHALL include a prioritized list of modifications ordered by estimated effort (low, medium, high).
6. WHEN the Migration_Recommendation is Not_Possible, THE Report_Generator SHALL include a section describing each blocker and any known workarounds or alternative approaches.
7. THE Report_Generator SHALL include a metadata section in the report containing the analysis timestamp, the source environment type, the target MWAA version, and the tool version.

### Requirement 8: Agent Architecture and Strands SDK Integration

**User Story:** As a developer, I want the Analyzer_Agent to be built using the Strands Agents SDK with Amazon Bedrock as the model provider, so that the tool leverages production-grade AI agent infrastructure.

#### Acceptance Criteria

1. THE Analyzer_Agent SHALL be implemented using the Strands_Agents_SDK Python package as the agent framework.
2. THE Analyzer_Agent SHALL use Amazon Bedrock as the default model provider for the underlying LLM.
3. THE Analyzer_Agent SHALL define each analysis capability (DAG inspection, dependency analysis, configuration analysis, plugin analysis, report generation) as a Strands tool function decorated with the @tool decorator.
4. THE Analyzer_Agent SHALL use a system prompt that encodes MWAA migration knowledge, compatibility rules, and the three-outcome decision framework.
5. WHERE the user provides an alternative model provider configuration, THE Analyzer_Agent SHALL support using that provider instead of Amazon Bedrock.

### Requirement 9: Telemetry and Usage Statistics

**User Story:** As a project maintainer, I want the Analyzer_Agent to collect anonymous usage statistics, so that I can understand adoption patterns and prioritize improvements.

#### Acceptance Criteria

1. THE Telemetry_Collector SHALL collect anonymous usage events including: tool invocation count, analysis duration, source environment type (API, MWAA, filesystem), migration recommendation outcome, number of DAGs analyzed, and error categories encountered.
2. THE Telemetry_Collector SHALL NOT collect any personally identifiable information, credentials, DAG content, environment names, or IP addresses.
3. THE Telemetry_Collector SHALL transmit usage events to a configurable telemetry endpoint using HTTPS.
4. WHEN the user sets the MWAA_ANALYZER_TELEMETRY_OPT_OUT environment variable to "true", THE Telemetry_Collector SHALL disable all telemetry collection and transmission.
5. WHEN the telemetry endpoint is unreachable, THE Telemetry_Collector SHALL silently discard the telemetry event and continue normal operation without affecting the analysis workflow.
6. THE Telemetry_Collector SHALL display a notice on first run informing the user that anonymous telemetry is collected and how to opt out.

### Requirement 10: Command-Line Interface

**User Story:** As a platform engineer, I want to run the Analyzer_Agent from the command line with clear options, so that I can integrate it into my workflow and automation scripts.

#### Acceptance Criteria

1. THE Analyzer_Agent SHALL provide a CLI entry point named `mwaa-analyzer` that accepts subcommands for analysis operations.
2. WHEN the user runs `mwaa-analyzer analyze --source-type api --endpoint <URL> --token <TOKEN>`, THE Analyzer_Agent SHALL connect to the Airflow REST API and perform a full migration analysis.
3. WHEN the user runs `mwaa-analyzer analyze --source-type mwaa --environment-name <NAME> --region <REGION>`, THE Analyzer_Agent SHALL connect to the specified MWAA environment and perform a full migration analysis.
4. WHEN the user runs `mwaa-analyzer analyze --source-type filesystem --path <PATH>`, THE Analyzer_Agent SHALL analyze the Airflow project files at the specified path.
5. WHERE the user provides the `--output-format` flag with a value of "markdown", "json", or "html", THE Report_Generator SHALL produce the report in the specified format.
6. WHERE the user provides the `--output-file` flag, THE Report_Generator SHALL write the report to the specified file path instead of stdout.
7. WHERE the user provides the `--target-mwaa-version` flag, THE Analyzer_Agent SHALL evaluate compatibility against the specified MWAA version.
8. IF the user provides an invalid combination of flags, THEN THE Analyzer_Agent SHALL display a descriptive error message and usage instructions.

### Requirement 11: Security and Credential Handling

**User Story:** As a platform engineer, I want the Analyzer_Agent to handle my credentials securely, so that my environment access tokens and AWS credentials are not exposed or persisted.

#### Acceptance Criteria

1. THE Analyzer_Agent SHALL NOT persist credentials to disk, logs, telemetry, or the generated report.
2. THE Analyzer_Agent SHALL accept credentials via environment variables, CLI flags, or AWS credential chain (for MWAA source type) and hold credentials only in memory for the duration of the analysis.
3. WHEN the analysis is complete, THE Analyzer_Agent SHALL clear credential values from memory.
4. THE Analyzer_Agent SHALL use HTTPS for all network communication with the source environment and telemetry endpoint.
5. IF the user provides credentials via CLI flags, THEN THE Analyzer_Agent SHALL display a warning recommending the use of environment variables instead to avoid credentials appearing in shell history.

### Requirement 12: Open-Source Packaging and Distribution

**User Story:** As a developer, I want the Analyzer_Agent to be packaged as a standard Python project with clear documentation, so that I can install it easily and contribute to the project.

#### Acceptance Criteria

1. THE Analyzer_Agent SHALL be packaged as a Python project installable via `pip install mwaa-analyzer-agent`.
2. THE Analyzer_Agent SHALL include a pyproject.toml file specifying all dependencies with pinned major versions.
3. THE Analyzer_Agent SHALL include a LICENSE file using the Apache License 2.0.
4. THE Analyzer_Agent SHALL include a README.md file with installation instructions, usage examples for each source type, configuration options, and a contributing guide reference.
5. THE Analyzer_Agent SHALL include a CONTRIBUTING.md file with development setup instructions, coding standards, and pull request guidelines.
6. THE Analyzer_Agent SHALL include a NOTICE file attributing third-party dependencies.

### Requirement 13: Error Handling and Resilience

**User Story:** As a platform engineer, I want the Analyzer_Agent to handle errors gracefully and provide partial results when possible, so that I still get useful information even if some parts of the analysis fail.

#### Acceptance Criteria

1. IF a single analysis tool (DAG_Inspector, Dependency_Analyzer, Configuration_Analyzer, or Plugin_Analyzer) fails during execution, THEN THE Analyzer_Agent SHALL continue executing the remaining tools and include the partial results in the report.
2. IF a single analysis tool fails, THEN THE Report_Generator SHALL include a section in the report noting which analysis was skipped and the reason for the failure.
3. IF the LLM provider is unreachable or returns an error, THEN THE Analyzer_Agent SHALL retry the request up to 3 times with exponential backoff before reporting the failure.
4. WHEN an unexpected error occurs, THE Analyzer_Agent SHALL log the error with a correlation identifier and display a user-friendly error message with the correlation identifier for troubleshooting.

### Requirement 14: Logging and Observability

**User Story:** As a developer or operator, I want the Analyzer_Agent to produce structured logs, so that I can troubleshoot issues and understand the analysis workflow.

#### Acceptance Criteria

1. THE Analyzer_Agent SHALL log analysis progress events using Python standard logging at the INFO level, including which analysis tool is running and when each tool completes.
2. WHERE the user sets the `--verbose` flag, THE Analyzer_Agent SHALL set the log level to DEBUG and include detailed information about each Compatibility_Finding as it is produced.
3. THE Analyzer_Agent SHALL include a unique run identifier in each log entry to support correlation across a single analysis run.
