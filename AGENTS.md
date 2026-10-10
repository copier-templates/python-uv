# AGENTS.md — working in this repo

This repo is a **Copier template** for Python + `uv` projects, not a regular app:

- `*.jinja` files are templates rendered into generated projects; plain files are this repo's own tooling.
- `my_tests/` validates the template by rendering it with Copier and asserting on the output.
  `tests/` is itself a template (note `__init__.py.jinja`).
- `scripts/`, `docs/`, `examples/`, `my_tests/` — and this `AGENTS.md` itself —
  never land in generated projects (`_exclude` in `copier.yaml`, enforced by
  `my_tests/test_exclusions.py`). Agent guidance for generated projects is
  deliberately not shipped; their `mise.toml` task contract (rule 4) is the interface.

## Always use mise tasks — never call tools directly

The toolchain (Python, `uv`, `shellcheck`) is pinned in `mise.toml`. Run:

| Command                   | Purpose                                            |
| ------------------------- | -------------------------------------------------- |
| `mise run install`        | First-time setup (`uv sync --dev` + pre-commit)    |
| `mise run lint`           | All linters (Ruff for Python, ShellCheck for `*`) |
| `mise run lint:python` / `mise run lint:shell` | Single-language lint                |
| `mise run format`         | Ruff formatter                                     |
| `mise run unit`           | Template validation tests (`my_tests/`)            |
| `mise run test`           | Full test suite                                    |
| `mise run ci`             | Pre-push gate: `lint` + `unit` + `format`          |

Do not invoke `ruff`, `pytest`, or `shellcheck` binaries directly — versions would drift
from the pinned toolchain. `pre-commit` hooks mirror the same linters as a second gate;
keep both in sync (see below).

## Rules for code changes / refactoring

1. **Test before pushing.** `mise run unit` while iterating, `mise run ci` before
   opening a PR. A green `ci` is required — it is what `test.yml` runs.
2. **Lint everything you touch.** `mise run lint` must be clean: Ruff for `*.py`,
   ShellCheck (`shellcheck -x`) for every `*.sh`. Shell code is modern bash only:
   `#!/usr/bin/env bash` + `set -euo pipefail` header (also on multiline mise tasks),
   `[[ ]]` / `(( ))` tests, `printf` over `echo`, arrays with NUL-delimited input
   (`git ls-files -z`, `find -print0`) — no legacy `[ ]`, backticks, or
   newline-delimited `| xargs` (enforced by the `script-must-have-extension` /
   `check-executables-have-shebangs` hooks and `test_mise_toml_uses_modern_bash`).
3. **Changing any `*.jinja` template? Add or update a regression test in `my_tests/`.**
   Changing the task graph in `mise.toml.jinja` requires updating
   `my_tests/test_conditional_sections.py`. Hook versions live in the single
   `.pre-commit-config.yaml`, which ships verbatim into generated projects
   (like `.github/workflows/*.yml`) — there is no `.jinja` mirror to keep
   in sync.
4. **Keep the template contract aligned.** `mise.toml` (this repo) and `mise.toml.jinja`
   (generated projects) must expose the same task names (`lint`, `lint:python`,
   `lint:shell`, `format`, `unit`, `test`, `ci`, `clean`) so muscle memory transfers.
5. **Refactor in small, verifiable steps.** One behavior change per commit, run the
   affected `mise` task after each step, and prefer extending existing
   session-scoped fixtures in `my_tests/conftest.py` over adding new Copier renders
   (each render costs a full `uv sync`).

## Security rules

- Never commit secrets: `.env` is loaded via mise (`_.file`) and must stay untracked;
  the `detect-private-key` hook is the backstop, not the plan.
- No binaries in git (`forbid-binary` hook); no `curl | bash` in scripts or tasks.
- Copier `_tasks` execute on every render (`uv sync`, `git init`, `mise trust`) —
  review them like production code when touching `copier.yaml`.
- Python lint includes Bandit (`S`) rules — do not silence them without a comment
  explaining why. Test-only suppressions belong in `per-file-ignores`, not inline.
- Report vulnerabilities per `SECURITY.md` (private advisory, never a public issue).

## Commits

Conventional Commits are enforced by the `commit-msg` hook
(e.g. `feat:`, `fix:`, `chore(deps):`). Pre-commit auto-fixers may modify your files —
re-run the affected `mise` task and re-stage before committing.
