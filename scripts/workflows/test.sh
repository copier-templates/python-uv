#!/usr/bin/env bash
# Local-test profile for the CI test workflow.
# Sourced by scripts/test-workflow.sh. See scripts/README.md.
# shellcheck disable=SC2034  # all vars are consumed by the sourcing runner
set -euo pipefail

WORKFLOW_FILE=".github/workflows/test.yml"
WORKFLOW_EVENT="pull_request"
WORKFLOW_JOB="test"
ACT_IMAGE="catthehacker/ubuntu:act-24.04"
