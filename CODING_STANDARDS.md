# Coding standards

Disclosed reference; `AGENTS.md` Gate always applies. Only `templates/` ships.

## Changing `templates/`

Any `templates/` change needs an added or updated `tests/` regression test: add or strengthen tests only, never weaken them. `tests/` validates renders; `templates/tests/` is the test payload that ships.
A task-graph change in `templates/mise.toml.jinja` also updates `tests/test_rendered_mise.py`.
Each render of a variant with `Variant.runs_tasks` set costs a full `uv sync`: reuse `projects.render("<variant>")` (variants live in `VARIANTS` in `tests/_projects.py`) before adding a Copier render, and set `runs_tasks` on a new variant only when a test needs its task outcomes; other variants render with `skip_tasks=True`, so the switch never reaches Copier.
Root files marked as symlinks in [Template contract](#template-contract) are relative symlinks into `templates/`: edit `templates/`, never the root link. Root `.github/workflows/*.yml` are byte copies of the payload (Actions does not reliably follow symlinks); a test enforces they stay identical.

## Template contract

`mise.toml` and rendered projects expose only thin local wrappers (`bootstrap`, `release`) over pinned shared includes, verified by `tests/test_sync.py` and `tests/test_rendered_mise.py`. The version-tag gate (`scripts/check_version_tag.py`) runs only as the `check-version-tag` pre-push hook, never as a mise task. Rendered projects ship no agent guidance; their `mise.toml` task contract is their interface.

Verbatim payload files (copied unprocessed, never containing Jinja):

| Payload file | Root copy |
| --- | --- |
| `templates/prek.toml` | Symlink |
| `templates/cliff.toml` | Symlink |
| `templates/taplo.toml` | Symlink |
| `templates/.editorconfig` | Symlink |
| `templates/.github/workflows/*.yml` | Mirror |
| `templates/scripts/release.py` | Symlink |
| `templates/scripts/check_version_tag.py` | Symlink |
| `templates/scripts/sync_shared_refs.py` | Symlink |
| `templates/scripts/_version.py` | Symlink |

Keep this list in sync with the actual non-`.jinja` files under `templates/` (a regression test enforces it). `templates/licenses/` partials are Jinja includes, not verbatim copies.

## Working method

The main agent is the orchestrator and owns delivery: it applies these software engineering best practices — the smallest change that satisfies the task, only task-named files, no unrequested refactors or speculative abstraction, and a readable diff over cleverness. Single agent by default: do all work yourself unless the orchestrator opted into a subagent (independent parallel workstreams or a fresh-context review of a risky diff); subagents never spawn their own and review subagents stay read-only.
For `templates/` changes, test first: add or strengthen the `tests/` acceptance test, confirm it fails for the expected behavior reason (`mise run test:unit`), then implement the minimal change. Never weaken or delete a test to make it pass.
Verify with `mise run ci` green before delivery; run the affected mise task after each step. After 3 failed attempts, stop, run `git status` and `git diff --stat`, and escalate to the user.

## Shell

Multiline mise tasks open with a bash shebang (`#!/usr/bin/env bash`) and `set -euo pipefail`; mise honours the shebang, so modern bash is available without a version-floor task. Prefer `[[ ]]` over `[ ]` for tests and guards, keep `printf` over `echo`, `$(...)` over backticks, and prefer NUL-delimited input (`git ls-files -z`, `find -print0`) over newline `| xargs`.

Keep simple shell work inline in `mise.toml`: `test:integration` is an inline `[[ -d tests/integration ]]` skip. Logic that needs tests ships as stdlib-only Python under `templates/scripts/` and runs through `uv run python`: `_version.py` keeps the version and tag helpers pure (`release.py` and `check_version_tag.py` import them). Each payload script opens with an overview comment: a purpose one-liner, what the script does, and how it works, including edge cases (no reachable tags, offline). Payload scripts contain no Jinja and ship verbatim; the root `scripts/*.py` files (`release.py`, `check_version_tag.py`, `sync_shared_refs.py`, `_version.py`) stay symlinks into the payload, so edit `templates/scripts/`, never the root link.

## Refactoring

One behavior change per commit; run the affected mise task after each step.

## Security and `copier.yaml`

Keep secrets out of git; `.env` loads via mise (`_.file`) and stays untracked. Keep binaries out of git. Review `copier.yaml` `_tasks` (`uv python install`, `uv python pin`, `uv sync`, `mise trust`) and `tasks/lifecycle.py` (Git commit/init, `mise run install`/`ci`) like production code — they run on every copy or update. Silence Bandit (`S`) findings only with an inline why-comment; test-only findings go in `per-file-ignores`. Report vulnerabilities via `SECURITY.md` (private advisory, never a public issue).

## Commits and branches

Use Conventional Commits (`feat:`, `fix:`, `chore(deps):`), enforced by the `commit-msg` hook. Commit granular increments, one per task scope. Prek auto-fixers may rewrite files: re-run the affected mise task, then re-stage.
