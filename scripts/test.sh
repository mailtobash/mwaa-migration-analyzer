#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Virtual environment not found. Running setup first..."
    "${REPO_ROOT}/scripts/setup.sh"
fi

# Install dev dependencies if pytest is not available
if ! "${VENV_DIR}/bin/python" -c "import pytest" 2>/dev/null; then
    echo "Installing development dependencies..."
    "${VENV_DIR}/bin/pip" install -r "${REPO_ROOT}/requirements-dev.txt"
fi

export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH:-}"
exec "${VENV_DIR}/bin/python" -m pytest "$@"
