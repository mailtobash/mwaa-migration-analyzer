# Implementation Plan: MWAA Analyzer Agent

## Overview

Build a Python CLI tool using the Strands Agents SDK that analyzes Apache Airflow environments and produces migration recommendation reports for Amazon MWAA. Implementation proceeds bottom-up: data models first, then connectors, analysis tools, recommendation engine, report generator, agent orchestration, telemetry, CLI entry point, and finally integration wiring.

## Tasks

- [x] 1. Set up project structure, packaging, and core data models
  - [x] 1.1 Create project skeleton with pyproject.toml, directory structure, and dependencies
    - Create `mwaa_analyzer_agent/` package with `__init__.py`
    - Create `pyproject.toml` with dependencies: `strands-agents`, `strands-agents-builder`, `click`, `httpx`, `boto3`, `packaging`, `jinja2`, `hypothesis`, `pytest`, `pytest-mock`, `moto`
    - Create `LICENSE` (Apache 2.0), `README.md`, `CONTRIBUTING.md`, `NOTICE` files
    - Set up `tests/` directory with `unit/`, `property/`, `integration/` subdirectories and `conftest.py`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 1.2 Implement core data models and enums
    - Create `mwaa_analyzer_agent/models.py` with all dataclasses: `SourceType`, `CompatibilityStatus`, `MigrationRecommendation`, `FindingCategory`, `EffortLevel`, `CompatibilityFinding`, `DAGFile`, `PluginFile`, `EnvironmentMetadata`, `EnvironmentData`, `ReportMetadata`, `MigrationReport`, `TelemetryEvent`, `MWAAVersionManifest`
    - _Requirements: 2.6, 3.5, 4.4, 5.4, 6.1_

  - [x] 1.3 Create MWAA version manifest data files
    - Create `mwaa_analyzer_agent/data/` directory with JSON manifest files for supported MWAA versions (at minimum 2.10.3)
    - Each manifest includes: `pre_installed_packages`, `supported_config_keys`, `supported_operators`, `known_incompatible_packages`
    - Create a loader function in `mwaa_analyzer_agent/data/loader.py` to load manifests by version
    - _Requirements: 3.2, 4.2, 5.2, 10.7_

  - [x] 1.4 Write unit tests for data models and manifest loader
    - Test enum values, dataclass instantiation, default values
    - Test manifest loading for valid and invalid versions
    - _Requirements: 2.6, 3.5, 4.4, 5.4_

