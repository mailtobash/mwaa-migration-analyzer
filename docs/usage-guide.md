# Usage Guide

## CLI Options

The analyzer is invoked via `./scripts/run.sh analyze` with the following options:

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--source-type` | Yes | — | Source type: `filesystem`, `api`, or `mwaa` |
| `--endpoint` | For `api` | — | Airflow REST API endpoint URL |
| `--token` | For `api` | — | Airflow REST API auth token |
| `--environment-name` | For `mwaa` | — | MWAA environment name |
| `--region` | For `mwaa` | — | AWS region for the MWAA environment |
| `--path` | For `filesystem` | — | Local path to Airflow project files |
| `--output-format` | No | `markdown` | Report format: `markdown`, `json`, or `html` |
| `--output-file` | No | stdout | File path to write the report to |
| `--target-mwaa-version` | No | `2.10.3` | Target MWAA Airflow version |
| `--verbose` | No | `false` | Enable debug logging |

## Source Types

### Filesystem

Analyze a local Airflow project directory containing DAGs, plugins, requirements, and configuration:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project
```

The directory should contain any combination of:
- `dags/` — DAG Python files
- `plugins/` — Custom operator/hook/sensor files
- `requirements.txt` — Python dependencies
- `airflow.cfg` — Airflow configuration

### API

Connect to a running Airflow instance via its REST API:

```bash
./scripts/run.sh analyze --source-type api \
  --endpoint https://airflow.example.com/api/v1 \
  --token <your-api-token>
```

Or using environment variables (recommended to avoid shell history exposure):

```bash
export AIRFLOW_API_ENDPOINT=https://airflow.example.com/api/v1
export AIRFLOW_API_TOKEN=<your-api-token>
./scripts/run.sh analyze --source-type api
```

### MWAA

Connect directly to an Amazon MWAA environment using AWS credentials:

```bash
./scripts/run.sh analyze --source-type mwaa \
  --environment-name my-mwaa-env \
  --region us-east-1
```

Or using environment variables:

```bash
export MWAA_ENVIRONMENT_NAME=my-mwaa-env
export MWAA_REGION=us-east-1
./scripts/run.sh analyze --source-type mwaa
```

This source type uses the standard AWS credential chain (environment variables, `~/.aws/credentials`, IAM role, etc.).

## Output Formats

### Markdown (default)

Human-readable report suitable for documentation or review:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project --output-format markdown
```

### JSON

Machine-readable structured output for integration with other tools:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project --output-format json
```

### HTML

Formatted HTML report for sharing via browser:

```bash
./scripts/run.sh analyze --source-type filesystem --path ./examples/sample-project --output-format html --output-file report.html
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `MWAA_ANALYZER_TELEMETRY_OPT_OUT` | Set to `true` to disable anonymous telemetry collection |
| `AIRFLOW_API_ENDPOINT` | Airflow REST API endpoint URL (alternative to `--endpoint` flag) |
| `AIRFLOW_API_TOKEN` | Airflow REST API auth token (alternative to `--token` flag) |
| `MWAA_ENVIRONMENT_NAME` | MWAA environment name (alternative to `--environment-name` flag) |
| `MWAA_REGION` | AWS region for MWAA (alternative to `--region` flag) |

CLI flags take precedence over environment variables when both are provided.
