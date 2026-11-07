#!/usr/bin/env bash
# Resolve the release bump kind for a PR from its release label.
# Used by .github/workflows/release.yml (release job).
#
#   release-resolve-version.sh --sha SHA --repo OWNER/REPO [--output FILE]
#   release-resolve-version.sh --pr NUMBER --repo OWNER/REPO [--output FILE]
#
# A PR carrying exactly one release:patch|minor|major label is a release PR.
# Writes release=<true|false> (plus pr, head_ref, bump when true) to
# --output (default: $GITHUB_OUTPUT, else stdout). Exits 0 on skip/success;
# exits 1 when the PR carries several release labels. Reads $GH_TOKEN via gh.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Prefix exit-1 diagnostics with this script's name (pre-refactor stderr).
SCRIPT_NAME="release-resolve-version"
# shellcheck source=scripts/maintainer/lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

SHA=""
PR=""
REPO=""
OUTPUT="${GITHUB_OUTPUT:-}"

usage() {
  cat <<'EOF'
Usage:
  release-resolve-version.sh --sha SHA --repo OWNER/REPO [--output FILE]
  release-resolve-version.sh --pr NUMBER --repo OWNER/REPO [--output FILE]
  release-resolve-version.sh --help

Resolve the release bump kind for a PR (by head SHA or number) from its
release:patch|minor|major label. Prints skip/fail reasons to stderr.
Issue metadata and version numbers are never read: the label alone decides.
EOF
}

usage_error() { # <message>
  usage >&2
  printf 'release-resolve-version: %s\n' "$1" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sha)
      [[ $# -ge 2 ]] || usage_error "Missing value for --sha."
      SHA="$2"
      shift 2
      ;;
    --pr)
      [[ $# -ge 2 ]] || usage_error "Missing value for --pr."
      PR="$2"
      shift 2
      ;;
    --repo)
      [[ $# -ge 2 ]] || usage_error "Missing value for --repo."
      REPO="$2"
      shift 2
      ;;
    --output)
      [[ $# -ge 2 ]] || usage_error "Missing value for --output."
      OUTPUT="$2"
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
[[ -n $REPO ]] || usage_error "--repo is required."
if [[ -n $SHA && -n $PR ]] || [[ -z $SHA && -z $PR ]]; then
  usage_error "Exactly one of --sha and --pr is required."
fi
need_cmd gh

emit() { # <line>
  if [[ -n $OUTPUT ]]; then
    printf '%s\n' "$1" >> "$OUTPUT"
  else
    printf '%s\n' "$1"
  fi
}

if [[ -n $PR ]]; then
  prs_json="$(gh api "repos/$REPO/pulls/$PR" | python3 -c 'import json,sys; print(json.dumps([json.load(sys.stdin)]))')"
  no_pr_message="PR #$PR is not open or does not target main; nothing to release."
else
  prs_json="$(gh api "repos/$REPO/commits/$SHA/pulls")"
  no_pr_message="No open PR targeting main for $SHA; nothing to release."
fi
# Select the open PR targeting main; extract its head ref and release labels.
# Prints: number, head ref, space-separated release bumps (possibly empty).
# Exit 3: no open PR for this repo+SHA/number. (Program via -c so piped JSON stays on stdin.)
selection="$(printf '%s' "$prs_json" | python3 -c '
import json
import sys

prs = json.load(sys.stdin)
open_main = [p for p in prs if p.get("state") == "open" and (p.get("base") or {}).get("ref") == "main"]
if not open_main:
    sys.exit(3)
pr = open_main[0]
labels = [label.get("name", "") for label in pr.get("labels") or []]
bumps = sorted({name.partition(":")[2] for name in labels if name.startswith("release:")})
print(pr["number"])
print(pr["head"]["ref"])
print(" ".join(bumps))
' || exit $?)" || {
  rc=$?
  if (( rc == 3 )); then
    printf '%s\n' "$no_pr_message" >&2
    emit "release=false"
    exit 0
  fi
  die "Could not parse PR lookup response."
}

pr="$(printf '%s' "$selection" | sed -n '1p')"
head_ref="$(printf '%s' "$selection" | sed -n '2p')"
bump_list="$(printf '%s' "$selection" | sed -n '3p')"

read -ra bumps <<< "$bump_list"
if (( ${#bumps[@]} == 0 )); then
  printf 'PR #%s carries no release label; not a release PR, skipping.\n' "$pr" >&2
  emit "release=false"
  exit 0
fi
if (( ${#bumps[@]} > 1 )); then
  die "PR #$pr carries several release labels (${bumps[*]}); keep exactly one of release:patch, release:minor, release:major."
fi
bump="${bumps[0]}"
if [[ ! $bump =~ ^(patch|minor|major)$ ]]; then
  die "PR #$pr carries unknown release label 'release:$bump'; use release:patch, release:minor or release:major."
fi

emit "release=true"
emit "pr=$pr"
emit "head_ref=$head_ref"
emit "bump=$bump"
