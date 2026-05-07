"""Plugin Analyzer tool for checking Airflow plugins for MWAA compatibility."""

from __future__ import annotations

import ast
import logging
import re

from strands import tool

from data_loader import load_manifest
from models import (
    CompatibilityFinding,
    CompatibilityStatus,
    EffortLevel,
    FindingCategory,
    MWAAVersionManifest,
)

logger = logging.getLogger(__name__)

# Standard library module names that should always be considered available.
# This is a representative set covering the most commonly imported stdlib modules.
_STDLIB_TOP_LEVEL_MODULES: set[str] = {
    "abc", "aifc", "argparse", "array", "ast", "asynchat", "asyncio",
    "asyncore", "atexit", "base64", "bdb", "binascii", "binhex",
    "bisect", "builtins", "bz2", "calendar", "cgi", "cgitb", "chunk",
    "cmath", "cmd", "code", "codecs", "codeop", "collections",
    "colorsys", "compileall", "concurrent", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "cProfile", "crypt", "csv",
    "ctypes", "curses", "dataclasses", "datetime", "dbm", "decimal",
    "difflib", "dis", "distutils", "doctest", "email", "encodings",
    "enum", "errno", "faulthandler", "fcntl", "filecmp", "fileinput",
    "fnmatch", "fractions", "ftplib", "functools", "gc", "getopt",
    "getpass", "gettext", "glob", "grp", "gzip", "hashlib", "heapq",
    "hmac", "html", "http", "idlelib", "imaplib", "imghdr", "imp",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "lib2to3", "linecache", "locale", "logging", "lzma",
    "mailbox", "mailcap", "marshal", "math", "mimetypes", "mmap",
    "modulefinder", "multiprocessing", "netrc", "nis", "nntplib",
    "numbers", "operator", "optparse", "os", "ossaudiodev",
    "pathlib", "pdb", "pickle", "pickletools", "pipes", "pkgutil",
    "platform", "plistlib", "poplib", "posix", "posixpath", "pprint",
    "profile", "pstats", "pty", "pwd", "py_compile", "pyclbr",
    "pydoc", "queue", "quopri", "random", "re", "readline", "reprlib",
    "resource", "rlcompleter", "runpy", "sched", "secrets", "select",
    "selectors", "shelve", "shlex", "shutil", "signal", "site",
    "smtpd", "smtplib", "sndhdr", "socket", "socketserver", "sqlite3",
    "ssl", "stat", "statistics", "string", "stringprep", "struct",
    "subprocess", "sunau", "symtable", "sys", "sysconfig", "syslog",
    "tabnanny", "tarfile", "telnetlib", "tempfile", "termios", "test",
    "textwrap", "threading", "time", "timeit", "tkinter", "token",
    "tokenize", "tomllib", "trace", "traceback", "tracemalloc",
    "tty", "turtle", "turtledemo", "types", "typing", "unicodedata",
    "unittest", "urllib", "uu", "uuid", "venv", "warnings", "wave",
    "weakref", "webbrowser", "winreg", "winsound", "wsgiref",
    "xdrlib", "xml", "xmlrpc", "zipapp", "zipfile", "zipimport",
    "zlib", "_thread",
}

# The MWAA DAGs folder path prefix — file I/O within this path is acceptable.
_MWAA_DAGS_FOLDER = "/usr/local/airflow/dags"


def extract_imports(source: str) -> set[str]:
    """Use ast.parse to extract top-level package names from Python source.

    Returns the top-level module name for each import. For example:
      ``import pandas`` yields ``"pandas"``
      ``from airflow.operators.python import PythonOperator`` yields ``"airflow"``
      ``from my_custom_lib.utils import helper`` yields ``"my_custom_lib"``
    """
    imports: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_level = alias.name.split(".")[0]
                imports.add(top_level)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                top_level = module.split(".")[0]
                imports.add(top_level)
    return imports


def detect_subprocess_calls(source: str) -> list[str]:
    """Detect subprocess usage patterns in Python source.

    Looks for:
    - subprocess.run(...)
    - subprocess.Popen(...)
    - subprocess.call(...)
    """
    issues: list[str] = []

    if re.search(r"\bsubprocess\.run\b", source):
        issues.append(
            "System resource access: subprocess.run() call detected"
        )

    if re.search(r"\bsubprocess\.Popen\b", source):
        issues.append(
            "System resource access: subprocess.Popen() call detected"
        )

    if re.search(r"\bsubprocess\.call\b", source):
        issues.append(
            "System resource access: subprocess.call() call detected"
        )

    return issues


