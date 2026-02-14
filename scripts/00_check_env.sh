#!/usr/bin/env bash
set -euo pipefail
command -v git >/dev/null 2>&1 || { echo "ERROR: git not found"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
command -v pip >/dev/null 2>&1 || { echo "ERROR: pip not found"; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -d "$ROOT_DIR/.vendor" ]]; then
  export PYTHONPATH="$ROOT_DIR/.vendor:${PYTHONPATH:-}"
fi
python3 -c "import docx" >/dev/null 2>&1 || echo "WARN: python-docx not installed. Run: python3 -m pip install python-docx --target \"$ROOT_DIR/.vendor\""
echo "OK"
