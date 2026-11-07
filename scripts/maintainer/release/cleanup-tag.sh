#!/usr/bin/env bash
# Delete tags that never reached main (abandoned release PRs).
# Used by .github/workflows/release.yml (cleanup job). Runs in a full-history
# checkout. Finds tags pointing at the closed PR head SHA and deletes those
# absent from the mainline. Never touches mainline tags. Needs no network
# beyond the tag delete itself.
#
#   cleanup-tag.sh --sha SHA [--remote REMOTE]
#
# Exits 0 on skips; 1 on usage errors or when a delete fails.
set -euo pipefail

SHA=""
REMOTE="origin"

usage() {
  cat <<'EOF'
Usage:
  cleanup-tag.sh --sha SHA [--remote REMOTE]
  cleanup-tag.sh --help

Delete origin tags pointing at the closed PR head SHA when their commits
never merged to the mainline. Prints what it keeps and deletes.
EOF
}

die() {
  printf 'cleanup-tag: %s\n' "$*" >&2
  exit 1
}

usage_error() { # <message>
  usage >&2
  printf 'cleanup-tag: %s\n' "$1" >&2
  exit 2
}

need_cmd() { # <cmd>
  command -v "$1" >/dev/null 2>&1 || die "Required tool '$1' not found."
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha)
      [[ $# -ge 2 ]] || usage_error "Missing value for --sha."
      SHA="$2"
      shift 2
      ;;
    --remote)
      [[ $# -ge 2 ]] || usage_error "Missing value for --remote."
      REMOTE="$2"
      shift 2
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
      usage_error "Unknown option: $1"
      ;;
    *)
      usage_error "Unexpected argument: $1"
      ;;
  esac
done
[[ -n $SHA ]] || usage_error "--sha is required."
need_cmd git

tags="$(git tag --points-at "$SHA" || true)"
if [[ -z $tags ]]; then
  echo "No tags point at $SHA; nothing to clean."
  exit 0
fi

while IFS= read -r tag; do
  [[ -n $tag ]] || continue
  if git merge-base --is-ancestor "$tag" "$REMOTE/main"; then
    echo "Tag $tag is on mainline; keeping."
    continue
  fi
  printf 'Deleting orphan tag %s.\n' "$tag"
  git push --delete "$REMOTE" "$tag"
done <<< "$tags"
