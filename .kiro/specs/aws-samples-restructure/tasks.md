# Implementation Plan: AWS Samples Restructure

## Overview

Restructure the MWAA Analyzer Agent from a pip-installable Python library into an AWS samples-style repository. This involves moving source code to `src/`, data files to `data/`, creating shell scripts, documentation, examples, and updating all imports to use the flat module layout.

## Tasks

- [x] 1. Create new directory structure and dependency files
  - [x] 1.1 Create `requirements.txt` with runtime dependencies extracted from `pyproject.toml`
    - Include: strands-agents>=0.1, strands-agents-builder>=0.1, click>=8.1, httpx>=0.27, boto3>=1.34, packaging>=24.0, jinja2>=3.1
    - _Requirements: 1.3_
  - [x] 1.2 Create `requirements-dev.txt` with development dependencies
    - Include `-r requirements.txt` and: hypothesis>=6.100, pytest>=8.0, pytest-mock>=3.12, moto>=5.0
    - _Requirements: 1.4_
  - [x] 1.3 Create `pytest.ini` with test configuration
    - Define testpaths = tests and markers for unit, property, and integration tests
    - _Requirements: 7.4_
  - [x] 1.4 Create top-level directory structure: `src/`, `src/connectors/`, `src/tools/`, `data/compatibility/`, `data/templates/`, `docs/`, `examples/sample-project/dags/`, `examples/sample-project/plugins/`, `scripts/`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 2. Move source code to `src/` directory
  - [x] 2.1 Move core modules to `src/`
    - Copy `mwaa_analyzer_agent/cli.py` → `src/cli.py`
    - Copy `mwaa_analyzer_agent/agent.py` → `src/agent.py`
    - Copy `mwaa_analyzer_agent/models.py` → `src/models.py`
    - Copy `mwaa_analyzer_agent/recommendation.py` → `src/recommendation.py`
    - Copy `mwaa_analyzer_agent/telemetry.py` → `src/telemetry.py`
    - _Requirements: 4.1, 4.2, 4.5_
  - [x] 2.2 Move connectors to `src/connectors/`
    - Copy `mwaa_analyzer_agent/connectors/__init__.py` → `src/connectors/__init__.py`
    - Copy `mwaa_analyzer_agent/connectors/api.py` → `src/connectors/api.py`
    - Copy `mwaa_analyzer_agent/connectors/filesystem.py` → `src/connectors/filesystem.py`
    - Copy `mwaa_analyzer_agent/connectors/mwaa.py` → `src/connectors/mwaa.py`
    - _Requirements: 4.3_
  - [x] 2.3 Move tools to `src/tools/`
    - Copy `mwaa_analyzer_agent/tools/__init__.py` → `src/tools/__init__.py`
    - Copy `mwaa_analyzer_agent/tools/configuration_analyzer.py` → `src/tools/configuration_analyzer.py`
    - Copy `mwaa_analyzer_agent/tools/dag_inspector.py` → `src/tools/dag_inspector.py`
    - Copy `mwaa_analyzer_agent/tools/dependency_analyzer.py` → `src/tools/dependency_analyzer.py`
    - Copy `mwaa_analyzer_agent/tools/plugin_analyzer.py` → `src/tools/plugin_analyzer.py`
    - Copy `mwaa_analyzer_agent/tools/report_generator.py` → `src/tools/report_generator.py`
    - _Requirements: 4.4_
  - [x] 2.4 Create `src/data_loader.py` from `mwaa_analyzer_agent/data/loader.py`
    - Update path resolution to use repository-root-relative `data/compatibility/` directory
    - Implement `_get_repo_root()` using REPO_ROOT env var with fallback to `Path(__file__).resolve().parent.parent`
    - _Requirements: 10.3_

