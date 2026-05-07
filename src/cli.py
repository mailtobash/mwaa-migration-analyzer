"""CLI entry point for the MWAA Analyzer Agent.

Provides the ``mwaa-analyzer`` command group with the ``analyze`` subcommand.
Handles flag validation, credential security, connector wiring, and report output.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.1, 11.2, 11.3, 11.4, 11.5
"""

from __future__ import annotations

import logging
import os
import sys
import time

try:
    import click

    from agent import run_analysis
    from connectors import create_connector
    from models import SourceType, TelemetryEvent
    from telemetry import TelemetryCollector

    _IMPORT_ERROR: ImportError | None = None
except ImportError as e:
    _IMPORT_ERROR = e
    if __name__ == "__main__":
        print(
            "Error: Could not import required modules. "
            "Please use 'scripts/run.sh' to run the analyzer, "
            "or set PYTHONPATH to include the 'src/' directory.",
            file=sys.stderr,
        )
        sys.exit(1)

logger = logging.getLogger(__name__)

# Environment variable names for credential inputs
_ENV_AIRFLOW_ENDPOINT = "AIRFLOW_API_ENDPOINT"
_ENV_AIRFLOW_TOKEN = "AIRFLOW_API_TOKEN"
_ENV_MWAA_ENVIRONMENT_NAME = "MWAA_ENVIRONMENT_NAME"
_ENV_MWAA_REGION = "MWAA_REGION"

_CREDENTIAL_CLI_WARNING = (
    "WARNING: Credentials provided via CLI flags may appear in shell history. "
    "Consider using environment variables instead:\n"
    "  export AIRFLOW_API_ENDPOINT=<url>\n"
    "  export AIRFLOW_API_TOKEN=<token>\n"
    "  export MWAA_ENVIRONMENT_NAME=<name>\n"
    "  export MWAA_REGION=<region>\n"
)


def _resolve_credentials(
    source_type: str,
    endpoint: str | None,
    token: str | None,
    environment_name: str | None,
    region: str | None,
    path: str | None,
) -> tuple[dict[str, str | None], bool]:
    """Resolve credentials from CLI flags and environment variables.

    CLI flags take precedence over environment variables. Returns a dict
    of resolved values and a boolean indicating whether any credential
    was supplied via a CLI flag (triggering a security warning).

    Returns:
        A tuple of (resolved_values_dict, credentials_from_cli_flag).
    """
    cli_flag_used = False

    resolved: dict[str, str | None] = {
        "endpoint": None,
        "token": None,
        "environment_name": None,
        "region": None,
        "path": path,
    }

    if source_type == "api":
        # Resolve endpoint
        if endpoint is not None:
            resolved["endpoint"] = endpoint
            cli_flag_used = True
        else:
            resolved["endpoint"] = os.environ.get(_ENV_AIRFLOW_ENDPOINT)

        # Resolve token
        if token is not None:
            resolved["token"] = token
            cli_flag_used = True
        else:
            resolved["token"] = os.environ.get(_ENV_AIRFLOW_TOKEN)

    elif source_type == "mwaa":
        # Resolve environment name
        if environment_name is not None:
            resolved["environment_name"] = environment_name
            cli_flag_used = True
        else:
            resolved["environment_name"] = os.environ.get(_ENV_MWAA_ENVIRONMENT_NAME)

        # Resolve region
        if region is not None:
            resolved["region"] = region
            cli_flag_used = True
        else:
            resolved["region"] = os.environ.get(_ENV_MWAA_REGION)

    return resolved, cli_flag_used


def _validate_flags(
    source_type: str,
    resolved: dict[str, str | None],
) -> list[str]:
    """Validate that required flags are present for the chosen source type.

    Returns:
        A list of error messages. Empty list means validation passed.
    """
    errors: list[str] = []

    if source_type == "api":
        if not resolved.get("endpoint"):
            errors.append(
                "--endpoint (or AIRFLOW_API_ENDPOINT env var) is required "
                "when --source-type is 'api'"
            )
        if not resolved.get("token"):
            errors.append(
                "--token (or AIRFLOW_API_TOKEN env var) is required "
                "when --source-type is 'api'"
            )
    elif source_type == "mwaa":
        if not resolved.get("environment_name"):
            errors.append(
                "--environment-name (or MWAA_ENVIRONMENT_NAME env var) is required "
                "when --source-type is 'mwaa'"
            )
        if not resolved.get("region"):
            errors.append(
                "--region (or MWAA_REGION env var) is required "
                "when --source-type is 'mwaa'"
            )
    elif source_type == "filesystem":
        if not resolved.get("path"):
            errors.append(
                "--path is required when --source-type is 'filesystem'"
            )

    return errors


def _collect_environment_data(connector):
    """Collect all environment data from a connector into a dict suitable for run_analysis.

    Args:
        connector: An EnvironmentConnector instance (already connected).

    Returns:
        A dict with keys matching run_analysis parameters.
    """
    dags = connector.get_dags()
    requirements = connector.get_requirements()
    configuration = connector.get_configuration()
    plugins = connector.get_plugins()
    metadata = connector.get_metadata()

    return {
        "dag_files": [{"filename": d.filename, "content": d.content} for d in dags],
        "requirements_content": requirements,
        "config_entries": configuration,
        "plugin_files": [{"filename": p.filename, "content": p.content} for p in plugins],
        "metadata_obj": metadata,
    }