- [x] 2. Implement environment connectors
  - [x] 2.1 Define the EnvironmentConnector protocol and connector factory
    - Create `mwaa_analyzer_agent/connectors/__init__.py` with the `EnvironmentConnector` protocol
    - Create a factory function that returns the appropriate connector based on `SourceType`
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 2.2 Implement FilesystemConnector
    - Create `mwaa_analyzer_agent/connectors/filesystem.py`
    - Read DAG files from `dags/` directory, plugins from `plugins/`, `requirements.txt`, and `airflow.cfg`
    - Parse `airflow.cfg` into `dict[str, dict[str, str]]` structure
    - Populate `EnvironmentMetadata` with file counts and source type
    - _Requirements: 1.3_

  - [x] 2.3 Implement ApiConnector
    - Create `mwaa_analyzer_agent/connectors/api.py`
    - Use `httpx` to authenticate with bearer token and retrieve DAGs, requirements, configuration, and plugins via Airflow REST API
    - Support both Airflow 2.x and 3.x REST API endpoints
    - Implement 30-second connection timeout
    - Return descriptive errors for authentication failures and timeouts
    - _Requirements: 1.1, 1.4, 1.5, 1.6_

  - [x] 2.4 Implement MwaaConnector
    - Create `mwaa_analyzer_agent/connectors/mwaa.py`
    - Use `boto3` to call `mwaa:GetEnvironment` and retrieve the CLI token
    - Use the CLI token to access the Airflow REST API for DAG and metadata retrieval
    - _Requirements: 1.2_

  - [x] 2.5 Write unit tests for connectors
    - Test FilesystemConnector with sample directory structures, missing files, empty directories
    - Test ApiConnector with mocked httpx responses for success, auth failure, and timeout
    - Test MwaaConnector with mocked boto3 responses
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 3. Checkpoint - Verify project structure and connectors
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement DAG Inspector tool
  - [x] 4.1 Implement the inspect_dags tool function
    - Create `mwaa_analyzer_agent/tools/dag_inspector.py` with `@tool` decorated `inspect_dags` function
    - Use Python `ast` module to parse DAG files and extract imports (operators, hooks, sensors)
    - Detect unsupported operators by comparing against MWAA version manifest
    - Detect direct metadata DB access (SQLAlchemy session usage patterns)
    - Detect SubDAG usage and recommend TaskGroups
    - Detect local filesystem path usage for inter-task data exchange
    - Produce `CompatibilityFinding` per DAG with appropriate status and issues
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 4.2 Write property test for DAG import extraction completeness
    - **Property 1: DAG import extraction completeness**
    - **Validates: Requirements 2.1**

  - [x] 4.3 Write property test for unsupported operator flagging
    - **Property 2: Unsupported operator flagging**
    - **Validates: Requirements 2.2**

  - [x] 4.4 Write property test for DAG incompatible pattern detection
    - **Property 3: DAG incompatible pattern detection**
    - **Validates: Requirements 2.3, 2.4, 2.5**

  - [x] 4.5 Write property test for compatibility finding structural invariant (DAG Inspector)
    - **Property 4: Compatibility finding structural invariant**
    - **Validates: Requirements 2.6**

  - [x] 4.6 Write unit tests for DAG Inspector
    - Test with sample DAG files containing known operators, SubDAGs, SQLAlchemy usage, local paths
    - Test with empty DAG files and files with syntax errors
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 5. Implement Dependency Analyzer tool
  - [x] 5.1 Implement the analyze_dependencies tool function
    - Create `mwaa_analyzer_agent/tools/dependency_analyzer.py` with `@tool` decorated `analyze_dependencies` function
    - Parse requirements.txt entries using `packaging.requirements.Requirement`
    - Compare each dependency against MWAA version manifest pre-installed packages
    - Classify as: compatible, version_conflict, unavailable, or incompatible (system-level libs)
    - Produce `CompatibilityFinding` per dependency
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 5.2 Write property test for requirements.txt parsing round-trip
    - **Property 5: Requirements.txt parsing round-trip**
    - **Validates: Requirements 3.1**

  - [x] 5.3 Write property test for dependency compatibility classification
    - **Property 6: Dependency compatibility classification**
    - **Validates: Requirements 3.2, 3.3, 3.4**

  - [x] 5.4 Write property test for compatibility finding structural invariant (Dependency Analyzer)
    - **Property 4: Compatibility finding structural invariant**
    - **Validates: Requirements 3.5**

  - [x] 5.5 Write unit tests for Dependency Analyzer
    - Test with known compatible, conflicting, unavailable, and incompatible packages
    - Test with empty requirements.txt and malformed entries
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. Implement Configuration Analyzer tool
  - [x] 6.1 Implement the analyze_configuration tool function
    - Create `mwaa_analyzer_agent/tools/configuration_analyzer.py` with `@tool` decorated `analyze_configuration` function
    - Check each config key against MWAA-supported configuration options from the version manifest
    - Flag unsupported sections (e.g., `[webserver]` settings managed by MWAA)
    - Detect local filesystem path references in configuration values
    - Produce `CompatibilityFinding` per configuration entry
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 6.2 Write property test for configuration key compatibility check
    - **Property 7: Configuration key compatibility check**
    - **Validates: Requirements 4.2**

  - [x] 6.3 Write property test for filesystem path detection in configuration values
    - **Property 8: Filesystem path detection in configuration values**
    - **Validates: Requirements 4.3**

  - [x] 6.4 Write property test for compatibility finding structural invariant (Configuration Analyzer)
    - **Property 4: Compatibility finding structural invariant**
    - **Validates: Requirements 4.4**

  - [x] 6.5 Write unit tests for Configuration Analyzer
    - Test with supported and unsupported config keys, filesystem path values
    - Test with empty configuration
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 7. Implement Plugin Analyzer tool
  - [x] 7.1 Implement the analyze_plugins tool function
    - Create `mwaa_analyzer_agent/tools/plugin_analyzer.py` with `@tool` decorated `analyze_plugins` function
    - Parse plugin files using AST to detect imports not available in MWAA runtime
    - Detect subprocess calls, local file I/O outside DAGs folder, network socket usage
    - Check for MWAA plugin structure compliance
    - Produce `CompatibilityFinding` per plugin
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 7.2 Write property test for plugin system resource access detection
    - **Property 9: Plugin system resource access detection**
    - **Validates: Requirements 5.3**

  - [x] 7.3 Write property test for plugin unavailable import detection
    - **Property 10: Plugin unavailable import detection**
    - **Validates: Requirements 5.2**

  - [x] 7.4 Write property test for compatibility finding structural invariant (Plugin Analyzer)
    - **Property 4: Compatibility finding structural invariant**
    - **Validates: Requirements 5.4**

  - [x] 7.5 Write unit tests for Plugin Analyzer
    - Test with plugins containing subprocess calls, socket usage, missing imports
    - Test with clean plugins and empty plugin files
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. Checkpoint - Verify all analysis tools
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement Recommendation Engine
  - [x] 9.1 Implement the recommendation engine
    - Create `mwaa_analyzer_agent/recommendation.py` with `determine_recommendation` function
    - Implement deterministic logic: all compatible → Lift_and_Shift; any incompatible → Not_Possible; any requires_modification/version_conflict/unsupported → Lift_and_Modernize
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 9.2 Write property test for migration recommendation determinism
    - **Property 11: Migration recommendation determinism**
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [x] 9.3 Write unit tests for Recommendation Engine
    - Test each recommendation outcome with specific finding combinations
    - Test with empty findings list
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 10. Implement Report Generator tool
  - [x] 10.1 Implement the generate_report tool function
    - Create `mwaa_analyzer_agent/tools/report_generator.py` with `@tool` decorated `generate_report` function
    - Create Jinja2 templates for Markdown and HTML output in `mwaa_analyzer_agent/templates/`
    - Implement JSON output as structured dict serialization
    - Include all required report sections: executive summary, recommendation, findings by category, action items, metadata
    - For Lift_and_Modernize: order action items by effort level (low → medium → high)
    - For Not_Possible: include blockers section with all incompatible findings
    - HTML output must be self-contained with inline CSS
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 10.2 Write property test for report required sections presence
    - **Property 12: Report required sections presence**
    - **Validates: Requirements 7.1, 7.7**

  - [x] 10.3 Write property test for JSON report validity
    - **Property 13: JSON report validity**
    - **Validates: Requirements 7.3**

  - [x] 10.4 Write property test for HTML report self-containment
    - **Property 14: HTML report self-containment**
    - **Validates: Requirements 7.4**

  - [x] 10.5 Write property test for Lift_and_Modernize effort ordering
    - **Property 15: Lift_and_Modernize effort ordering**
    - **Validates: Requirements 7.5**

  - [x] 10.6 Write property test for Not_Possible blockers inclusion
    - **Property 16: Not_Possible blockers inclusion**
    - **Validates: Requirements 7.6**

  - [x] 10.7 Write unit tests for Report Generator
    - Test each output format with sample findings
    - Test report content for each recommendation type
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

