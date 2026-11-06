#!/usr/bin/env bash
# Cut a release: bump [project] version, re-lock, regenerate CHANGELOG.md,
# amend HEAD, and tag. Never pushes. Shows local vs origin tags before prompting.
# Interactive via gum on a TTY, flag-driven otherwise (CI-safe).
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
  1. determines the next version (always a patch bump; conventional commits
     only shape the changelog)
  2. bumps [project] version in pyproject.toml and re-locks uv.lock
  3. regenerates CHANGELOG.md, amends HEAD, and tags (never pushes)

Options:
  --version X.Y.Z   release this exact version (default: prompt on a TTY,
                    or the suggested patch version with --yes)
  --yes             non-interactive: accept the suggested version, skip
                    confirmations, and allow releasing from a non-main/master
                    branch (required when not on a TTY)
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

# Highest plain X.Y.Z tag in `git ls-remote --tags` output (empty when none).
# Ignores non-semver tags and peeled (^{}) entries; portable across BSD/GNU sort.
latest_remote_tag() { # <ls-remote-output>
  printf '%s\n' "$1" \
    | sed -nE 's#.*refs/tags/([0-9]+\.[0-9]+\.[0-9]+)$#\1#p' \
    | sort -t. -k1,1n -k2,2n -k3,3n \
    | tail -n 1
}

# Suggested next version: the patch bump above the highest known version
# (pyproject, latest local tag, latest remote tag). Conventional commit types
# never bump minor/major; pass --version to release those explicitly. A repo
# with no tags yet keeps the pyproject version for its first release.
suggested_version() { # <current> <last-tag> <remote-tag>
  python - "$@" <<'EOF'
import sys

def key(version):
    return tuple(int(part) for part in version.split("."))

current, last, remote = sys.argv[1:4]
if not last and not remote:
    print(current)
else:
    major, minor, patch = max(key(version) for version in (current, last, remote) if version)
    print(f"{major}.{minor}.{patch + 1}")
EOF
}

main() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Not inside a git repository."
  cd "$(git rev-parse --show-toplevel)"

  # 1. Preflight: working tree must be clean; HEAD must not already be a
  # release commit (release files amend HEAD, never form their own commit).
  if ! git diff --quiet || ! git diff --cached --quiet; then
    die "Working tree is dirty. Commit or stash first, then re-run."
  fi
  local last_subject
  last_subject="$(git log -1 --format=%s 2>/dev/null || true)"
  if [[ $last_subject == chore\(release\)* ]]; then
    die "Last commit is already a release commit ('${last_subject}'). Aborting."
  fi
  local branch
  branch="$(git branch --show-current 2>/dev/null || true)"
  if [[ -n $branch && $branch != "main" && $branch != "master" ]]; then
    if (( ASSUME_YES )); then
      log_warn "On branch '${branch}' (expected main/master); continuing because --yes was given."
    elif is_interactive; then
      log_warn "On branch '${branch}' (expected main/master)."
      gum confirm "Release from '${branch}' instead of main/master?" --default=false \
        || { printf 'Aborted, nothing changed.\n'; exit 0; }
    else
      die "On branch '${branch}' (expected main/master). Switch to main/master, or re-run with --yes to release from here."
    fi
  fi
  need_cmd git-cliff "Install it: mise install"
  need_cmd uv "Install it: mise install"
  need_cmd python "Install it: mise install"
  python -c 'import sys, tomllib; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null \
    || die "'python' must be 3.12+ (tomllib). Run via 'mise run release'."

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

  # Remote latest tag (best-effort; stays quiet offline). Shown alongside the
  # local tag so the release version is chosen against both. Never push from
  # here; the push gate (check-version-tag) catches a forgotten --follow-tags.
  local remote_tag="" remote_refs="" escaped_version=""
  if remote_refs="$(git ls-remote --tags origin 2>/dev/null)"; then
    remote_tag="$(latest_remote_tag "$remote_refs")"
  fi
  if [[ -n $remote_tag && -n $last_tag ]]; then
    log_info "Latest tags: local ${last_tag}, remote ${remote_tag}."
  elif [[ -n $remote_tag ]]; then
    log_info "Latest tags: local none, remote ${remote_tag}."
  elif [[ -n $last_tag ]]; then
    log_info "Latest local tag: ${last_tag} (origin unreachable or no remote tags)."
  fi

  # 3. Determine the version to release. The suggestion is always the next
  # patch, regardless of feat/breaking commits.
  local suggested explicit=0
  suggested="$(suggested_version "$current_version" "$last_tag" "$remote_tag")" \
    || die "Cannot derive a patch version from pyproject (${current_version})${last_tag:+ or tag ${last_tag}}${remote_tag:+ or remote tag ${remote_tag}}. Pass --version X.Y.Z explicitly."
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
  # Never move a published tag: abort when the version tag exists on origin.
  escaped_version="${VERSION//./\\.}"
  if git ls-remote --tags origin 2>/dev/null | grep -Eq --color=never "refs/tags/${escaped_version}(\\^\\{\\})?$"; then
    die "Tag '${VERSION}' already exists on origin. Never move a published tag; pick a new version."
  fi
  # Never go backwards: above the highest of pyproject version / latest local
  # tag / latest remote tag.
  # Exception: a first release (no tags) may equal the pyproject version.
  if ! python - "$VERSION" "$current_version" "$last_tag" "$remote_tag" <<'EOF' >/dev/null 2>&1
import sys
def key(v):
    return tuple(int(p) for p in v.split("."))
ver, cur, last, remote = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
known = [v for v in (cur, last, remote) if v]
floor = max(key(v) for v in known)
if last or remote:
    ok = key(ver) > floor
else:
    ok = key(ver) >= floor
sys.exit(0 if ok else 1)
EOF
  then
    die "Version ${VERSION} must be above pyproject (${current_version})${last_tag:+ and tag ${last_tag}}${remote_tag:+ and remote tag ${remote_tag}}."
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
    gum confirm "Amend HEAD and tag ${VERSION}?" --default \
      || { printf 'Aborted, HEAD untouched.\n'; exit 0; }
  fi

  # 8. Amend + tag. Release files are folded into HEAD so the version bump
  # never forms a standalone release commit. Historical `chore(release)`
  # commits stay in cliff.toml's skip list so old releases never pollute
  # future changelogs.
  if ! git commit --amend --no-edit; then
    printf 'Amend failed (hooks may have modified files).\n' >&2
    printf "Inspect with 'git status', stage fixes, then finish manually:\n" >&2
    printf '  git commit --amend --no-edit && git tag %s\n' "$VERSION" >&2
    exit 1
  fi
  git tag "$VERSION" || die "Tagging '${VERSION}' failed."

  # 9. Never push automatically.
  log_ok "Released ${VERSION}."
  printf "Review, then push: git push --follow-tags\n"
}

main "$@"
