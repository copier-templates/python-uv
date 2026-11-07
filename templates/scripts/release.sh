#!/usr/bin/env bash
# Cut a release: bump [project] version, re-lock, regenerate CHANGELOG.md,
# amend HEAD, and tag. Never pushes. Shows local vs origin tags before prompting.
# Interactive via gum on a TTY, flag-driven otherwise (CI-safe).
#
#   scripts/release.sh [--version X.Y.Z] [--bump patch|minor|major] [--yes] [--print-version]
#   scripts/release.sh --help
#
# Env overrides (same as flags, win over nothing — flags win over env):
#   RELEASE_VERSION, RELEASE_BUMP, RELEASE_YES=1
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/release-common.sh
source "$SCRIPT_DIR/lib/release-common.sh"
VERSION_PY="$SCRIPT_DIR/release_version.py"

VERSION=""
BUMP=""
BUMP_GIVEN=0
PRINT_VERSION=0
ASSUME_YES=0

usage() {
  cat <<'EOF'
Usage:
  release.sh [--version X.Y.Z | --bump patch|minor|major] [--yes]
  release.sh --print-version [--version X.Y.Z | --bump patch|minor|major]
  release.sh --help

Cut a release in the current repository:
  1. determines the next version (patch bump by default, or --bump/--version;
     conventional commits only shape the changelog)
  2. bumps [project] version in pyproject.toml and re-locks uv.lock
  3. regenerates CHANGELOG.md, amends HEAD, and tags (never pushes)

With --print-version the script prints the version it would release and
exits 0 without touching the working tree (used by CI to preview the
version before cutting the release). An explicit --version preview still
runs the tag-exists and version-floor checks; a --bump preview is pure.

Options:
  --version X.Y.Z   release this exact version (default: prompt on a TTY,
                    or the suggested bump with --yes)
  --bump KIND       bump the highest known version by KIND (patch, minor or
                    major); cannot be combined with --version
  --print-version   print the release version and exit (no tree changes)
  --yes             non-interactive: accept the suggested version, skip
                    confirmations, and allow releasing from a non-main/master
                    branch (required when not on a TTY)
  --help            print this help and exit

Environment:
  RELEASE_VERSION   same as --version
  RELEASE_BUMP      same as --bump
  RELEASE_YES=1     same as --yes

Exit codes:
  0  success (or the printed version with --print-version)
  1  release refused (dirty tree, tag exists, version not above known, ...)
  2  usage error (unknown flag, invalid version, missing value, --version with --bump)

Examples:
  scripts/release.sh
  scripts/release.sh --bump minor --yes
  scripts/release.sh --version 0.4.0 --yes
  scripts/release.sh --bump major --print-version
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
    --bump)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      BUMP="$2"
      BUMP_GIVEN=1
      shift 2
      ;;
    --version=*)
      VERSION="${1#--version=}"
      shift
      ;;
    --bump=*)
      BUMP="${1#--bump=}"
      BUMP_GIVEN=1
      shift
      ;;
    --print-version)
      PRINT_VERSION=1
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
BUMP="${BUMP:-${RELEASE_BUMP:-patch}}"
if [[ -n "${RELEASE_BUMP:-}" ]]; then
  BUMP_GIVEN=1
fi
if [[ "${RELEASE_YES:-0}" == "1" ]]; then
  ASSUME_YES=1
fi
if [[ ! $BUMP =~ ^(patch|minor|major)$ ]]; then
  printf 'Invalid bump %q: expected patch, minor or major.\n' "$BUMP" >&2
  exit 2
fi
if [[ -n $VERSION && $BUMP_GIVEN == 1 ]]; then
  printf 'release.sh: pass either --version or --bump, not both.\n' >&2
  exit 2
fi

is_interactive() {
  [[ -t 0 && -t 1 ]] && command -v gum >/dev/null 2>&1
}

