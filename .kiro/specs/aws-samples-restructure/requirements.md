# Requirements Document

## Introduction

Restructure the MWAA Analyzer Agent project from a Python library-style package (pip-installable) into an AWS samples-style repository. The goal is to present the tool as a runnable sample/utility with clear documentation, operational guidance, and multi-component organization — not as a distributable Python library. The restructuring preserves all existing functionality while aligning with conventions seen in repositories like `amazon-mwaa-docker-images` and `amazon-mwaa-examples`.

## Glossary

- **Repository**: The top-level Git repository containing all project files
- **Analyzer_CLI**: The command-line interface that users invoke to run the MWAA migration analysis
- **Source_Directory**: The directory containing the core Python source code for the analyzer tool
- **Documentation_Directory**: The directory containing user-facing guides, tutorials, and operational documentation
- **Examples_Directory**: The directory containing sample configurations, DAG files, and usage examples
- **Setup_Script**: A shell script or Python script that bootstraps the local environment (creates virtualenv, installs dependencies) without requiring pip install of a package
- **Run_Script**: A shell script that invokes the analyzer tool after environment setup
- **MWAA_Compatibility_Data**: The JSON data files containing provider/package compatibility information for target MWAA versions
- **Report_Templates**: Jinja2 templates used to render analysis reports in Markdown and HTML formats

## Requirements

### Requirement 1: Remove Library Packaging

**User Story:** As a repository maintainer, I want the project to not be structured as a pip-installable library, so that users understand it is a runnable sample tool rather than a distributable package.

#### Acceptance Criteria

1. THE Repository SHALL NOT contain a `pyproject.toml` with a `[build-system]` section that enables `pip install`
2. THE Repository SHALL NOT define `[project.scripts]` entry points for CLI commands
3. THE Repository SHALL use a `requirements.txt` file to declare runtime dependencies
4. THE Repository SHALL use a separate `requirements-dev.txt` file to declare development and testing dependencies
5. WHEN a user clones the Repository, THE Setup_Script SHALL create a Python virtual environment and install dependencies from `requirements.txt`

### Requirement 2: Repository Directory Layout

**User Story:** As a developer exploring the repository, I want a clear multi-component directory structure, so that I can quickly find source code, documentation, examples, and tests.

#### Acceptance Criteria

1. THE Repository SHALL contain a top-level `src/` directory holding the analyzer source code
2. THE Repository SHALL contain a top-level `docs/` directory holding user-facing documentation
3. THE Repository SHALL contain a top-level `examples/` directory holding sample inputs and usage examples
4. THE Repository SHALL contain a top-level `tests/` directory holding all test files
5. THE Repository SHALL contain a top-level `scripts/` directory holding setup and run scripts
6. THE Repository SHALL contain a top-level `data/` directory holding MWAA_Compatibility_Data and Report_Templates

### Requirement 3: Setup and Run Scripts

**User Story:** As a user, I want simple scripts to set up and run the analyzer, so that I do not need to understand Python packaging to use the tool.

#### Acceptance Criteria

1. THE Repository SHALL provide a `scripts/setup.sh` script for Linux and macOS environments
2. WHEN a user executes `scripts/setup.sh`, THE Setup_Script SHALL create a Python virtual environment in a `.venv` directory at the repository root
3. WHEN a user executes `scripts/setup.sh`, THE Setup_Script SHALL install all runtime dependencies into the virtual environment
4. THE Repository SHALL provide a `scripts/run.sh` script that activates the virtual environment and invokes the Analyzer_CLI
5. WHEN a user executes `scripts/run.sh` with valid arguments, THE Run_Script SHALL pass all arguments to the Analyzer_CLI entry point
6. IF the virtual environment does not exist when `scripts/run.sh` is executed, THEN THE Run_Script SHALL display an error message instructing the user to run `scripts/setup.sh` first

### Requirement 4: Source Code Organization

**User Story:** As a developer, I want the source code organized under a single `src/` directory with clear module boundaries, so that the code is easy to navigate without Python package installation.

#### Acceptance Criteria

1. THE Source_Directory SHALL contain the CLI entry point module
2. THE Source_Directory SHALL contain the agent orchestration module
3. THE Source_Directory SHALL contain a `connectors/` subdirectory with all environment connector modules
4. THE Source_Directory SHALL contain a `tools/` subdirectory with all analyzer tool modules
5. THE Source_Directory SHALL contain a `models.py` module defining all data structures
6. THE Source_Directory SHALL preserve the existing module interfaces and public function signatures

### Requirement 5: Documentation Structure

