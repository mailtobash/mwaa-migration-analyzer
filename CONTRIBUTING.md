# Contributing to MWAA Analyzer Agent

Thank you for your interest in contributing to the MWAA Analyzer Agent! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git

### Getting Started

1. Clone the repository:

```bash
git clone <repository-url>
cd mwaa-analyzer-agent
```

2. Run the setup script to create a virtual environment and install dependencies:

```bash
./scripts/setup.sh
```

This creates a `.venv/` directory at the repository root with all runtime dependencies installed.

3. Install development dependencies (done automatically on first test run):

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Project Structure

This project is structured as a runnable sample tool, not a pip-installable library. Source code lives in `src/` and is accessed via `PYTHONPATH` rather than package installation.

```
src/              # Source code (flat module layout)
data/             # Compatibility data and report templates
docs/             # User-facing documentation
examples/         # Sample Airflow projects for testing
scripts/          # Setup, run, and test scripts
tests/            # Unit, property, and integration tests
```

### Running the Analyzer

Use the run script to invoke the CLI:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

The run script handles `PYTHONPATH` configuration and virtual environment activation automatically.

### Running Tests

Use the test script to run the full test suite:

```bash
./scripts/test.sh
```

Run specific test categories:

```bash
./scripts/test.sh tests/unit/          # Unit tests
./scripts/test.sh tests/property/      # Property-based tests
./scripts/test.sh tests/integration/   # Integration tests
```

The test script automatically installs development dependencies (from `requirements-dev.txt`) if they are not already present.

### Working Without Scripts

If you prefer to run commands directly, set `PYTHONPATH` to include the `src/` directory:

```bash
source .venv/bin/activate
export PYTHONPATH=src:$PYTHONPATH
python -m cli analyze --source-type filesystem --path ./examples/sample-project
python -m pytest tests/
```

## Coding Standards

- Follow PEP 8 style guidelines
- Use type hints for all function signatures
- Write docstrings for all public modules, classes, and functions
- Keep functions focused and small
- Use dataclasses for data structures
- Use enums for fixed sets of values

## Pull Request Guidelines

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure all tests pass (`./scripts/test.sh`)
4. Include a clear description of changes in the PR
5. Reference any related issues

## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.
