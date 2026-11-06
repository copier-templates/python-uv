#!/usr/bin/env bash
# Check that pyproject.toml [project] version equals the max-semver plain X.Y.Z
# tag reachable from HEAD. Blocks both drift directions:
#   version > tag  -> bumped without tagging (run release / tag / push --follow-tags)
#   tag > version  -> tag moved ahead (never delete the tag; bump pyproject)
# No tags reachable -> pass (fresh repo). Offline-safe: remote checks warn only.
#
#   scripts/check-version-tag.sh [--help]
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/release-common.sh
source "$SCRIPT_DIR/lib/release-common.sh"

usage() {
  cat <<'EOF'
Usage:
  check-version-tag.sh [--help]

Check pyproject.toml [project] version against git tags.

Exits 0 when the version equals the max-semver X.Y.Z tag reachable from HEAD
(or when no X.Y.Z tags exist yet). Exits 1 on mismatch with a recovery hint,
or when the version is unparseable.
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi
if [[ $# -gt 0 ]]; then
  log_error "Unexpected argument: $1"
  usage >&2
  exit 2
fi

git rev-parse --show-toplevel >/dev/null 2>&1 || die "Not inside a git repository."
cd "$(git rev-parse --show-toplevel)"

current_version="$(python "$SCRIPT_DIR/release_version.py" project-version)" \
  || die "Could not read [project] version from pyproject.toml."

# Newest reachable plain X.Y.Z tag by semver (git describe is recency, not max).
# An unborn HEAD (fresh repo, no commits) cannot be tagged yet: treat it like
# "no tags reachable" instead of letting `git tag --merged HEAD` fail.
if git rev-parse --verify --quiet HEAD >/dev/null; then
  latest="$(git -c color.ui=false tag --merged HEAD 2>/dev/null \
    | python "$SCRIPT_DIR/release_version.py" latest-tag)" \
    || die "Could not compare tags by semver."
else
  latest=""
fi

state="$(python "$SCRIPT_DIR/release_version.py" classify \
  --current "$current_version" --latest "$latest")" \
  || die "Could not classify version drift."

case "$state" in
  no-tags)
    log_ok "No X.Y.Z tags reachable from HEAD; pyproject is ${current_version}. OK."
    ;;
  ok)
    log_ok "pyproject version ${current_version} matches latest tag ${latest}. OK."
    # Best-effort reminder when the tag is not on the remote yet (offline-safe).
    if remote_tags="$(git ls-remote --tags origin 2>/dev/null)" && ! grep -q "refs/tags/${latest}$" <<<"$remote_tags"; then
      log_info "Note: tag ${latest} is not on origin yet; push with: git push --follow-tags"
    fi
    ;;
  ahead)
    log_error "Blocked: pyproject version ${current_version} is ahead of latest tag ${latest}."
    die "You bumped without tagging. Fix with: mise run release --version ${current_version} --yes, then: git push --follow-tags"
    ;;
  behind)
    log_error "Blocked: latest tag ${latest} is ahead of pyproject version ${current_version}."
    die "Never delete the tag. Fix with: mise run release (--version above ${latest}), then: git push --follow-tags"
    ;;
  *)
    die "Unknown version drift state: ${state}"
    ;;
esac

exit 0
