#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"

echo "Creating virtual environment..."
python3 -m venv "${VENV_DIR}"

echo "Installing dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${REPO_ROOT}/requirements.txt"

echo "Setup complete. Activate with: source .venv/bin/activate"
