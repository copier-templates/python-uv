#!/usr/bin/env bash
# Local-test profile for the scheduled pre-commit auto-update workflow.
# Sourced by scripts/test-workflow.sh. Copy this file to add a new workflow.
# shellcheck disable=SC2034  # all vars are consumed by the sourcing runner
set -euo pipefail

WORKFLOW_FILE=".github/workflows/pre-commit.yml"
WORKFLOW_EVENT="workflow_dispatch"
WORKFLOW_JOB="auto-update"
ACT_IMAGE="catthehacker/ubuntu:act-24.04"

# This job shells out to git (`pre-commit autoupdate`, `git diff`), but act's
# fake checkout copies files WITHOUT the .git directory. Stage a scratch repo
# inside the container so git-dependent steps behave like on real runners.
WORKFLOW_NEEDS_GIT_SHIM="yes"
WORKFLOW_SHIM_SNIPPET="$SCRIPTS_DIR/workflows/pre-commit-shim.yml"
