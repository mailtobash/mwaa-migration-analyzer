# Architecture

## Overview

The MWAA Analyzer Agent is an AI-powered tool that analyzes Apache Airflow environments and produces migration recommendations for Amazon Managed Workflows for Apache Airflow (MWAA). It uses the [Strands Agents SDK](https://github.com/strands-agents/sdk-python) to implement a tool-based agent pattern.

## System Design

The system follows a pipeline architecture where data flows from source connectors through analysis tools to a final report:

```
CLI → Connector → Agent → Tools → Report
```

### Data Flow

1. **CLI** parses user input (source type, credentials, output preferences)
2. **Connector** retrieves environment data (DAGs, requirements, config, plugins)
3. **Agent** orchestrates analysis by invoking each tool in sequence
4. **Tools** analyze specific aspects and produce compatibility findings
5. **Report Generator** aggregates findings, determines a recommendation, and renders the output

## Key Components

### CLI (`src/cli.py`)

Entry point for the application. Handles argument parsing, credential resolution (from flags or environment variables), connector creation, and report output. Supports `markdown`, `json`, and `html` output formats.

### Agent (`src/agent.py`)

Orchestrates the analysis pipeline. Provides two execution modes:

- **Agent mode** — uses the Strands SDK to run an LLM-driven analysis loop where the model decides which tools to call
- **Deterministic pipeline mode** — calls each tool directly in sequence without LLM involvement

The agent is configured with a system prompt encoding MWAA migration knowledge and compatibility rules.

### Connectors (`src/connectors/`)

Retrieve environment data from different sources:

| Connector | Module | Description |
|-----------|--------|-------------|
| API | `api.py` | Connects to Airflow REST API endpoints |
| MWAA | `mwaa.py` | Connects to AWS MWAA environments via boto3 |
| Filesystem | `filesystem.py` | Reads from a local directory structure |

All connectors implement a common interface: `connect()`, `get_dags()`, `get_requirements()`, `get_configuration()`, `get_plugins()`, `get_metadata()`.

### Tools (`src/tools/`)

Each tool analyzes a specific aspect of the Airflow environment:

| Tool | Module | Purpose |
|------|--------|---------|
| DAG Inspector | `dag_inspector.py` | Analyzes DAG files for incompatible operators, patterns, and anti-patterns |
| Dependency Analyzer | `dependency_analyzer.py` | Checks requirements.txt for version conflicts and incompatible packages |
| Configuration Analyzer | `configuration_analyzer.py` | Evaluates airflow.cfg for unsupported keys and values |
| Plugin Analyzer | `plugin_analyzer.py` | Inspects custom plugins for incompatible patterns |
| Report Generator | `report_generator.py` | Renders findings into the final report using Jinja2 templates |

### Telemetry (`src/telemetry.py`)

Collects anonymous usage statistics. Opt out by setting `MWAA_ANALYZER_TELEMETRY_OPT_OUT=true`. Events are buffered and sent via HTTPS POST; network failures are silently discarded.

## Three-Outcome Decision Framework

After all tools complete, the agent determines exactly one migration recommendation:

| Recommendation | Meaning |
|----------------|---------|
| **Lift and Shift** | All findings are compatible — migrate with minimal or no changes |
| **Lift and Modernize** | Some findings require modification but none are blocking |
| **Not Possible** | One or more findings are incompatible with no known workaround |

The recommendation is determined by the `determine_recommendation()` function in `src/recommendation.py`, which evaluates the aggregate compatibility status of all findings.

## Tool-Based Agent Pattern (Strands SDK)

The Strands Agents SDK enables the tool-use pattern where:

1. An LLM (Claude via Amazon Bedrock) receives a system prompt with domain knowledge
2. The LLM is given access to the analysis tools as callable functions
3. The LLM decides which tools to invoke and in what order
4. Tool results are fed back to the LLM for interpretation
5. The LLM produces a final synthesized report

In deterministic mode, the same tools are called directly without LLM involvement, providing a predictable and faster execution path.
