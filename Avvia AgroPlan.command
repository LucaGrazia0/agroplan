#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if command -v python3.12 >/dev/null 2>&1; then
  python_bin="$(command -v python3.12)"
else
  python_bin="$(command -v python3)"
fi
"$python_bin" scripts/bootstrap_local.py "$@"
