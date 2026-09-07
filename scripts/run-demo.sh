#!/usr/bin/env bash
set -euo pipefail

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$repo_root"

export WEALTHPILOT_MODE="${WEALTHPILOT_MODE:-PERSONAL_LOCAL}"
export WEALTHPILOT_HOST="${WEALTHPILOT_HOST:-127.0.0.1}"
export WEALTHPILOT_PORT="${WEALTHPILOT_PORT:-8000}"

exec uv run uvicorn apps.api.main:app \
  --host "$WEALTHPILOT_HOST" \
  --port "$WEALTHPILOT_PORT"
