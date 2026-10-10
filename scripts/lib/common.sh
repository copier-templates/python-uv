#!/usr/bin/env bash
# Shared helpers for local GitHub Actions workflow testing.
# Sourced by scripts/test-workflow.sh and per-workflow configs. Not executed directly.
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# --- logging (colors only when attached to a TTY) ---
if [ -t 1 ]; then
  _C_OK=$'\033[1;32m'
  _C_ERR=$'\033[1;31m'
  _C_WARN=$'\033[1;33m'
  _C_INFO=$'\033[1;34m'
  _C_OFF=$'\033[0m'
else
  _C_OK=""
  _C_ERR=""
  _C_WARN=""
  _C_INFO=""
  _C_OFF=""
fi

log_info() { printf '%s==> %s%s\n' "$_C_INFO" "$*" "$_C_OFF"; }
log_ok() { printf '%s✓ %s%s\n' "$_C_OK" "$*" "$_C_OFF"; }
log_warn() { printf '%s! %s%s\n' "$_C_WARN" "$*" "$_C_OFF" >&2; }
log_error() { printf '%s✗ %s%s\n' "$_C_ERR" "$*" "$_C_OFF" >&2; }
die() {
  log_error "$*"
  exit 1
}

need_cmd() { # <cmd> [install-hint]
  command -v "$1" >/dev/null 2>&1 || die "Required tool '$1' not found. ${2:-}"
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || die "Not inside a git repository."
}

ensure_docker() {
  # A `docker` shim can exist on PATH yet be broken (e.g. mise without the
  # docker-cli backend). Prefer whichever `docker` actually responds.
  if ! docker --version >/dev/null 2>&1; then
    if [ -x /opt/homebrew/bin/docker ]; then
      export PATH="/opt/homebrew/bin:$PATH"
    fi
  fi
  docker --version >/dev/null 2>&1 \
    || die "No working 'docker' CLI. Install one: brew install docker"
  if ! docker info >/dev/null 2>&1; then
    if command -v colima >/dev/null 2>&1; then
      log_info "Docker daemon unreachable, starting colima..."
      colima start || die "'colima start' failed."
      docker info >/dev/null 2>&1 \
        || die "Docker daemon still unreachable after 'colima start'."
    else
      die "Docker daemon unreachable. Start it (e.g. 'colima start') and retry."
    fi
  fi
  log_ok "docker: $(docker --version)"
}

run_actionlint() { # <workflow-file>
  need_cmd actionlint "Install it: brew install actionlint"
  actionlint "$1"
  log_ok "actionlint: $1 clean"
}

# Copy workflow files to a scratch dir so local-only patches never touch the repo.
stage_workflows() { # <repo-root> <dest-dir>
  mkdir -p "$2"
  cp "$1/.github/workflows/"*.yml "$2/"
}

inject_snippet() { # <staged-workflow-file> <job> <snippet-file>
  need_cmd python3 "Install it: brew install python"
  python3 "$SCRIPTS_DIR/lib/inject_step.py" "$1" "$2" "$3"
}

# Execute the job in an Ubuntu container. Log file path is echoed for the caller.
run_act() { # <workflows-dir> <event> <job-or-empty> <image> <log-file> [extra act args...]
  local workflows_dir="$1" event="$2" job="$3" image="$4" log_file="$5"
  shift 5
  need_cmd act "Install it: brew install act"
  local args=(-W "$workflows_dir" "$event")
  if [ -n "$job" ]; then
    args+=(-j "$job")
  fi
  # shellcheck disable=SC2206
  args+=(-P "ubuntu-latest=$image" --container-daemon-socket - "$@")
  log_info "act ${args[*]}"
  # Stream live output AND keep a log for the summary. pipefail is off here so
  # we can report act's exact exit code instead of tripping `set -e` early.
  set +e
  act "${args[@]}" 2>&1 | tee "$log_file"
  local rc=${PIPESTATUS[0]}
  set -e
  return "$rc"
}

print_summary() { # <log-file>
  local log_file="$1"
  echo "--- step results ---"
  grep -a -E "Success -|Failure -" "$log_file" \
    | sed -e 's/.*\(Success\|Failure\) - \(.*\) \[.*/\1: \2/' \
    | sort -u || true
  if grep -a -q "Job succeeded" "$log_file"; then
    log_ok "local run: JOB SUCCEEDED"
    return 0
  else
    log_error "local run: JOB FAILED (see $log_file)"
    return 1
  fi
}