def detect_os_system_calls(source: str) -> list[str]:
    """Detect os.system() usage in Python source."""
    issues: list[str] = []

    if re.search(r"\bos\.system\s*\(", source):
        issues.append(
            "System resource access: os.system() call detected"
        )

    return issues


def detect_local_file_io(source: str) -> list[str]:
    """Detect local file I/O outside the MWAA DAGs folder.

    Looks for open() calls with path arguments that reference locations
    outside /usr/local/airflow/dags.
    """
    issues: list[str] = []

    # Find open() calls with string literal paths
    # Match patterns like: open("/some/path", ...) or open('/some/path', ...)
    open_pattern = re.compile(
        r"""\bopen\s*\(\s*(['"])(.*?)\1""",
        re.DOTALL,
    )

    for match in open_pattern.finditer(source):
        path = match.group(2)
        # If the path is absolute and not within the DAGs folder, flag it
        if path.startswith("/") and not path.startswith(_MWAA_DAGS_FOLDER):
            issues.append(
                f"System resource access: file I/O outside DAGs folder "
                f"detected — open('{path}')"
            )

    return issues


def detect_socket_usage(source: str) -> list[str]:
    """Detect network socket usage in Python source.

    Looks for socket module usage patterns such as:
    - socket.socket(...)
    - socket.create_connection(...)
    - socket.getaddrinfo(...)
    - Any socket.* call
    """
    issues: list[str] = []

    if re.search(r"\bsocket\.\w+\s*\(", source):
        issues.append(
            "System resource access: network socket usage detected"
        )

    return issues


def detect_unavailable_imports(
    source: str, manifest: MWAAVersionManifest
) -> list[str]:
    """Detect imports of packages not available in the MWAA runtime.

    Compares extracted top-level imports against:
    1. Python standard library modules
    2. airflow.* modules (always available)
    3. Pre-installed packages from the MWAA version manifest (normalized)

    Returns a list of issue description strings for unavailable imports.
    """
    imports = extract_imports(source)
    issues: list[str] = []

    # Build a normalized set of pre-installed package top-level names
    available_packages: set[str] = set()
    for pkg_name in manifest.pre_installed_packages:
        # Normalize: lowercase, replace hyphens/underscores with hyphens
        normalized = re.sub(r"[-_.]+", "-", pkg_name).lower()
        # Also add the underscore variant (for import compatibility)
        underscore_variant = normalized.replace("-", "_")
        available_packages.add(normalized)
        available_packages.add(underscore_variant)

    for imp in sorted(imports):
        # Standard library modules are always available
        if imp in _STDLIB_TOP_LEVEL_MODULES:
            continue

        # airflow.* modules are always available in MWAA
        if imp == "airflow":
            continue

        # Check against pre-installed packages (normalized)
        imp_normalized = re.sub(r"[-_.]+", "-", imp).lower()
        imp_underscore = imp_normalized.replace("-", "_")
        if imp_normalized in available_packages or imp_underscore in available_packages:
            continue

        issues.append(
            f"Unavailable import: '{imp}' is not available in the MWAA runtime"
        )

    return issues


def check_plugin_structure(source: str, filename: str) -> list[str]:
    """Check for MWAA plugin structure compliance.

    MWAA plugins should follow the Airflow plugin structure:
    - Define a class that inherits from AirflowPlugin
    - Or be a valid Python module in the plugins directory

    This is a lightweight check — we just verify the file is parseable.
    """
    issues: list[str] = []

    try:
        ast.parse(source)
    except SyntaxError as exc:
        issues.append(
            f"Plugin structure issue: syntax error in '{filename}' — {exc}"
        )

    return issues


