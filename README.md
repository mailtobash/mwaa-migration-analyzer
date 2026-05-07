# MWAA Analyzer Agent

AI-powered CLI tool that analyzes Apache Airflow environments and produces migration recommendation reports for [Amazon MWAA](https://aws.amazon.com/managed-workflows-for-apache-airflow/).

## Overview

The MWAA Analyzer Agent connects to your existing Airflow environment, inspects DAGs, plugins, configurations, and dependencies, and uses an AI agent (built on the [Strands Agents SDK](https://strandsagents.com/) with Amazon Bedrock) to determine one of three migration outcomes:

- **Lift and Shift** — Direct migration with minimal changes
- **Lift and Modernize** — Migration requiring refactoring or adaptation
- **Not Possible** — Migration blocked by incompatible features

## Quick Start

### Setup

```bash
./scripts/setup.sh
```

This creates a Python virtual environment in `.venv/` and installs all runtime dependencies.

### Run an Analysis

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

## Usage

### Analyze a local Airflow project

```bash
./scripts/run.sh analyze --source-type filesystem --path /path/to/airflow/project
```

### Analyze via Airflow REST API

```bash
./scripts/run.sh analyze --source-type api --endpoint https://airflow.example.com --token $AIRFLOW_TOKEN
```

### Analyze an Amazon MWAA environment

```bash
./scripts/run.sh analyze --source-type mwaa --environment-name my-env --region us-east-1
```

### Options

| Flag | Description |
|---|---|
| `--source-type` | Source type: `api`, `mwaa`, or `filesystem` (required) |
| `--endpoint` | Airflow REST API endpoint URL (required for `api`) |
| `--token` | Airflow REST API auth token (required for `api`) |
| `--environment-name` | MWAA environment name (required for `mwaa`) |
| `--region` | AWS region for MWAA (required for `mwaa`) |
| `--path` | Local filesystem path (required for `filesystem`) |
| `--output-format` | Output format: `markdown`, `json`, or `html` (default: `markdown`) |
| `--output-file` | Write report to file instead of stdout |
| `--target-mwaa-version` | Target MWAA Airflow version (default: `2.10.3`) |
| `--verbose` | Enable debug logging |

## Documentation

- [Getting Started](docs/getting-started.md) — Prerequisites, setup, and first run
- [Usage Guide](docs/usage-guide.md) — All CLI options, source types, and output formats
- [Architecture](docs/architecture.md) — System design and component interactions
- [Troubleshooting](docs/troubleshooting.md) — Common issues and solutions

## Report Output

The generated report includes:

- **Executive Summary** — High-level migration assessment
- **Migration Recommendation** — One of the three outcomes with justification
- **Detailed Findings** — Organized by category (DAGs, dependencies, configuration, plugins)
- **Action Items** — Prioritized list of required changes
- **Metadata** — Analysis timestamp, source type, target version, tool version

## Telemetry

The tool collects anonymous usage statistics to help maintainers understand adoption patterns. No personally identifiable information is collected.

To opt out:

```bash
export MWAA_ANALYZER_TELEMETRY_OPT_OUT=true
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and pull request guidelines.

## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
