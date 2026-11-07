#!/usr/bin/env bash
# Locally test a GitHub Actions workflow: lint it, then run the real job in an
# Ubuntu container via `act`, exactly as CI would. See scripts/README.md.
#
#   scripts/maintainer/test-workflow.sh <name> [--event EVENT] [--job JOB]
#                            [--image IMAGE] [--amd64] [--list] [--help]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/workflow_test.py" "$@"
