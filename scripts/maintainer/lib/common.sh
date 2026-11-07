#!/usr/bin/env bash
# Shared die/need_cmd for the maintainer release CLIs. Sourced by
# scripts/maintainer/release/*.sh; never executed directly.
#
# Callers may set SCRIPT_NAME before calling die/need_cmd: when it is non-empty,
# die prints "SCRIPT_NAME: message" (the release CLIs rely on this to keep their
# pre-refactor stderr); when empty, die keeps the "✗ message" default.
set -euo pipefail

SCRIPT_NAME="${SCRIPT_NAME:-}"

# --- error logging (color only when attached to a TTY) ---
if [[ -t 1 ]]; then
  _C_ERR=$'\033[1;31m'
  _C_OFF=$'\033[0m'
else
  _C_ERR=""
  _C_OFF=""
fi

log_error() { printf '%s✗ %s%s\n' "$_C_ERR" "$*" "$_C_OFF" >&2; }
die() {
  if [[ -n $SCRIPT_NAME ]]; then
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit 1
  fi
  log_error "$*"
  exit 1
}

need_cmd() { # <cmd> [install-hint]
  if ! command -v "$1" >/dev/null 2>&1; then
    local hint="${2:-}"
    if [[ -n $hint ]]; then
      die "Required tool '$1' not found. $hint"
    else
      die "Required tool '$1' not found."
    fi
  fi
}
