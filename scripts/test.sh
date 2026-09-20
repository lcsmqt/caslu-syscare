#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  "$ROOT/scripts/setup-dev.sh"
fi

# shellcheck source=/dev/null
source .venv/bin/activate
prev_qt="${QT_QPA_PLATFORM-}"
export QT_QPA_PLATFORM=offscreen
if [[ $# -gt 0 ]]; then
  python -m pytest "$@"
else
  python -m pytest -q
fi
rc=$?
if [[ -z "$prev_qt" ]]; then
  unset QT_QPA_PLATFORM
else
  export QT_QPA_PLATFORM="$prev_qt"
fi
exit $rc
