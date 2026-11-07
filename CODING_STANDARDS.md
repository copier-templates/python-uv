# Coding standards

Disclosed reference; `AGENTS.md` Gate always applies. Only `templates/` ships.

## Changing `templates/`

Any `templates/` change needs an added or updated `tests/` regression test: add or strengthen tests only, never weaken them. `tests/` validates renders; `templates/tests/` is the test payload that ships.
A task-graph change in `templates/mise.toml.jinja` also updates `tests/test_conditional_sections.py`.
Each render of a `TASK_VARIANTS` variant costs a full `uv sync`: reuse `projects.render("<variant>")` (variants live in `VARIANTS` in `tests/_projects.py`) before adding a Copier render, and list a new variant in `TASK_VARIANTS` only when a test needs its task outcomes (the rule is documented there); other variants render with `skip_tasks=True`.
Root files marked as symlinks in [Template contract](#template-contract) are relative symlinks into `templates/`: edit `templates/`, never the root link. Root `.github/workflows/*.yml` are mirrors of the payload (Actions does not reliably follow symlinks); a test enforces they stay identical.

## Template contract

`mise.toml` and generated projects expose the same core task names, pinned as `TASK_CONTRACT` in `tests/test_sync.py`. Maintenance tasks such as `update:python-versions` stay in root `mise.toml`. Generated projects ship no agent guidance; their `mise.toml` task contract is their interface.

Verbatim payload files (copied unprocessed, never containing Jinja):

| Payload file | Root copy |
| --- | --- |
| `templates/prek.toml` | Symlink |
| `templates/cliff.toml` | Symlink |
| `templates/taplo.toml` | Symlink |
| `templates/.editorconfig` | Symlink |
| `templates/.github/workflows/*.yml` | Mirror (Actions does not follow symlinks) |
| `templates/scripts/release.sh` | Symlink |
| `templates/scripts/check-version-tag.sh` | Symlink |
| `templates/scripts/release_version.py` | Symlink |
| `templates/scripts/lib/release-common.sh` | Symlink |

Keep this list in sync with the actual non-`.jinja` files under `templates/` (a regression test enforces it). `templates/licenses/` partials are Jinja includes, not verbatim copies.

`templates/scripts/release_version.py` owns all version math and `templates/scripts/lib/release-common.sh` owns the shared logging; both release scripts delegate to them. `.github/workflows/release.yml` and `scripts/maintainer/` are root-only maintainer automation (PR-triggered auto-release); they never ship to generated projects, and the workflow sync test carves them out.

## Shell

`*.sh` files and multiline mise tasks using bash features (`[[ ]]`, `(( ))`, arrays, process substitution) start with `#!/usr/bin/env bash` plus `set -euo pipefail`. POSIX-only tasks omit the header and rely on mise's `sh -o errexit`. Prefer `printf` over `echo`, `[[ ]]` over `[ ]`, `$(...)` over backticks, and NUL-delimited input (`git ls-files -z`, `find -print0`) over newline `| xargs`.

## Refactoring

One behavior change per commit; run the affected mise task after each step.

## Security and `copier.yaml`

Keep secrets out of git; `.env` loads via mise (`_.file`) and stays untracked. Keep binaries out of git. Never pipe `curl` into `bash`. Review `copier.yaml` `_tasks` (`uv python install`, `uv sync`, `mise trust`) and `tasks/lifecycle.py` (Git commit/init, `mise run install`/`ci`) like production code — they run on every copy or update. Silence Bandit (`S`) findings only with an inline why-comment; test-only findings go in `per-file-ignores`. Report vulnerabilities via `SECURITY.md` (private advisory, never a public issue).

## Commits and branches

Use Conventional Commits (`feat:`, `fix:`, `chore(deps):`), enforced by the `commit-msg` hook. Commit granular increments, one per task scope. Prek auto-fixers may rewrite files: re-run the affected mise task, then re-stage.

## Mise task map

| Command                                        | Purpose                                                        |
| ---------------------------------------------- | -------------------------------------------------------------- |
| `mise run install`                             | First-time setup (`uv sync --dev` + prek)                      |
| `mise run lint`                                | All linters (Ruff, ShellCheck, actionlint)                     |
| `mise run lint:python` / `mise run lint:shell` | Single-language lint                                           |
| `mise run format`                              | Ruff formatter                                                 |
| `mise run test:unit`                           | Template validation tests (`tests/`)                           |
| `mise run test:integration`                    | Integration tests (`tests/integration/`, skips when absent)    |
| `mise run test`                                | Aggregator: `test:unit` + `test:integration`                   |
| `mise run ci`                                  | Pre-push gate: `check:version-tag` + `lint` + `format:check` + `test:unit` |
| `mise run check:version-tag`                 | Block push when `pyproject.toml` version differs from latest tag |
