#!/usr/bin/env bash
# Check that pyproject.toml [project] version equals the max-semver plain X.Y.Z
# tag reachable from HEAD. Blocks both drift directions:
#   version > tag  -> bumped without tagging (run release / tag / push --follow-tags)
#   tag > version  -> tag moved ahead (never delete the tag; bump pyproject)
# No tags reachable -> pass (fresh repo). Offline-safe: remote checks warn only.
#
#   scripts/check-version-tag.sh [--help]
set -euo pipefail

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
  printf 'Unexpected argument: %s\n' "$1" >&2
  usage >&2
  exit 2
fi

git rev-parse --show-toplevel >/dev/null 2>&1 || {
  printf 'Not inside a git repository.\n' >&2
  exit 1
}
cd "$(git rev-parse --show-toplevel)"

current_version="$(python - <<'EOF'
import tomllib
with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
EOF
)" || {
  printf 'Could not read [project] version from pyproject.toml.\n' >&2
  exit 1
}
if [[ ! $current_version =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  printf 'Invalid pyproject version %q: expected X.Y.Z.\n' "$current_version" >&2
  exit 1
fi

# Newest reachable plain X.Y.Z tag by semver (git describe is recency, not max).
# Portable read loop: `mapfile` needs bash 4+, macOS ships bash 3.2.
tags=()
while IFS= read -r tag; do
  tags+=("$tag")
done < <(git -c color.ui=false tag --merged HEAD 2>/dev/null | grep -E --color=never '^[0-9]+\.[0-9]+\.[0-9]+$' || true)
latest=""
if (( ${#tags[@]} > 0 )); then
  latest="$(printf '%s\n' "${tags[@]}" | python -c 'import sys; print(sorted((tuple(map(int, l.strip().split("."))), l.strip()) for l in sys.stdin if l.strip())[-1][1])')" || {
    printf 'Could not compare tags by semver.\n' >&2
    exit 1
  }
fi

if [[ -z $latest ]]; then
  printf 'No X.Y.Z tags reachable from HEAD; pyproject is %s. OK.\n' "$current_version"
  exit 0
fi

if [[ $current_version == "$latest" ]]; then
  printf 'pyproject version %s matches latest tag %s. OK.\n' "$current_version" "$latest"
  # Best-effort reminder when the tag is not on the remote yet (offline-safe).
  if remote_tags="$(git ls-remote --tags origin 2>/dev/null)" && ! grep -q "refs/tags/${latest}$" <<<"$remote_tags"; then
    printf 'Note: tag %s is not on origin yet; push with: git push --follow-tags\n' "$latest"
  fi
  exit 0
fi

higher="$(printf '%s\n%s\n' "$current_version" "$latest" | python -c 'import sys; vs=[(tuple(map(int, l.strip().split("."))), l.strip()) for l in sys.stdin]; print(sorted(vs)[-1][1])')"
if [[ $higher == "$current_version" ]]; then
  printf 'Blocked: pyproject version %s is ahead of latest tag %s.\n' "$current_version" "$latest" >&2
  printf 'You bumped without tagging. Fix with: mise run release --version %s --yes, then: git push --follow-tags\n' "$current_version" >&2
else
  printf 'Blocked: latest tag %s is ahead of pyproject version %s.\n' "$latest" "$current_version" >&2
  printf 'Never delete the tag. Fix with: mise run release (--version above %s), then: git push --follow-tags\n' "$latest" >&2
fi
exit 1
