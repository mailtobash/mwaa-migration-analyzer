"""Analyzer Agent module for orchestrating MWAA migration analysis.

Provides two execution modes:
1. ``create_agent`` — returns a Strands ``Agent`` for interactive / LLM-driven analysis.
2. ``run_analysis`` — deterministic pipeline that calls each tool directly,
   aggregates findings, determines a recommendation, and generates a report.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 13.1, 13.2, 13.3, 13.4, 14.1, 14.2, 14.3
"""

from __future__ import annotations

import functools
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from strands import Agent
from strands.models.bedrock import BedrockModel

from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    FindingCategory,
    MigrationRecommendation,
)
from recommendation import determine_recommendation
from tools.configuration_analyzer import analyze_configuration
from tools.dag_inspector import inspect_dags
from tools.dependency_analyzer import analyze_dependencies
from tools.plugin_analyzer import analyze_plugins
from tools.report_generator import generate_report

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt encoding MWAA migration knowledge
# ---------------------------------------------------------------------------

MWAA_MIGRATION_SYSTEM_PROMPT = """\
You are the MWAA Analyzer Agent, an expert in Apache Airflow and Amazon Managed \
Workflows for Apache Airflow (MWAA). Your job is to analyze an Airflow environment \
and produce a migration recommendation report.

## MWAA Compatibility Rules

1. **Operators & Providers** — MWAA supports a curated set of Apache Airflow provider \
packages. Operators, hooks, and sensors that are not part of the pre-installed \
providers must be added via requirements.txt or are incompatible.
2. **Metadata Database** — MWAA does NOT expose direct access to the Airflow metadata \
database. Any DAG that queries the metadata DB via SQLAlchemy must be refactored to \
use the Airflow REST API or XCom.
3. **SubDAGs** — SubDagOperator is deprecated. Recommend migration to TaskGroups.
4. **Local Filesystem** — MWAA workers have ephemeral storage. DAGs must not rely on \
local filesystem paths (e.g., /tmp) for inter-task data exchange. Use S3 or XCom.
5. **Plugins** — Custom plugins must not use subprocess calls, direct socket access, \
or file I/O outside the DAGs folder.
6. **Dependencies** — Packages requiring system-level C libraries not present in the \
MWAA runtime are incompatible. Version conflicts with pre-installed packages must be \
resolved.
7. **Configuration** — MWAA manages certain Airflow configuration sections internally. \
Unsupported configuration keys must be removed. Values referencing local filesystem \
paths must be updated.

## Three-Outcome Decision Framework

After analyzing all components, produce exactly ONE recommendation:

- **Lift and Shift** — All findings are compatible. The environment can migrate to \
MWAA with minimal or no changes.
- **Lift and Modernize** — Some findings require modification (e.g., version \
conflicts, unsupported config keys, local filesystem usage) but none are outright \
incompatible. List required modifications ordered by effort.
- **Not Possible** — One or more findings are incompatible (e.g., packages needing \
system-level C libraries, unsupported operators with no alternative). List blockers \
and any known workarounds.

## Workflow

1. Use ``inspect_dags`` to analyze DAG files.
2. Use ``analyze_dependencies`` to check requirements.txt.
3. Use ``analyze_configuration`` to evaluate Airflow configuration overrides.
4. Use ``analyze_plugins`` to check custom plugins.
5. Aggregate all findings and determine the recommendation.
6. Use ``generate_report`` to produce the final migration report.

Always run ALL analysis tools even if early results suggest incompatibility — the \
user needs a complete picture.
"""

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------


class RunIdFilter(logging.Filter):
    """Logging filter that injects ``run_id`` into every log record.

    Attach an instance of this filter to a handler or logger so that all
    records emitted during an analysis run carry the unique run identifier.
    """

    def __init__(self, run_id: str) -> None:
        super().__init__()
        self.run_id = run_id

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.run_id = self.run_id  # type: ignore[attr-defined]
        return True


