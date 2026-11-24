#!/usr/bin/env bash
###############################################################################
# Defects4J Instrumenter - Linux / WSL2 Native Execution Script
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

# 1. Check or configure Java 11
if [[ -z "${JAVA_HOME:-}" ]]; then
    if [[ -d "/usr/lib/jvm/java-11-openjdk-amd64" ]]; then
        export JAVA_HOME="/usr/lib/jvm/java-11-openjdk-amd64"
    elif [[ -d "/usr/lib/jvm/default-java" ]]; then
        export JAVA_HOME="/usr/lib/jvm/default-java"
    fi
fi

if [[ -n "${JAVA_HOME:-}" ]]; then
    export PATH="$JAVA_HOME/bin:$PATH"
fi

# 2. Check Defects4J Archive default
DEFAULT_ZIP="$SCRIPT_DIR/defects4j-3.0.1.zip"
PARENT_ZIP="$(dirname "$SCRIPT_DIR")/defects4j-3.0.1.zip"
DEFECTS4J_ARG=()
if [[ ! " $* " =~ " --defects4j " ]]; then
    if [[ -f "$DEFAULT_ZIP" ]]; then
        DEFECTS4J_ARG=(--defects4j "$DEFAULT_ZIP")
    elif [[ -f "$PARENT_ZIP" ]]; then
        DEFECTS4J_ARG=(--defects4j "$PARENT_ZIP")
    elif [[ -z "${DEFECTS4J_HOME:-}" && -z "${DEFECTS4J_PATH:-}" ]] && ! command -v defects4j >/dev/null 2>&1; then
        DEFECTS4J_ARG=(--defects4j "$DEFAULT_ZIP")
    fi
fi

# 3. Export PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

echo "========================================================================"
echo " Defects4J Instrumenter - Linux / WSL2 Mode"
echo "========================================================================"
if [[ -n "${JAVA_HOME:-}" ]]; then
    echo "[+] Using JAVA_HOME: $JAVA_HOME"
fi

exec "$PYTHON" "$SCRIPT_DIR/run_defects4j.py" "${DEFECTS4J_ARG[@]}" "$@"
