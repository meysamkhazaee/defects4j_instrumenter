#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)";
elif command -v python >/dev/null 2>&1; then PYTHON_BIN="$(command -v python)";
else echo "error: Python 3 is required to build the Java agent." >&2; exit 1; fi
exec "$PYTHON_BIN" "$ROOT/build.py" "$@"
