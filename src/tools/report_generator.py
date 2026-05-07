"""Report Generator tool for producing migration assessment reports.

Generates reports in Markdown, JSON, or HTML format from compatibility
findings and a migration recommendation.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from strands import tool

logger = logging.getLogger(__name__)

# Effort ordering for sorting action items (low → medium → high)
_EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2}

# Category display names and ordering
_CATEGORY_DISPLAY = {
    "dag": "DAGs",
    "dependency": "Dependencies",
    "configuration": "Configuration",
    "plugin": "Plugins",
}

# Recommendation display names
_RECOMMENDATION_DISPLAY = {
    "lift_and_shift": "Lift and Shift",
    "lift_and_modernize": "Lift and Modernize",
    "not_possible": "Not Possible",
}

# Recommendation descriptions
_RECOMMENDATION_DESCRIPTIONS = {
    "lift_and_shift": (
        "Your Airflow environment is fully compatible with Amazon MWAA. "
        "You can migrate directly with minimal or no changes."
    ),
    "lift_and_modernize": (
        "Your Airflow environment requires some modifications before "
        "migrating to Amazon MWAA. See the action items below for details."
    ),
    "not_possible": (
        "Your Airflow environment contains incompatible components that "
        "block migration to Amazon MWAA. See the blockers section below."
    ),
}

# CSS class for recommendation styling in HTML
_RECOMMENDATION_CSS = {
    "lift_and_shift": "",
    "lift_and_modernize": "modernize",
    "not_possible": "not-possible",
}


def _get_template_dir() -> Path:
    """Resolve the template directory relative to repository root."""
    env_root = os.environ.get("REPO_ROOT")
    if env_root:
        return Path(env_root) / "data" / "templates"
    return Path(__file__).resolve().parent.parent.parent / "data" / "templates"


# Template directory
_TEMPLATE_DIR = _get_template_dir()


def _build_findings_by_category(
    findings: list[dict],
) -> dict[str, list[dict]]:
    """Group findings by category with display names.

    Args:
        findings: List of finding dicts.

    Returns:
        Ordered dict mapping category display name to list of findings.
    """
    grouped: dict[str, list[dict]] = {
        display: [] for display in _CATEGORY_DISPLAY.values()
    }
    for f in findings:
        category = f.get("category", "")
        display = _CATEGORY_DISPLAY.get(category, category)
        if display not in grouped:
            grouped[display] = []
        grouped[display].append(f)
    return grouped


def _build_action_items(
    findings: list[dict], recommendation: str
) -> list[dict]:
    """Build the action items list from findings that require action.

    For lift_and_modernize, items are sorted by effort level (low → medium → high).

    Args:
        findings: List of finding dicts.
        recommendation: The migration recommendation string.

    Returns:
        List of finding dicts that require action, sorted by effort.
    """
    # Statuses that require action
    actionable_statuses = {
        "requires_modification",
        "version_conflict",
        "unsupported",
        "incompatible",
        "unavailable",
    }

    action_items = [
        f for f in findings if f.get("status") in actionable_statuses
    ]

    if recommendation == "lift_and_modernize":
        action_items.sort(
            key=lambda f: _EFFORT_ORDER.get(f.get("effort", "") or "", 999)
        )

    return action_items


def _build_blockers(findings: list[dict]) -> list[dict]:
    """Extract all findings with incompatible status as blockers.

    Args:
        findings: List of finding dicts.

    Returns:
        List of finding dicts with incompatible status.
    """
    return [f for f in findings if f.get("status") == "incompatible"]


def _build_executive_summary(
    findings: list[dict], recommendation: str
) -> str:
    """Generate an executive summary from findings and recommendation.

    Args:
        findings: List of finding dicts.
        recommendation: The migration recommendation string.

    Returns:
        Executive summary text.
    """
    total = len(findings)
    compatible_count = sum(
        1 for f in findings if f.get("status") == "compatible"
    )
    incompatible_count = sum(
        1 for f in findings if f.get("status") == "incompatible"
    )
    action_count = total - compatible_count

    rec_display = _RECOMMENDATION_DISPLAY.get(recommendation, recommendation)

    summary = (
        f"Analyzed {total} component(s) for MWAA compatibility. "
        f"{compatible_count} component(s) are fully compatible"
    )

    if action_count > 0:
        summary += f", {action_count} require attention"

    if incompatible_count > 0:
        summary += f" (including {incompatible_count} incompatible blocker(s))"

    summary += f". Overall recommendation: {rec_display}."

    return summary


def _generate_markdown(template_context: dict) -> str:
    """Render the Markdown report template.

    Args:
        template_context: Context dict for the Jinja2 template.

    Returns:
        Rendered Markdown string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )
    template = env.get_template("report.md.j2")
    return template.render(**template_context)