- [x] 3. Move data and template files
  - [x] 3.1 Move compatibility data to `data/compatibility/`
    - Copy `mwaa_analyzer_agent/data/2.10.3.json` → `data/compatibility/2.10.3.json`
    - _Requirements: 10.1_
  - [x] 3.2 Move report templates to `data/templates/`
    - Copy `mwaa_analyzer_agent/templates/report.md.j2` → `data/templates/report.md.j2`
    - Copy `mwaa_analyzer_agent/templates/report.html.j2` → `data/templates/report.html.j2`
    - _Requirements: 10.2_

- [x] 4. Update all imports to flat module layout
  - [x] 4.1 Update imports in `src/cli.py`
    - Change `from mwaa_analyzer_agent.X import Y` to `from X import Y`
    - Add `__main__` block: `if __name__ == "__main__": cli()`
    - Add import error guard with helpful error message about PYTHONPATH
    - _Requirements: 11.3, 11.4_
  - [x] 4.2 Update imports in `src/agent.py`
    - Change all `from mwaa_analyzer_agent.X import Y` to `from X import Y`
    - _Requirements: 4.6_
  - [x] 4.3 Update imports in `src/recommendation.py`
    - Change all `from mwaa_analyzer_agent.X import Y` to `from X import Y`
    - _Requirements: 4.6_
  - [x] 4.4 Update imports in `src/telemetry.py`
    - Change all `from mwaa_analyzer_agent.X import Y` to `from X import Y`
    - _Requirements: 4.6_
  - [x] 4.5 Update imports in `src/connectors/` modules
    - Update `__init__.py`, `api.py`, `filesystem.py`, `mwaa.py`
    - Change `from mwaa_analyzer_agent.connectors.X` to `from connectors.X`
    - Change `from mwaa_analyzer_agent.models` to `from models`
    - _Requirements: 4.6_
  - [x] 4.6 Update imports in `src/tools/` modules
    - Update `__init__.py`, all analyzer modules, and `report_generator.py`
    - Change `from mwaa_analyzer_agent.tools.X` to `from tools.X`
    - Change `from mwaa_analyzer_agent.models` to `from models`
    - Change `from mwaa_analyzer_agent.data.loader` to `from data_loader`
    - Update `report_generator.py` template path resolution to use `_get_template_dir()` pointing to `data/templates/`
    - _Requirements: 4.6, 10.4_

- [x] 5. Checkpoint - Verify source code structure
  - Ensure all source files are in place under `src/`, all imports are updated, and no references to `mwaa_analyzer_agent` remain in `src/`. Ask the user if questions arise.

- [x] 6. Create shell scripts
  - [x] 6.1 Create `scripts/setup.sh`
    - Implement virtualenv creation at `.venv/`
    - Install dependencies from `requirements.txt`
    - Make script executable
    - _Requirements: 3.1, 3.2, 3.3_
  - [x] 6.2 Create `scripts/run.sh`
    - Check for `.venv/` existence, error if missing
    - Set `PYTHONPATH` to include `src/`
    - Forward all arguments to `python -m cli`
    - Make script executable
    - _Requirements: 3.4, 3.5, 3.6, 11.1_
  - [x] 6.3 Create `scripts/test.sh`
    - Auto-run setup if `.venv/` missing
    - Install dev dependencies if pytest not available
    - Set `PYTHONPATH` to include `src/`
    - Forward arguments to pytest
    - Make script executable
    - _Requirements: 7.2, 7.3, 11.2_

- [x] 7. Update test imports and configuration
  - [x] 7.1 Update `tests/conftest.py`
    - Add `sys.path.insert(0, str(Path(__file__).parent.parent / "src"))` for IDE support
    - _Requirements: 7.1_
  - [x] 7.2 Update unit test imports
    - Update all files in `tests/unit/` to use flat imports (e.g., `from models import X` instead of `from mwaa_analyzer_agent.models import X`)
    - Update `tests/unit/connectors/` and `tests/unit/tools/` test files
    - _Requirements: 7.1_
  - [x] 7.3 Update property test imports
    - Update all files in `tests/property/` to use flat imports
    - _Requirements: 7.1_
  - [x] 7.4 Update integration test imports
    - Update all files in `tests/integration/` to use flat imports
    - _Requirements: 7.1_

