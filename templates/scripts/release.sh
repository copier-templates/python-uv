#!/usr/bin/env bash
# Cut a release: bump [project] version, re-lock, regenerate CHANGELOG.md,
# commit, and tag. Never pushes. Interactive via gum on a TTY, flag-driven
# otherwise (CI-safe).
#
#   scripts/release.sh [--version X.Y.Z] [--yes]
#   scripts/release.sh --help
#
# Env overrides (same as flags, win over nothing — flags win over env):
#   RELEASE_VERSION, RELEASE_YES=1
set -euo pipefail

VERSION=""
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage:
  release.sh [--version X.Y.Z] [--yes]
  release.sh --help

Cut a release in the current repository:
  1. determines the next version (git-cliff over conventional commits)
  2. bumps [project] version in pyproject.toml and re-locks uv.lock
  3. regenerates CHANGELOG.md, commits, and tags (never pushes)

Options:
  --version X.Y.Z   release this exact version (default: prompt on a TTY,
                    or the git-cliff suggestion with --yes)
  --yes             non-interactive: accept the suggested version and skip
                    confirmations (required when not on a TTY)
  --help            print this help and exit

Environment:
  RELEASE_VERSION   same as --version
  RELEASE_YES=1     same as --yes

Examples:
  scripts/release.sh
  scripts/release.sh --version 0.4.0 --yes
  RELEASE_YES=1 scripts/release.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      VERSION="$2"
      shift 2
      ;;
    --version=*)
      VERSION="${1#--version=}"
      shift
      ;;
    --yes)
      ASSUME_YES=1
      shift
      ;;
    --help | -h)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      printf 'Unexpected argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

# Flags win over env.
VERSION="${VERSION:-${RELEASE_VERSION:-}}"
if [[ "${RELEASE_YES:-0}" == "1" ]]; then
  ASSUME_YES=1
fi

# --- logging (colors only on a TTY, mirrors scripts/lib/common.sh) ---
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
die() {
  printf '%s✗ %s%s\n' "$_C_ERR" "$*" "$_C_OFF" >&2
  exit 1
}

need_cmd() { # <cmd> [install-hint]
  command -v "$1" >/dev/null 2>&1 || die "Required tool '$1' not found. ${2:-}"
}

is_interactive() {
  [[ -t 0 && -t 1 ]] && command -v gum >/dev/null 2>&1
}

main() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Not inside a git repository."
  cd "$(git rev-parse --show-toplevel)"

  # 1. Preflight: the release commit must contain exactly the release files.
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Working tree is dirty. Commit or stash first, then re-run."
  fi
  local branch
  branch="$(git branch --show-current 2>/dev/null || true)"
  if [[ -n $branch && $branch != "main" && $branch != "master" ]]; then
    log_warn "On branch '${branch}' (expected main/master). Continuing anyway."
  fi
  need_cmd git-cliff "Install it: mise install"
  need_cmd uv "Install it: mise install"
  need_cmd python "Install it: mise install"
  python -c 'import sys, tomllib; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null \
    || die "'python' must be 3.11+ (tomllib). Run via 'mise run release'."

  # 2. Current version + latest tag (fresh repos may have no tags yet).
  local current_version last_tag has_tags
  current_version="$(python - <<'EOF'
