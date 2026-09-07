#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${repo_root}/packages/python${PYTHONPATH:+:${PYTHONPATH}}"
if [[ -x "${repo_root}/.venv/bin/python" ]]; then
  exec "${repo_root}/.venv/bin/python" -m wealthpilot.adapters.persistence.cli backup "$@"
fi
exec uv run --frozen python -m wealthpilot.adapters.persistence.cli backup "$@"