main() {
  git rev-parse --show-toplevel >/dev/null 2>&1 || die "Not inside a git repository."
  cd "$(git rev-parse --show-toplevel)"

  # 1. Preflight: working tree must be clean; HEAD must not already be a
  # release commit (release files amend HEAD, never form their own commit).
  # Skipped for --print-version: previewing is pure computation.
  if (( ! PRINT_VERSION )); then
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
  fi
  need_cmd python "Install it: mise install"
  if (( ! PRINT_VERSION )); then
    need_cmd git-cliff "Install it: mise install"
    need_cmd uv "Install it: mise install"
  fi
  python -c 'import sys, tomllib; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null \
    || die "'python' must be 3.12+ (tomllib). Run via 'mise run release'."

  # 2. Current version + latest tag (fresh repos may have no tags yet).
  # The latest tag is the highest reachable plain X.Y.Z (not git-describe
  # recency), so a stale branch cannot suggest a lower version.
  local current_version last_tag has_tags tag_lines
  current_version="$(python "$VERSION_PY" project-version)" \
    || die "Could not read [project] version from pyproject.toml."
  tag_lines="$(git tag --merged HEAD 2>/dev/null || true)"
  last_tag="$(printf '%s\n' "$tag_lines" | python "$VERSION_PY" latest-tag)" \
    || die "Could not compare tags by semver."
  has_tags=0
  if [[ -n $last_tag ]]; then
    has_tags=1
  elif [[ -n $tag_lines ]]; then
    log_warn "Reachable tags are not X.Y.Z; comparing against pyproject version only."
  fi
  if (( has_tags )) && (( ! PRINT_VERSION )) && git diff --quiet "${last_tag}..HEAD" --; then
    die "Nothing to release: no commits since tag ${last_tag}."
  fi

  # Remote latest tag (best-effort; stays quiet offline). Shown alongside the
  # local tag so the release version is chosen against both. Never push from
  # here; the push gate (check-version-tag) catches a forgotten --follow-tags.
  local remote_tag="" remote_refs="" escaped_version=""
  if remote_refs="$(git ls-remote --tags origin 2>/dev/null)"; then
    remote_tag="$(printf '%s\n' "$remote_refs" | python "$VERSION_PY" latest-remote-tag)" \
      || remote_tag=""
  fi
  if [[ -n $remote_tag && -n $last_tag ]]; then
    log_info "Latest tags: local ${last_tag}, remote ${remote_tag}."
  elif [[ -n $remote_tag ]]; then
    log_info "Latest tags: local none, remote ${remote_tag}."
  elif [[ -n $last_tag ]]; then
    log_info "Latest local tag: ${last_tag} (origin unreachable or no remote tags)."
  fi

  # 3. Determine the version to release. The suggestion is KIND bump above
  # the highest known version, regardless of feat/breaking commits.
  local suggested explicit=0
  suggested="$(python "$VERSION_PY" suggest \
    --bump "$BUMP" --current "$current_version" --local "$last_tag" --remote "$remote_tag")" \
    || die "Cannot derive a $BUMP version from pyproject (${current_version})${last_tag:+ or tag ${last_tag}}${remote_tag:+ or remote tag ${remote_tag}}. Pass --version X.Y.Z explicitly."
  if [[ -n $VERSION ]]; then
    explicit=1
  fi
  if is_interactive && (( ! explicit )) && (( ! PRINT_VERSION )); then
    VERSION="$(gum input --header "Release version" --prompt "Version: " --value "$suggested")" || exit 0
    [[ -n $VERSION ]] || die "No version entered, aborting."
  elif [[ -z $VERSION ]]; then
    if (( PRINT_VERSION )) || (( ASSUME_YES )); then
      VERSION="$suggested"
    else
      usage >&2
      die "Not interactive (no TTY or gum missing): pass --version X.Y.Z with --yes."
    fi
  fi
  [[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || die "Invalid version '${VERSION}': expected X.Y.Z (plain tags, no 'v' prefix)."
  # An explicit preview is still a release attempt: check the tag and the
  # version floor before printing. A --bump preview stays pure computation.
  if (( ! PRINT_VERSION )) || (( explicit )); then
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
    if ! python "$VERSION_PY" check-floor \
      --version "$VERSION" --current "$current_version" --local "$last_tag" --remote "$remote_tag"; then
      die "Version ${VERSION} must be above pyproject (${current_version})${last_tag:+ and tag ${last_tag}}${remote_tag:+ and remote tag ${remote_tag}}."
    fi
  fi
  if (( PRINT_VERSION )); then
    printf '%s\n' "$VERSION"
    exit 0
  fi

  log_info "Releasing ${VERSION} (pyproject was ${current_version})."

  # 4. Bump [project] version (the version module owns the TOML rewrite).
  python "$VERSION_PY" set-version "$VERSION" \
    || die "Could not update [project] version in pyproject.toml."

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
