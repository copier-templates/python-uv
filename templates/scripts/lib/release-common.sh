#!/usr/bin/env bash
# Shared logging, color and guard helpers for the release scripts.
# Sourced by release.sh and check-version-tag.sh; never executed directly.
set -euo pipefail

# --- logging (colors only when attached to a TTY) ---
if [[ -t 1 ]]; then
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