- [x] 8. Create documentation
  - [x] 8.1 Create `docs/getting-started.md`
    - Cover prerequisites (Python 3.11+, AWS credentials for MWAA source type)
    - Document setup instructions using `scripts/setup.sh`
    - Include first analysis run example using the sample project
    - _Requirements: 5.1_
  - [x] 8.2 Create `docs/usage-guide.md`
    - Document all CLI options and flags
    - Describe each source type (filesystem, api, mwaa) with examples
    - Document output formats (markdown, json, html)
    - Document environment variables (MWAA_ANALYZER_TELEMETRY_OPT_OUT)
    - _Requirements: 5.2_
  - [x] 8.3 Create `docs/architecture.md`
    - Explain system design and component interactions
    - Include component diagram description
    - Document data flow from source connectors through analysis to report generation
    - _Requirements: 5.3_
  - [x] 8.4 Create `docs/troubleshooting.md`
    - Cover common issues: import errors, credential issues, connectivity problems
    - Include FAQ section
    - Document PYTHONPATH requirements for direct invocation
    - _Requirements: 5.4_

- [x] 9. Create examples directory
  - [x] 9.1 Create `examples/README.md`
    - Explain how to use the examples with the analyzer
    - Include command to run analysis against the sample project
    - _Requirements: 6.4_
  - [x] 9.2 Create `examples/sample-project/` with sample Airflow files
    - Create `examples/sample-project/dags/example_dag.py` with a simple DAG
    - Create `examples/sample-project/dags/complex_dag.py` with operators and dependencies
    - Create `examples/sample-project/plugins/custom_operator.py` with a sample plugin
    - Create `examples/sample-project/requirements.txt` with typical Airflow dependencies
    - Create `examples/sample-project/airflow.cfg` with sample configuration
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 10. Update top-level repository files
  - [x] 10.1 Update `README.md`
    - Replace pip install instructions with scripts-based workflow
    - Add links to `docs/` files (getting-started, usage-guide, architecture, troubleshooting)
    - Update usage examples to use `./scripts/run.sh`
    - _Requirements: 5.5_
  - [x] 10.2 Update `CONTRIBUTING.md`
    - Replace `pip install -e ".[dev]"` with `scripts/setup.sh` and `scripts/test.sh` workflow
    - Document the non-library development workflow
    - _Requirements: 8.3_
  - [x] 10.3 Create `CODE_OF_CONDUCT.md`
    - Add Amazon Open Source Code of Conduct
    - _Requirements: 8.4_
  - [x] 10.4 Update `.gitignore` for Python project
    - Ensure `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.hypothesis/` are included
    - _Requirements: 8.5_

- [x] 11. Remove old library packaging artifacts
  - [x] 11.1 Remove `pyproject.toml`
    - Delete the file entirely (build-system and project.scripts no longer needed)
    - _Requirements: 1.1, 1.2_
  - [x] 11.2 Remove `mwaa_analyzer_agent/` directory
    - Delete the entire old package directory (all code now lives in `src/`, `data/`)
    - _Requirements: 2.1_

- [x] 12. Final checkpoint - Verify restructuring is complete
  - Ensure all tests pass with `PYTHONPATH=src python -m pytest tests/`, verify no references to `mwaa_analyzer_agent` remain in source or test files, verify all scripts are executable, and ask the user if questions arise.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

## Notes

- No property-based tests are needed for this feature — it is a structural restructuring with no new business logic
- The existing property and unit tests for the analyzer logic remain unchanged (only imports are updated)
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation of the restructuring
- Task 11 (removal of old artifacts) is intentionally last to allow verification before deletion
