#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
JAVA_ARGS=()
if [[ $# -ge 1 && -n "$1" ]]; then
  JAVA_ARGS=(--java-home "$1")
fi
"$PYTHON" "$ROOT/java-agent/build.py" "${JAVA_ARGS[@]}"