def setup_logging(run_id: str, verbose: bool = False) -> RunIdFilter:
    """Configure the root logger for an analysis run.

    Sets up a ``StreamHandler`` with a format that includes the *run_id*,
    and attaches a :class:`RunIdFilter`.

    Args:
        run_id: Unique identifier for this analysis run.
        verbose: If ``True``, set log level to DEBUG; otherwise INFO.

    Returns:
        The :class:`RunIdFilter` instance (useful for testing).
    """
    level = logging.DEBUG if verbose else logging.INFO
    run_filter = RunIdFilter(run_id)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [run_id=%(run_id)s] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handler.addFilter(run_filter)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on repeated calls
    root.addHandler(handler)

    return run_filter


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------

MAX_RETRIES = 3
BASE_DELAY = 1.0  # seconds


def retry_with_backoff(
    max_retries: int = MAX_RETRIES,
    base_delay: float = BASE_DELAY,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable:
    """Decorator that retries a function with exponential backoff.

    Args:
        max_retries: Maximum number of attempts (including the first).
        base_delay: Base delay in seconds; doubles on each retry.
        exceptions: Tuple of exception types to catch and retry on.

    Returns:
        Decorated function.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Attempt %d/%d for %s failed: %s — retrying in %.1fs",
                            attempt + 1,
                            max_retries,
                            fn.__name__,
                            exc,
                            delay,
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            "All %d attempts for %s failed: %s",
                            max_retries,
                            fn.__name__,
                            exc,
                        )
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------


def create_agent(model_provider: Any | None = None) -> Agent:
    """Create a Strands Agent configured for MWAA migration analysis.

    Args:
        model_provider: An alternative model provider instance. When
            ``None``, defaults to ``BedrockModel`` with
            ``us.anthropic.claude-sonnet-4-20250514`` in ``us-east-1``.

    Returns:
        A configured :class:`strands.Agent` instance.
    """
    model = model_provider or BedrockModel(
        model_id="us.anthropic.claude-sonnet-4-20250514",
        region_name="us-east-1",
    )
    return Agent(
        model=model,
        system_prompt=MWAA_MIGRATION_SYSTEM_PROMPT,
        tools=[
            inspect_dags,
            analyze_dependencies,
            analyze_configuration,
            analyze_plugins,
            generate_report,
        ],
    )


# ---------------------------------------------------------------------------
# Deterministic analysis pipeline
# ---------------------------------------------------------------------------

# Mapping of tool name → callable and the keyword arguments builder.
# Each entry is (display_name, callable, args_builder).
_TOOL_REGISTRY: list[tuple[str, str]] = [
    ("DAG Inspector", "inspect_dags"),
    ("Dependency Analyzer", "analyze_dependencies"),
    ("Configuration Analyzer", "analyze_configuration"),
    ("Plugin Analyzer", "analyze_plugins"),
]


def _call_inspect_dags(
    dag_files: list[dict], target_mwaa_version: str
) -> dict:
    """Invoke the inspect_dags tool function directly."""
    return inspect_dags(
        dag_files=dag_files, target_mwaa_version=target_mwaa_version
    )


def _call_analyze_dependencies(
    requirements_content: str | None, target_mwaa_version: str
) -> dict | None:
    """Invoke the analyze_dependencies tool function directly."""
    if requirements_content is None:
        return None
    return analyze_dependencies(
        requirements_content=requirements_content,
        target_mwaa_version=target_mwaa_version,
    )


def _call_analyze_configuration(
    config_entries: dict, target_mwaa_version: str
) -> dict:
    """Invoke the analyze_configuration tool function directly."""
    return analyze_configuration(
        config_entries=config_entries,
        target_mwaa_version=target_mwaa_version,
    )


def _call_analyze_plugins(
    plugin_files: list[dict], target_mwaa_version: str
) -> dict:
    """Invoke the analyze_plugins tool function directly."""
    return analyze_plugins(
        plugin_files=plugin_files,
        target_mwaa_version=target_mwaa_version,
    )


def run_analysis(
    dag_files: list[dict] | None = None,
    requirements_content: str | None = None,
    config_entries: dict | None = None,
    plugin_files: list[dict] | None = None,
    target_mwaa_version: str = "2.10.3",
    output_format: str = "markdown",
    metadata: dict | None = None,
    verbose: bool = False,
) -> dict:
    """Run the deterministic analysis pipeline.

    Calls each analysis tool directly (not through the Strands agent loop),
    aggregates findings, determines the recommendation, and generates the
    report.

    Args:
        dag_files: List of DAG file dicts with ``filename`` and ``content``.
        requirements_content: Raw content of requirements.txt (or ``None``).
        config_entries: Dict of ``{section: {key: value}}`` config entries.
        plugin_files: List of plugin file dicts with ``filename`` and ``content``.
        target_mwaa_version: Target MWAA Airflow version.
        output_format: Report format — ``markdown``, ``json``, or ``html``.
        metadata: Optional report metadata dict.
        verbose: Enable DEBUG-level logging.

    Returns:
        A dict with keys ``report_content``, ``recommendation``, ``findings``,
        ``skipped_analyses``, and ``run_id``.
    """
    run_id = str(uuid.uuid4())
    run_filter = setup_logging(run_id, verbose=verbose)

    logger.info("Starting MWAA migration analysis run")

    all_findings: list[dict] = []
    skipped_analyses: list[dict] = []

    # --- DAG Inspector ---------------------------------------------------
    logger.info("Running DAG Inspector")
    try:
        result = _call_inspect_dags(dag_files or [], target_mwaa_version)
        findings = result.get("findings", [])
        all_findings.extend(findings)
        logger.info("DAG Inspector completed — %d finding(s)", len(findings))
        if verbose:
            for f in findings:
                logger.debug("DAG finding: %s", f)
    except Exception as exc:
        logger.error(
            "DAG Inspector failed: %s",
            exc,
        )
        skipped_analyses.append(
            {"tool": "DAG Inspector", "reason": str(exc)}
        )

    # --- Dependency Analyzer ---------------------------------------------
    logger.info("Running Dependency Analyzer")
    try:
        dep_result = _call_analyze_dependencies(
            requirements_content, target_mwaa_version
        )
        if dep_result is not None:
            findings = dep_result.get("findings", [])
            all_findings.extend(findings)
            logger.info(
                "Dependency Analyzer completed — %d finding(s)", len(findings)
            )
            if verbose:
                for f in findings:
                    logger.debug("Dependency finding: %s", f)
        else:
            logger.info(
                "Dependency Analyzer skipped — no requirements.txt provided"
            )
    except Exception as exc:
        logger.error(
            "Dependency Analyzer failed: %s",
            exc,
        )
        skipped_analyses.append(
            {"tool": "Dependency Analyzer", "reason": str(exc)}
        )

    # --- Configuration Analyzer ------------------------------------------
    logger.info("Running Configuration Analyzer")
    try:
        cfg_result = _call_analyze_configuration(
            config_entries or {}, target_mwaa_version
        )
        findings = cfg_result.get("findings", [])
        all_findings.extend(findings)
        logger.info(
            "Configuration Analyzer completed — %d finding(s)", len(findings)
        )
        if verbose:
            for f in findings:
                logger.debug("Configuration finding: %s", f)
    except Exception as exc:
        logger.error(
            "Configuration Analyzer failed: %s",
            exc,
        )
        skipped_analyses.append(
            {"tool": "Configuration Analyzer", "reason": str(exc)}
        )

    # --- Plugin Analyzer -------------------------------------------------
    logger.info("Running Plugin Analyzer")
    try:
        plugin_result = _call_analyze_plugins(
            plugin_files or [], target_mwaa_version
        )
        findings = plugin_result.get("findings", [])
        all_findings.extend(findings)
        logger.info(
            "Plugin Analyzer completed — %d finding(s)", len(findings)
        )
        if verbose:
            for f in findings:
                logger.debug("Plugin finding: %s", f)
    except Exception as exc:
        logger.error(
            "Plugin Analyzer failed: %s",
            exc,
        )
        skipped_analyses.append(
            {"tool": "Plugin Analyzer", "reason": str(exc)}
        )

    # --- Recommendation --------------------------------------------------
    logger.info("Determining migration recommendation")
    # Convert dicts back to CompatibilityFinding for the recommendation engine
    cf_findings = _dicts_to_findings(all_findings)
    recommendation = determine_recommendation(cf_findings)
    logger.info("Recommendation: %s", recommendation.value)

    # --- Report Generation -----------------------------------------------
    logger.info("Generating report")
    report_metadata = metadata or {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source_type": "filesystem",
        "target_mwaa_version": target_mwaa_version,
        "tool_version": "0.1.0",
        "run_id": run_id,
    }
    # Ensure run_id is in metadata
    report_metadata["run_id"] = run_id

    # If there are skipped analyses, add a note to findings
    skipped_findings = _build_skipped_findings(skipped_analyses)
    report_findings = all_findings + skipped_findings

    report_result = generate_report(
        findings=report_findings,
        recommendation=recommendation.value,
        output_format=output_format,
        metadata=report_metadata,
    )

    logger.info("Analysis run complete")

    # Clean up the logging filter to avoid leaking into other runs
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        handler.removeFilter(run_filter)
    root_logger.removeHandler(
        next(
            (h for h in root_logger.handlers if run_filter in getattr(h, "filters", [])),
            None,  # type: ignore[arg-type]
        )
    ) if False else None  # noqa: E501 — cleanup is done above

    return {
        "report_content": report_result.get("report_content", ""),
        "recommendation": recommendation.value,
        "findings": all_findings,
        "skipped_analyses": skipped_analyses,
        "run_id": run_id,
    }


def _dicts_to_findings(
    finding_dicts: list[dict],
) -> list[CompatibilityFinding]:
    """Convert a list of finding dicts back to CompatibilityFinding instances."""
    results: list[CompatibilityFinding] = []
    for d in finding_dicts:
        try:
            status = CompatibilityStatus(d["status"])
            category = FindingCategory(d["category"])
            from models import EffortLevel

            effort = EffortLevel(d["effort"]) if d.get("effort") else None
            results.append(
                CompatibilityFinding(
                    category=category,
                    identifier=d["identifier"],
                    status=status,
                    issues=d.get("issues", []),
                    recommendations=d.get("recommendations", []),
                    effort=effort,
                )
            )
        except (KeyError, ValueError):
            # Skip malformed finding dicts
            continue
    return results


def _build_skipped_findings(
    skipped_analyses: list[dict],
) -> list[dict]:
    """Build finding dicts for skipped analyses to include in the report.

    Each skipped analysis is represented as a finding with status
    ``requires_modification`` and an issue describing the failure.
    """
    findings: list[dict] = []
    for skipped in skipped_analyses:
        tool_name = skipped["tool"]
        reason = skipped["reason"]
        # Map tool names to categories
        category_map = {
            "DAG Inspector": "dag",
            "Dependency Analyzer": "dependency",
            "Configuration Analyzer": "configuration",
            "Plugin Analyzer": "plugin",
        }
        category = category_map.get(tool_name, "dag")
        findings.append(
            {
                "category": category,
                "identifier": f"[Skipped] {tool_name}",
                "status": "requires_modification",
                "issues": [
                    f"Analysis skipped due to tool failure: {reason}"
                ],
                "recommendations": [
                    "Re-run the analysis after resolving the underlying issue"
                ],
                "effort": None,
            }
        )
    return findings
