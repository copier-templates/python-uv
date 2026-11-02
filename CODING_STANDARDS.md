# Coding standards

Disclosed reference; `AGENTS.md` Gate always applies. Only `templates/` ships.

## Changing `templates/`

Any `templates/` change needs an added or updated `tests/` regression test: add or strengthen tests only, never weaken them. `tests/` validates renders; `templates/tests/` is the test payload that ships.
A task-graph change in `templates/mise.toml.jinja` also updates `tests/test_conditional_sections.py`.
Each render costs a full `uv sync`: extend session fixtures in `tests/conftest.py` before adding a Copier render.
Hook versions live in root `prek.toml` and verbatim `templates/prek.toml`; keep both in sync (no `.jinja` mirror).

## Template contract

`mise.toml` and `templates/mise.toml.jinja` expose the same task names: `lint`, `lint:python`, `lint:shell`, `format`, `test:unit`, `test:integration`, `test`, `ci`, `clean`. Maintenance tasks such as `update:python-versions` stay in root `mise.toml`. Generated projects ship no agent guidance; their `mise.toml` task contract is their interface.

Verbatim payload files (copied unprocessed, never containing Jinja): `templates/prek.toml`, `templates/.editorconfig`, `templates/.github/workflows/*.yml`, `templates/cliff.toml`, `templates/scripts/release.sh`. Keep this list in sync with the actual non-`.jinja` files under `templates/` (a regression test enforces it). `templates/licenses/` partials are Jinja includes, not verbatim copies.

## Shell

`*.sh` files and multiline mise tasks using bash features (`[[ ]]`, `(( ))`, arrays, process substitution) start with `#!/usr/bin/env bash` plus `set -euo pipefail`. POSIX-only tasks omit the header and rely on mise's `sh -o errexit`. Prefer `printf` over `echo`, `[[ ]]` over `[ ]`, `$(...)` over backticks, and NUL-delimited input (`git ls-files -z`, `find -print0`) over newline `| xargs`.

## Refactoring

One behavior change per commit; run the affected mise task after each step.

## Security and `copier.yaml`

Keep secrets out of git; `.env` loads via mise (`_.file`) and stays untracked. Keep binaries out of git. Never pipe `curl` into `bash`. Review `copier.yaml` `_tasks` (`uv sync`, `git init`, `mise trust`) like production code — they run on every render. Silence Bandit (`S`) findings only with an inline why-comment; test-only findings go in `per-file-ignores`. Report vulnerabilities via `SECURITY.md` (private advisory, never a public issue).

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
| `mise run ci`                                  | Pre-push gate: `lint` + `format:check` + `hooks` + `test:unit` |