- [x] 11. Checkpoint - Verify recommendation engine and report generator
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Implement Telemetry Collector
  - [x] 12.1 Implement the TelemetryCollector class
    - Create `mwaa_analyzer_agent/telemetry.py` with `TelemetryCollector` class
    - Implement `record_event` and `flush` methods using `httpx` HTTPS POST
    - Check `MWAA_ANALYZER_TELEMETRY_OPT_OUT` environment variable
    - Silently discard events on network failure
    - Implement first-run notice using `.mwaa-analyzer-telemetry-notice` marker file in user home
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 12.2 Write property test for telemetry event completeness
    - **Property 17: Telemetry event completeness**
    - **Validates: Requirements 9.1**

  - [x] 12.3 Write property test for no PII in telemetry
    - **Property 18: No PII in telemetry**
    - **Validates: Requirements 9.2**

  - [x] 12.4 Write unit tests for Telemetry Collector
    - Test opt-out behavior, first-run notice, network failure handling
    - Test that no PII is included in events
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 13. Implement Analyzer Agent and error handling
  - [x] 13.1 Implement the Analyzer Agent with Strands SDK
    - Create `mwaa_analyzer_agent/agent.py` with `create_agent` function
    - Configure `strands.Agent` with `BedrockModel` as default provider
    - Register all tool functions: `inspect_dags`, `analyze_dependencies`, `analyze_configuration`, `analyze_plugins`, `generate_report`
    - Write the MWAA migration system prompt encoding compatibility rules and the three-outcome decision framework
    - Support alternative model provider configuration
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 13.2 Implement error handling and resilience
    - Implement per-tool error boundaries: catch exceptions, log with correlation ID, continue with remaining tools
    - Implement LLM provider retry with exponential backoff (3 retries, 1s/2s/4s delays)
    - Generate UUID-based run identifier for correlation across log entries
    - Include skipped analysis notes in report when tools fail
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 13.3 Implement logging and observability
    - Set up Python standard logging with custom filter for run identifier injection
    - Log analysis progress at INFO level (which tool is running, when each completes)
    - Support `--verbose` flag for DEBUG level with detailed finding output
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 13.4 Write property test for partial results on tool failure
    - **Property 21: Partial results on tool failure**
    - **Validates: Requirements 13.1**

  - [x] 13.5 Write property test for skipped analysis noted in report
    - **Property 22: Skipped analysis noted in report**
    - **Validates: Requirements 13.2**

  - [x] 13.6 Write property test for run identifier in log entries
    - **Property 23: Run identifier in log entries**
    - **Validates: Requirements 13.4, 14.3**

  - [x] 13.7 Write unit tests for agent creation and error handling
    - Test agent creation with default and custom model providers
    - Test retry logic with mocked LLM failures
    - Test partial results when individual tools fail
    - _Requirements: 8.1, 8.2, 8.5, 13.1, 13.2, 13.3_

