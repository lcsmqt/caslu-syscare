#!/usr/bin/env bash
# Caslu SysCare — ambiente de desenvolvimento (Linux/macOS)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" == "--recreate" ]] && [[ -d .venv ]]; then
  rm -rf .venv
fi

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

echo ""
echo "Pronto. Proximos passos:"
echo "  Testes:  ./scripts/test.sh"
echo "  App GUI: ./scripts/run.sh"
