#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

if [ ! -d "${VENV_DIR}" ]; then
    echo "Error: Virtual environment not found at ${VENV_DIR}"
    echo "Please run 'scripts/setup.sh' first."
    exit 1
fi

export PYTHONPATH="${REPO_ROOT}/src:${PYTHONPATH:-}"
exec "${VENV_DIR}/bin/python" -m cli "$@"