def _generate_html(template_context: dict) -> str:
    """Render the HTML report template.

    Args:
        template_context: Context dict for the Jinja2 template.

    Returns:
        Rendered HTML string.
    """
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
        keep_trailing_newline=True,
    )
    template = env.get_template("report.html.j2")
    return template.render(**template_context)


def _generate_json(template_context: dict) -> str:
    """Generate a JSON report from the template context.

    Args:
        template_context: Context dict with report data.

    Returns:
        JSON string.
    """
    report_dict = {
        "executive_summary": template_context["executive_summary"],
        "recommendation": template_context["recommendation"],
        "recommendation_display": template_context["recommendation_display"],
        "findings_by_category": {
            category: [
                {
                    "identifier": f["identifier"],
                    "status": f["status"],
                    "issues": f["issues"],
                    "recommendations": f["recommendations"],
                    "effort": f.get("effort"),
                }
                for f in cat_findings
            ]
            for category, cat_findings in template_context[
                "findings_by_category"
            ].items()
        },
        "action_items": [
            {
                "identifier": item["identifier"],
                "status": item["status"],
                "issues": item["issues"],
                "recommendations": item["recommendations"],
                "effort": item.get("effort"),
            }
            for item in template_context["action_items"]
        ],
        "metadata": template_context["metadata"],
    }

    if template_context.get("blockers"):
        report_dict["blockers"] = [
            {
                "identifier": b["identifier"],
                "status": b["status"],
                "issues": b["issues"],
                "recommendations": b["recommendations"],
                "effort": b.get("effort"),
            }
            for b in template_context["blockers"]
        ]

    return json.dumps(report_dict, indent=2, default=str)


@tool
def generate_report(
    findings: list[dict],
    recommendation: str,
    output_format: str,
    metadata: dict,
) -> dict:
    """Generate the migration assessment report.

    Args:
        findings: All compatibility findings from analysis tools.
        recommendation: Migration recommendation (lift_and_shift, lift_and_modernize, not_possible).
        output_format: Output format (markdown, json, html).
        metadata: Report metadata (timestamp, source type, target version, tool version).

    Returns:
        A dict with 'report_content' containing the formatted report string.
    """
    recommendation = recommendation.lower().strip()
    output_format = output_format.lower().strip()

    findings_by_category = _build_findings_by_category(findings)
    action_items = _build_action_items(findings, recommendation)
    blockers = _build_blockers(findings)
    executive_summary = _build_executive_summary(findings, recommendation)

    template_context = {
        "executive_summary": executive_summary,
        "recommendation": recommendation,
        "recommendation_display": _RECOMMENDATION_DISPLAY.get(
            recommendation, recommendation
        ),
        "recommendation_description": _RECOMMENDATION_DESCRIPTIONS.get(
            recommendation, ""
        ),
        "recommendation_css_class": _RECOMMENDATION_CSS.get(
            recommendation, ""
        ),
        "findings_by_category": findings_by_category,
        "action_items": action_items,
        "blockers": blockers,
        "metadata": metadata,
    }

    if output_format == "json":
        report_content = _generate_json(template_context)
    elif output_format == "html":
        report_content = _generate_html(template_context)
    else:
        report_content = _generate_markdown(template_context)

    return {"report_content": report_content}
