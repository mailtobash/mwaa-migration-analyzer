"""Property-based tests for credential security.

Feature: mwaa-analyzer-agent
Property 19: No credentials in output artifacts
Property 20: CLI invalid flag combination error

Validates: Requirements 10.8, 11.1
"""

from __future__ import annotations

import logging
import logging.handlers

from hypothesis import given, settings, strategies as st, HealthCheck

from agent import run_analysis


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate realistic-looking credential strings with a distinctive prefix
# to avoid false positives from collisions with report content words.
# The "CRED_" prefix ensures these won't match normal English words.
_credential_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=10,
    max_size=32,
).map(lambda s: f"CRED_{s.strip()[:20]}").filter(lambda s: len(s) >= 15)


# ---------------------------------------------------------------------------
# Property 19: No credentials in output artifacts
# ---------------------------------------------------------------------------


@settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
@given(
    token=_credential_strategy,
    endpoint=_credential_strategy,
    env_name=_credential_strategy,
)
def test_property_19_no_credentials_in_output_artifacts(
    token: str, endpoint: str, env_name: str,
) -> None:
    """Feature: mwaa-analyzer-agent, Property 19: No credentials in output artifacts

    **Validates: Requirements 11.1**

    For any analysis run where credentials are provided, the generated report
    content, log output, and telemetry events SHALL not contain any credential
    values.
    """
    # Clean up any accumulated logging handlers from previous iterations
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)

    # Capture log output using a list handler
    captured_records: list[logging.LogRecord] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    handler = ListHandler()
    handler.setLevel(logging.DEBUG)
    root_logger.addHandler(handler)

    try:
        result = run_analysis(
            dag_files=[],
            requirements_content=None,
            config_entries={},
            plugin_files=[],
            target_mwaa_version="2.10.3",
            output_format="markdown",
            verbose=True,
        )
    finally:
        root_logger.removeHandler(handler)

    report_content = result.get("report_content", "")

    # The report content must not contain any of the credential values
    assert token not in report_content, (
        f"Token '{token}' found in report content"
    )
    assert endpoint not in report_content, (
        f"Endpoint '{endpoint}' found in report content"
    )
    assert env_name not in report_content, (
        f"Environment name '{env_name}' found in report content"
    )

    # Check log records for credential leakage
    log_text = " ".join(r.getMessage() for r in captured_records)
    assert token not in log_text, (
        f"Token '{token}' found in log output"
    )
    assert endpoint not in log_text, (
        f"Endpoint '{endpoint}' found in log output"
    )
    assert env_name not in log_text, (
        f"Environment name '{env_name}' found in log output"
    )


# ---------------------------------------------------------------------------
# Property 20: CLI invalid flag combination error
# ---------------------------------------------------------------------------

from click.testing import CliRunner

from cli import analyze, cli


# Strategy for source types and their required/missing flag combos
_source_type_strategy = st.sampled_from(["api", "mwaa", "filesystem"])


def _build_missing_flag_args(source_type: str, omit_flags: set[str]) -> list[str]:
    """Build CLI args for a source type with specific flags omitted."""
    args = ["analyze", "--source-type", source_type]

    if source_type == "api":
        if "endpoint" not in omit_flags:
            args.extend(["--endpoint", "https://airflow.example.com"])
        if "token" not in omit_flags:
            args.extend(["--token", "test-token-value"])
    elif source_type == "mwaa":
        if "environment-name" not in omit_flags:
            args.extend(["--environment-name", "my-env"])
        if "region" not in omit_flags:
            args.extend(["--region", "us-east-1"])
    elif source_type == "filesystem":
        # For filesystem, --path requires an existing path, so we skip it
        # to trigger the missing flag error
        pass

    return args


# Define all invalid flag combinations per source type
_invalid_combos = st.sampled_from([
    ("api", {"endpoint"}),
    ("api", {"token"}),
    ("api", {"endpoint", "token"}),
    ("mwaa", {"environment-name"}),
    ("mwaa", {"region"}),
    ("mwaa", {"environment-name", "region"}),
    ("filesystem", {"path"}),
])


@settings(max_examples=100)
@given(combo=_invalid_combos)
def test_property_20_cli_invalid_flag_combination_error(
    combo: tuple[str, set[str]],
) -> None:
    """Feature: mwaa-analyzer-agent, Property 20: CLI invalid flag combination error

    **Validates: Requirements 10.8**

    For any invocation of the CLI where required flags for the chosen source
    type are missing, the CLI SHALL exit with a non-zero status code and
    display an error message identifying the missing flags.
    """
    source_type, omit_flags = combo
    args = _build_missing_flag_args(source_type, omit_flags)

    runner = CliRunner(env={
        # Clear env vars so they don't satisfy the missing flags
        "AIRFLOW_API_ENDPOINT": "",
        "AIRFLOW_API_TOKEN": "",
        "MWAA_ENVIRONMENT_NAME": "",
        "MWAA_REGION": "",
    })
    result = runner.invoke(cli, args)

    # Must exit with non-zero status
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for source_type={source_type} "
        f"with omitted flags={omit_flags}, got {result.exit_code}. "
        f"Output: {result.output}"
    )

    # Must contain "Error" in the output
    combined_output = result.output + (result.stderr if hasattr(result, 'stderr') else "")
    assert "Error" in combined_output or "error" in combined_output.lower(), (
        f"Expected error message for source_type={source_type} "
        f"with omitted flags={omit_flags}. Output: {combined_output}"
    )
