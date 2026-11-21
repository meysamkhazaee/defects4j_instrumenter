#!/usr/bin/env bash
###############################################################################
# Defects4J Instrumenter - Linux Runner Entry Point
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$SCRIPT_DIR/scripts/run_linux.sh" "$@"