@tool
def analyze_plugins(
    plugin_files: list[dict], target_mwaa_version: str = "2.10.3"
) -> dict:
    """Analyze Airflow plugins for MWAA compatibility.

    Args:
        plugin_files: List of plugin file dicts with 'filename' and 'content' keys.
        target_mwaa_version: Target MWAA Airflow version.

    Returns:
        A dict with 'findings' containing compatibility results per plugin.
    """
    manifest = load_manifest(target_mwaa_version)
    findings: list[dict] = []

    for plugin_file in plugin_files:
        filename = plugin_file.get("filename", "unknown")
        content = plugin_file.get("content", "")

        all_issues: list[str] = []
        all_recommendations: list[str] = []

        # Check plugin structure compliance
        structure_issues = check_plugin_structure(content, filename)
        if structure_issues:
            all_issues.extend(structure_issues)
            all_recommendations.append(
                "Fix the syntax error in the plugin file"
            )
            # If there's a syntax error, we can't do AST-based analysis
            finding = CompatibilityFinding(
                category=FindingCategory.PLUGIN,
                identifier=filename,
                status=CompatibilityStatus.REQUIRES_MODIFICATION,
                issues=all_issues,
                recommendations=all_recommendations,
                effort=EffortLevel.LOW,
            )
            findings.append(_finding_to_dict(finding))
            continue

        # Detect system resource access patterns
        subprocess_issues = detect_subprocess_calls(content)
        if subprocess_issues:
            all_issues.extend(subprocess_issues)
            all_recommendations.append(
                "Replace subprocess calls with Airflow operators "
                "(e.g., BashOperator) or AWS service integrations"
            )

        os_system_issues = detect_os_system_calls(content)
        if os_system_issues:
            all_issues.extend(os_system_issues)
            all_recommendations.append(
                "Replace os.system() calls with Airflow operators "
                "or AWS service integrations"
            )

        file_io_issues = detect_local_file_io(content)
        if file_io_issues:
            all_issues.extend(file_io_issues)
            all_recommendations.append(
                "Replace local file I/O with S3 operations using "
                "the S3Hook or boto3 client"
            )

        socket_issues = detect_socket_usage(content)
        if socket_issues:
            all_issues.extend(socket_issues)
            all_recommendations.append(
                "Replace direct socket usage with Airflow HTTP operators "
                "or provider hooks"
            )

        # Detect unavailable imports
        import_issues = detect_unavailable_imports(content, manifest)
        if import_issues:
            all_issues.extend(import_issues)
            all_recommendations.append(
                "Add missing packages to your MWAA requirements.txt "
                "or replace with MWAA-compatible alternatives"
            )

        # Determine status based on issues found
        status = _determine_status(all_issues)

        # Determine effort level
        effort = _determine_effort(all_issues)

        finding = CompatibilityFinding(
            category=FindingCategory.PLUGIN,
            identifier=filename,
            status=status,
            issues=all_issues,
            recommendations=all_recommendations,
            effort=effort,
        )
        findings.append(_finding_to_dict(finding))

    return {"findings": findings}


def _determine_status(issues: list[str]) -> CompatibilityStatus:
    """Determine the overall compatibility status from a list of issues.

    - No issues → COMPATIBLE
    - Has system resource access issues → REQUIRES_MODIFICATION
    - Has unavailable import issues → REQUIRES_MODIFICATION
    - Has syntax errors → REQUIRES_MODIFICATION
    """
    if not issues:
        return CompatibilityStatus.COMPATIBLE

    return CompatibilityStatus.REQUIRES_MODIFICATION


def _determine_effort(issues: list[str]) -> EffortLevel | None:
    """Determine the effort level based on the types of issues found."""
    if not issues:
        return None

    has_system_resource = any(
        issue.startswith("System resource access:") for issue in issues
    )
    has_unavailable_import = any(
        issue.startswith("Unavailable import:") for issue in issues
    )
    has_structure_issue = any(
        issue.startswith("Plugin structure issue:") for issue in issues
    )

    # System resource access requires significant refactoring
    if has_system_resource:
        return EffortLevel.HIGH

    # Unavailable imports may need requirements.txt changes
    if has_unavailable_import:
        return EffortLevel.MEDIUM

    # Structure issues are typically easy to fix
    if has_structure_issue:
        return EffortLevel.LOW

    return EffortLevel.LOW


def _finding_to_dict(finding: CompatibilityFinding) -> dict:
    """Convert a CompatibilityFinding dataclass to a plain dict for tool output."""
    return {
        "category": finding.category.value,
        "identifier": finding.identifier,
        "status": finding.status.value,
        "issues": finding.issues,
        "recommendations": finding.recommendations,
        "effort": finding.effort.value if finding.effort else None,
    }
