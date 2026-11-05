# 0001. Symlink root tooling to the payload

Status: Accepted

## Context

`prek.toml`, `cliff.toml`, `.editorconfig` and `scripts/release.sh` are used both
by this repository (hooks, changelog, release) and shipped in generated projects
from `templates/`. Keeping two copies let them drift.

GitHub Actions does not reliably follow symlinked workflow files, so workflows
cannot use the same approach.

## Decision

- The four root files are relative symlinks into `templates/`. Edit `templates/`, never the root link.
- Root `.github/workflows/*.yml` stay byte copies of `templates/.github/workflows/*.yml`.
- `tests/test_sync.py` asserts that each symlink resolves into `templates/`, and that each workflow pair is byte-identical.

## Consequences

- One source of truth for shared tooling; the only drift risk is workflows, and a test covers it.
- Editing a root link by mistake changes nothing in the payload. The symlink test fails if a root file is not a symlink resolving to `templates/`, which points the edit back to the source.
