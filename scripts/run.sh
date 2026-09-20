#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/syscare ]]; then
  "$ROOT/scripts/setup-dev.sh"
fi

# shellcheck source=/dev/null
source .venv/bin/activate
unset QT_QPA_PLATFORM
python -m syscare