import tomllib
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
EOF
)"
  has_tags=0
  last_tag=""
  if last_tag="$(git describe --tags --abbrev=0 2>/dev/null)"; then
    has_tags=1
    if [[ ! $last_tag =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      log_warn "Latest tag '${last_tag}' is not X.Y.Z; comparing against pyproject version only."
      last_tag=""
      has_tags=0
    fi
  fi
  if (( has_tags )) && git diff --quiet "${last_tag}..HEAD" --; then
    die "Nothing to release: no commits since tag ${last_tag}."
  fi
  if git rev-parse --verify --quiet "refs/tags/${current_version}" >/dev/null && (( ! has_tags )); then
    : # first release reuses the pyproject version below; tag check happens later
  fi

  # 3. Determine the version to release.
  local suggested explicit=0
  if (( has_tags )); then
    suggested="$(git-cliff --bumped-version 2>/dev/null)" \
      || die "git-cliff cannot suggest a version (no conventional commits since ${last_tag}?). Pass --version X.Y.Z explicitly."
  else
    suggested="$current_version"
  fi
  if [[ -n $VERSION ]]; then
    explicit=1
  fi
  if is_interactive && (( ! explicit )); then
    VERSION="$(gum input --header "Release version" --prompt "Version: " --value "$suggested")" || exit 0
    [[ -n $VERSION ]] || die "No version entered, aborting."
  elif [[ -z $VERSION ]]; then
    if (( ASSUME_YES )); then
      VERSION="$suggested"
    else
      usage >&2
      die "Not interactive (no TTY or gum missing): pass --version X.Y.Z with --yes."
    fi
  fi
  [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "Invalid version '${VERSION}': expected X.Y.Z (plain tags, no 'v' prefix)."
  if git rev-parse --verify --quiet "refs/tags/${VERSION}" >/dev/null; then
    die "Tag '${VERSION}' already exists."
  fi
  # Never go backwards: above the highest of pyproject version / latest tag.
  # Exception: a first release (no tags) may equal the pyproject version.
  if ! python - "$VERSION" "$current_version" "$last_tag" <<'EOF' >/dev/null 2>&1
import sys
def key(v):
    return tuple(int(p) for p in v.split("."))
ver, cur, last = sys.argv[1], sys.argv[2], sys.argv[3]
floor = max(key(cur), key(last)) if last else key(cur)
ok = (key(ver) >= floor) if not last else (key(ver) > floor)
sys.exit(0 if ok else 1)
EOF
  then
    die "Version ${VERSION} must be above pyproject (${current_version})${last_tag:+ and tag ${last_tag}}."
  fi

  log_info "Releasing ${VERSION} (pyproject was ${current_version})."

  # 4. Bump [project] version (exactly one `version =` key in our pyprojects).
  python - "$VERSION" <<'EOF'
import re
import sys
path = "pyproject.toml"
text = open(path).read()
new, n = re.subn(r'^version\s*=\s*"[^"]*"', f'version = "{sys.argv[1]}"', text, count=1, flags=re.M)
if n != 1:
    sys.exit("expected exactly one top-level version key in pyproject.toml")
open(path, "w").write(new)
EOF

  # 5. Re-lock so uv.lock records the new version (stale locks break --locked CI).
  if is_interactive; then
    gum spin --title "Updating uv.lock..." -- uv lock \
      || die "'uv lock' failed. Restore with: git checkout -- pyproject.toml"
  else
    uv lock \
      || die "'uv lock' failed. Restore with: git checkout -- pyproject.toml"
  fi

  # 6. Regenerate the changelog. --tag names the not-yet-existing tag so the
  # new section renders as a version instead of [unreleased].
  git-cliff --tag "$VERSION" -o CHANGELOG.md \
    || die "'git-cliff' failed. Restore with: git checkout -- pyproject.toml uv.lock"

  # 7. Review gate.
  git add -- pyproject.toml uv.lock CHANGELOG.md
  git diff --cached --stat
  log_info "CHANGELOG.md preview:"
  head -n 15 CHANGELOG.md
  if is_interactive && (( ! ASSUME_YES )); then
    gum confirm "Commit and tag ${VERSION}?" --default \
      || { printf 'Aborted, nothing committed.\n'; exit 0; }
  fi

  # 8. Commit + tag. The message prefix is in cliff.toml's skip list, so
  # release commits never pollute future changelogs.
  if ! git commit -m "chore(release): prepare for ${VERSION}"; then
    printf 'Commit failed (hooks may have modified files).\n' >&2
    printf "Inspect with 'git status', stage fixes, then finish manually:\n" >&2
    printf '  git commit -m "chore(release): prepare for %s" && git tag %s\n' "$VERSION" "$VERSION" >&2
    exit 1
  fi
  git tag "$VERSION" || die "Tagging '${VERSION}' failed."

  # 9. Never push automatically.
  log_ok "Released ${VERSION}."
  printf "Review, then push: git push --follow-tags\n"
}

main "$@"