- [x] 14. Implement CLI entry point and security
  - [x] 14.1 Implement the CLI with click
    - Create `mwaa_analyzer_agent/cli.py` with `click` command group and `analyze` subcommand
    - Implement all CLI options: `--source-type`, `--endpoint`, `--token`, `--environment-name`, `--region`, `--path`, `--output-format`, `--output-file`, `--target-mwaa-version`, `--verbose`
    - Validate flag combinations: `api` requires `--endpoint` and `--token`; `mwaa` requires `--environment-name` and `--region`; `filesystem` requires `--path`
    - Display descriptive error messages for invalid flag combinations
    - Wire CLI to connector factory, agent, and report output (stdout or file)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [x] 14.2 Implement credential security
    - Accept credentials via environment variables, CLI flags, or AWS credential chain
    - Hold credentials only in memory for the duration of the analysis
    - Clear credential values from memory on completion
    - Display warning when credentials are provided via CLI flags
    - Ensure credentials do not appear in logs, reports, or telemetry
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x] 14.3 Write property test for no credentials in output artifacts
    - **Property 19: No credentials in output artifacts**
    - **Validates: Requirements 11.1**

  - [x] 14.4 Write property test for CLI invalid flag combination error
    - **Property 20: CLI invalid flag combination error**
    - **Validates: Requirements 10.8**

  - [x] 14.5 Write unit tests for CLI
    - Test each source type with valid and invalid flag combinations
    - Test output format and output file options
    - Test credential warning display
    - Test verbose flag behavior
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.5_

- [x] 15. Checkpoint - Verify agent, CLI, and security
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Integration wiring and end-to-end flow
  - [x] 16.1 Wire the complete analysis pipeline
    - Connect CLI → connector factory → environment data retrieval → agent invocation → tool execution → recommendation → report generation → output
    - Integrate telemetry collection at analysis start and completion
    - Ensure the `mwaa-analyzer` console script entry point is configured in `pyproject.toml`
    - _Requirements: 6.5, 10.1, 10.2, 10.3, 10.4_

  - [x] 16.2 Write integration tests for the full analysis pipeline
    - Test filesystem source type end-to-end with sample Airflow project files
    - Test API source type with mocked httpx transport
    - Test MWAA source type with moto-mocked boto3 client
    - Mock the Bedrock model provider to return deterministic responses
    - Verify report output contains expected sections for each recommendation type
    - _Requirements: 1.1, 1.2, 1.3, 6.1, 7.1, 10.2, 10.3, 10.4_

- [x] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 23 universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- All code uses Python with the Strands Agents SDK, click, httpx, boto3, packaging, Jinja2, pytest, and hypothesis
