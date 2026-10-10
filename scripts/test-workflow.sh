#!/usr/bin/env bash
# Locally test a GitHub Actions workflow: lint it, then run the real job in an
# Ubuntu container via `act`, exactly as CI would. See scripts/README.md.
#
#   scripts/test-workflow.sh <name> [--event EVENT] [--job JOB]
#                            [--image IMAGE] [--amd64] [--list] [--help]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

usage() {
  cat <<'EOF'
Usage:
  test-workflow.sh <name> [--event EVENT] [--job JOB] [--image IMAGE] [--amd64]
  test-workflow.sh --list
  test-workflow.sh --help

Examples:
  test-workflow.sh pre-commit
  test-workflow.sh pre-commit --event schedule
  test-workflow.sh test --job test --event pull_request

Full docs: scripts/README.md
EOF
}

list_workflows() {
  local cfg name
  for cfg in "$SCRIPT_DIR"/workflows/*.sh; do
    [ -e "$cfg" ] || continue
    name="$(basename "$cfg" .sh)"
    # Sourced in the current shell (not a subshell) so static analysis sees
    # the assignments; unset afterwards to avoid leaking between profiles.
    # shellcheck disable=SC1090
    source "$cfg"
    printf '%-16s file=%s event=%s job=%s\n' \
      "$name" "$WORKFLOW_FILE" "$WORKFLOW_EVENT" "${WORKFLOW_JOB:-(all)}"
    unset WORKFLOW_FILE WORKFLOW_EVENT WORKFLOW_JOB ACT_IMAGE \
      WORKFLOW_NEEDS_GIT_SHIM WORKFLOW_SHIM_SNIPPET ACT_EXTRA_ARGS
  done
}

NAME=""
EVENT_OVERRIDE=""
JOB_OVERRIDE=""
IMAGE_OVERRIDE=""
AMD64="no"

while [ $# -gt 0 ]; do
  case "$1" in
    --list) list_workflows; exit 0 ;;
    --help | -h) usage; exit 0 ;;
    --event) EVENT_OVERRIDE="${2:?--event needs a value}"; shift 2 ;;
    --job) JOB_OVERRIDE="${2:?--job needs a value}"; shift 2 ;;
    --image) IMAGE_OVERRIDE="${2:?--image needs a value}"; shift 2 ;;
    --amd64) AMD64="yes"; shift ;;
    --*) die "Unknown flag: $1 (see --help)" ;;
    *) NAME="$1"; shift ;;
  esac
done

[ -n "$NAME" ] || { usage; die "Missing workflow name."; }

CONFIG="$SCRIPT_DIR/workflows/$NAME.sh"
[ -f "$CONFIG" ] || {
  log_error "Unknown workflow '$NAME'. Available:"
  list_workflows >&2
  exit 1
}

# Per-workflow profile. Only simple variable assignments + optional hooks.
# shellcheck disable=SC1090
source "$CONFIG"

EVENT="${EVENT_OVERRIDE:-${WORKFLOW_EVENT:-workflow_dispatch}}"
JOB="${JOB_OVERRIDE:-${WORKFLOW_JOB:-}}"
IMAGE="${IMAGE_OVERRIDE:-${ACT_IMAGE:-catthehacker/ubuntu:act-24.04}}"

cd "$(repo_root)"
ROOT="$(pwd)"
WORKFLOW_PATH="$ROOT/$WORKFLOW_FILE"
[ -f "$WORKFLOW_PATH" ] || die "Workflow file not found: $WORKFLOW_PATH"

log_info "testing $WORKFLOW_FILE (event=$EVENT job=${JOB:-(all)})"
run_actionlint "$WORKFLOW_PATH"
ensure_docker

STAGE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/act-workflows-XXXXXX")"
# NOTE: macOS mktemp requires the X's to be trailing (no ".log" suffix).
ACT_LOG="$(mktemp "${TMPDIR:-/tmp}/act-run-XXXXXX")"
# Invoked indirectly via the trap below.
# shellcheck disable=SC2329
cleanup() { rm -rf "$STAGE_DIR"; }
trap cleanup EXIT INT TERM

stage_workflows "$ROOT" "$STAGE_DIR"
STAGED_FILE="$STAGE_DIR/$(basename "$WORKFLOW_FILE")"
if [ "${WORKFLOW_NEEDS_GIT_SHIM:-no}" = "yes" ]; then
  [ -n "${WORKFLOW_SHIM_SNIPPET:-}" ] \
    || die "$CONFIG sets WORKFLOW_NEEDS_GIT_SHIM but no WORKFLOW_SHIM_SNIPPET."
  inject_snippet "$STAGED_FILE" "$JOB" "$WORKFLOW_SHIM_SNIPPET"
  log_info "injected act-local git shim into staged copy (repo untouched)"
fi

EXTRA_ARGS=()
if [ "$AMD64" = "yes" ]; then
  EXTRA_ARGS+=(--container-architecture linux/amd64)
fi
# Per-workflow escape hatch, e.g. ACT_EXTRA_ARGS="--matrix os:ubuntu-latest".
# Word-split on purpose; keep it to simple flags without spaces.
if [ -n "${ACT_EXTRA_ARGS:-}" ]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS+=($ACT_EXTRA_ARGS)
fi

log_info "full log: $ACT_LOG"
if [ ${#EXTRA_ARGS[@]} -gt 0 ]; then
  run_act_result=0
  run_act "$STAGE_DIR" "$EVENT" "$JOB" "$IMAGE" "$ACT_LOG" "${EXTRA_ARGS[@]}" \
    || run_act_result=$?
else
  run_act_result=0
  run_act "$STAGE_DIR" "$EVENT" "$JOB" "$IMAGE" "$ACT_LOG" \
    || run_act_result=$?
fi
ACT_RC=$run_act_result

# The staged copy is disposable; the real workflow file was never modified.
if [ "${WORKFLOW_NEEDS_GIT_SHIM:-no}" = "yes" ] && grep -q "ACT-LOCAL" "$WORKFLOW_PATH"; then
  die "Safety check failed: $WORKFLOW_FILE contains ACT-LOCAL markers!"
fi
log_ok "repo workflow file untouched by local shims"

print_summary "$ACT_LOG"
exit "$ACT_RC"