def _clear_credentials(resolved: dict[str, str | None]) -> None:
    """Clear credential values from the resolved dict to free them from memory.

    Requirement 11.3: Clear credential values from memory on completion.
    """
    for key in ("endpoint", "token", "environment_name", "region"):
        resolved[key] = None


@click.group()
def cli():
    """MWAA Analyzer Agent - AI-powered Airflow migration analysis."""
    pass


@cli.command()
@click.option(
    "--source-type",
    type=click.Choice(["api", "mwaa", "filesystem"]),
    required=True,
    help="Source type for the Airflow environment.",
)
@click.option(
    "--endpoint",
    default=None,
    help="Airflow REST API endpoint URL.",
)
@click.option(
    "--token",
    default=None,
    help="Airflow REST API auth token.",
)
@click.option(
    "--environment-name",
    default=None,
    help="MWAA environment name.",
)
@click.option(
    "--region",
    default=None,
    help="AWS region for MWAA.",
)
@click.option(
    "--path",
    default=None,
    type=click.Path(exists=True),
    help="Local filesystem path containing Airflow project files.",
)
@click.option(
    "--output-format",
    type=click.Choice(["markdown", "json", "html"]),
    default="markdown",
    help="Output report format.",
)
@click.option(
    "--output-file",
    default=None,
    type=click.Path(),
    help="Output file path. Defaults to stdout.",
)
@click.option(
    "--target-mwaa-version",
    default="2.10.3",
    help="Target MWAA Airflow version.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
def analyze(
    source_type: str,
    endpoint: str | None,
    token: str | None,
    environment_name: str | None,
    region: str | None,
    path: str | None,
    output_format: str,
    output_file: str | None,
    target_mwaa_version: str,
    verbose: bool,
) -> None:
    """Analyze an Airflow environment for MWAA migration."""
    # Step 1: Resolve credentials from CLI flags / env vars
    resolved, cli_flag_used = _resolve_credentials(
        source_type, endpoint, token, environment_name, region, path
    )

    # Step 2: Validate required flags
    errors = _validate_flags(source_type, resolved)
    if errors:
        for err in errors:
            click.echo(f"Error: {err}", err=True)
        sys.exit(1)

    # Step 3: Show credential warning if credentials were provided via CLI flags
    if cli_flag_used:
        click.echo(_CREDENTIAL_CLI_WARNING, err=True)

    # Step 4: Show telemetry first-run notice
    telemetry = TelemetryCollector(endpoint="https://telemetry.example.com")
    telemetry.show_first_run_notice()

    # Step 5: Create the appropriate connector
    source_type_enum = SourceType(source_type)
    connector_kwargs: dict[str, object] = {}
    if source_type == "api":
        connector_kwargs["endpoint"] = resolved["endpoint"]
        connector_kwargs["token"] = resolved["token"]
    elif source_type == "mwaa":
        connector_kwargs["environment_name"] = resolved["environment_name"]
        connector_kwargs["region"] = resolved["region"]
    elif source_type == "filesystem":
        connector_kwargs["path"] = resolved["path"]

    # Track timing for telemetry
    start_time = time.monotonic()
    error_category: str | None = None

    try:
        connector = create_connector(source_type_enum, **connector_kwargs)

        # Step 6: Connect and retrieve environment data
        connector.connect()
        env_data = _collect_environment_data(connector)

        # Record analysis-start telemetry event
        dag_count = len(env_data["dag_files"])
        telemetry.record_event(
            TelemetryEvent(
                event_type="analysis_start",
                source_type=source_type,
                dag_count=dag_count,
            )
        )

        # Step 7: Run analysis
        result = run_analysis(
            dag_files=env_data["dag_files"],
            requirements_content=env_data["requirements_content"],
            config_entries=env_data["config_entries"],
            plugin_files=env_data["plugin_files"],
            target_mwaa_version=target_mwaa_version,
            output_format=output_format,
            metadata={
                "source_type": source_type,
                "target_mwaa_version": target_mwaa_version,
                "tool_version": "0.1.0",
            },
            verbose=verbose,
        )

        report_content = result.get("report_content", "")
        recommendation = result.get("recommendation")

        # Record analysis-complete telemetry event
        duration = time.monotonic() - start_time
        telemetry.record_event(
            TelemetryEvent(
                event_type="analysis_complete",
                source_type=source_type,
                recommendation=recommendation,
                dag_count=dag_count,
                duration_seconds=round(duration, 2),
            )
        )

        # Step 8: Write report to stdout or file
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(report_content)
            click.echo(f"Report written to {output_file}", err=True)
        else:
            click.echo(report_content)

    except (FileNotFoundError, NotADirectoryError, ConnectionError, TimeoutError, ValueError, PermissionError) as exc:
        error_category = type(exc).__name__
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:
        error_category = type(exc).__name__
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(1)
    finally:
        # Record error telemetry if an error occurred
        if error_category is not None:
            duration = time.monotonic() - start_time
            telemetry.record_event(
                TelemetryEvent(
                    event_type="analysis_error",
                    source_type=source_type,
                    error_category=error_category,
                    duration_seconds=round(duration, 2),
                )
            )

        # Flush all buffered telemetry events
        telemetry.flush()

        # Step 9: Clear credentials from memory (Requirement 11.3)
        _clear_credentials(resolved)


if __name__ == "__main__":
    cli()