**User Story:** As a user evaluating the tool, I want comprehensive documentation organized by purpose, so that I can quickly understand how to set up, configure, and use the analyzer.

#### Acceptance Criteria

1. THE Documentation_Directory SHALL contain a `getting-started.md` guide covering prerequisites, setup, and first run
2. THE Documentation_Directory SHALL contain a `usage-guide.md` document describing all CLI options and source types
3. THE Documentation_Directory SHALL contain an `architecture.md` document explaining the system design and component interactions
4. THE Documentation_Directory SHALL contain a `troubleshooting.md` document covering common issues and solutions
5. THE Repository SHALL contain a top-level `README.md` that provides an overview and links to documentation in the Documentation_Directory

### Requirement 6: Examples Directory

**User Story:** As a user, I want example configurations and sample inputs, so that I can quickly test the analyzer without connecting to a real Airflow environment.

#### Acceptance Criteria

1. THE Examples_Directory SHALL contain a sample filesystem project structure with example DAG files
2. THE Examples_Directory SHALL contain a sample `airflow.cfg` configuration file
3. THE Examples_Directory SHALL contain a sample `requirements.txt` representing typical Airflow dependencies
4. THE Examples_Directory SHALL contain a `README.md` explaining how to use the examples with the analyzer

### Requirement 7: Test Execution Without Package Installation

**User Story:** As a developer, I want to run the test suite without installing the project as a Python package, so that the development workflow matches the non-library structure.

#### Acceptance Criteria

1. WHEN a developer runs the test suite, THE tests SHALL execute using path-based imports from the `src/` directory
2. THE Repository SHALL provide a `scripts/test.sh` script that configures the Python path and invokes pytest
3. WHEN `scripts/test.sh` is executed, THE script SHALL install development dependencies if not already present
4. THE test directory structure SHALL preserve the existing separation of unit, property, and integration tests

### Requirement 8: Top-Level Repository Files

**User Story:** As a user or contributor, I want standard AWS samples repository files at the top level, so that the project follows AWS open-source conventions.

#### Acceptance Criteria

1. THE Repository SHALL contain a `LICENSE` file with the Apache-2.0 license text
2. THE Repository SHALL contain a `NOTICE` file with attribution information
3. THE Repository SHALL contain a `CONTRIBUTING.md` file with contribution guidelines updated for the non-library workflow
4. THE Repository SHALL contain a `CODE_OF_CONDUCT.md` file
5. THE Repository SHALL contain a `.gitignore` file appropriate for Python projects

### Requirement 9: Preserve Existing Functionality

**User Story:** As a user of the existing tool, I want all current features to continue working after the restructuring, so that the migration does not break any capabilities.

#### Acceptance Criteria

1. THE Analyzer_CLI SHALL continue to support the `filesystem`, `api`, and `mwaa` source types
2. THE Analyzer_CLI SHALL continue to support `markdown`, `json`, and `html` output formats
3. THE Analyzer_CLI SHALL continue to support all existing command-line flags and options
4. THE telemetry subsystem SHALL continue to function with opt-out support via the `MWAA_ANALYZER_TELEMETRY_OPT_OUT` environment variable
5. THE agent orchestration module SHALL continue to support both interactive agent mode and deterministic pipeline mode
6. WHEN the analyzer produces a report, THE report SHALL contain the same sections and content as the current implementation

### Requirement 10: Data and Template Files

**User Story:** As a maintainer, I want compatibility data and report templates stored in a dedicated top-level directory, so that they are easy to find and update independently of source code.

#### Acceptance Criteria

1. THE Repository SHALL store MWAA_Compatibility_Data JSON files in `data/compatibility/`
2. THE Repository SHALL store Report_Templates in `data/templates/`
3. WHEN the analyzer loads compatibility data, THE Source_Directory modules SHALL reference the `data/` directory relative to the repository root
4. WHEN the analyzer renders a report, THE Source_Directory modules SHALL reference templates in `data/templates/`

### Requirement 11: Python Path Configuration

**User Story:** As a developer, I want the project to work correctly without `pip install -e .`, so that the non-library structure does not cause import errors.

#### Acceptance Criteria

1. THE Run_Script SHALL configure `PYTHONPATH` to include the `src/` directory before invoking the Analyzer_CLI
2. THE test script SHALL configure `PYTHONPATH` to include the `src/` directory before invoking pytest
3. WHEN a user imports modules from the source code, THE imports SHALL use the module names directly without a top-level package namespace
4. IF a user attempts to run the analyzer without using the provided scripts, THEN THE Analyzer_CLI SHALL display a clear error message about the required Python path configuration
