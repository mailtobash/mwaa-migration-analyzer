"""Loader for MWAA version manifest data files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from models import MWAAVersionManifest


def _get_repo_root() -> Path:
    """Determine the repository root directory.

    Uses the REPO_ROOT environment variable if set (for flexibility),
    otherwise walks up from this file's location to find the repository root.
    """
    env_root = os.environ.get("REPO_ROOT")
    if env_root:
        return Path(env_root)

    # Walk up from src/data_loader.py -> src/ -> repo_root/
    return Path(__file__).resolve().parent.parent


_DATA_DIR = _get_repo_root() / "data" / "compatibility"


def load_manifest(version: str) -> MWAAVersionManifest:
    """Load the MWAA version manifest for the given Airflow version.

    Args:
        version: The target MWAA Airflow version (e.g., "2.10.3").

    Returns:
        A populated MWAAVersionManifest dataclass instance.

    Raises:
        ValueError: If no manifest file exists for the requested version.
    """
    manifest_path = _DATA_DIR / f"{version}.json"
    if not manifest_path.exists():
        available = sorted(
            p.stem for p in _DATA_DIR.glob("*.json")
        )
        raise ValueError(
            f"Unsupported MWAA version: {version}. "
            f"Available versions: {', '.join(available) if available else 'none'}"
        )

    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)

    return MWAAVersionManifest(
        airflow_version=data["airflow_version"],
        pre_installed_packages=data["pre_installed_packages"],
        supported_config_keys=set(data["supported_config_keys"]),
        supported_operators=set(data["supported_operators"]),
        known_incompatible_packages=set(data["known_incompatible_packages"]),
    )
