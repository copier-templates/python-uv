# AGENTS.md — working in this repo

This repo is a **Copier template** for Python + `uv` projects, not a regular app:

- `templates/` holds the Copier payload (`_subdirectory: templates` in `copier.yaml`).
  `*.jinja` files under `templates/` are rendered into generated projects;
  verbatim files under `templates/` (`prek.toml`, `.editorconfig`,
  `.github/workflows/*.yml`) are copied as-is. Plain files outside `templates/`
  are this repo's own tooling.
- `my_tests/` validates the template by rendering it with Copier and asserting on the output.
  `templates/tests/` is itself a template (note `__init__.py.jinja`).
- `scripts/`, `docs/`, `examples/`, `my_tests/` — and this `AGENTS.md` itself —
  never land in generated projects (only `templates/` is copied, enforced by
  `my_tests/test_exclusions.py`). Agent guidance for generated projects is
  deliberately not shipped; their `mise.toml` task contract (rule 4) is the interface.

## Always use mise tasks — never call tools directly

The toolchain (Python, `uv`, `shellcheck`) is pinned in `mise.toml`. Run:

| Command                   | Purpose                                            |
| ------------------------- | -------------------------------------------------- |
| `mise run install`        | First-time setup (`uv sync --dev` + prek)         |
| `mise run lint`           | All linters (Ruff for Python, ShellCheck for `*`) |
| `mise run lint:python` / `mise run lint:shell` | Single-language lint                |
| `mise run format`         | Ruff formatter                                     |
| `mise run unit`           | Template validation tests (`my_tests/`)            |
| `mise run test`           | Full test suite                                    |
| `mise run ci`             | Pre-push gate: `lint` + `unit` + `format`          |

Do not invoke `ruff`, `pytest`, or `shellcheck` binaries directly — versions would drift
from the pinned toolchain. `prek` hooks mirror the same linters as a second gate;
keep both in sync (see below).

## Rules for code changes / refactoring

1. **Test before pushing.** `mise run unit` while iterating, `mise run ci` before
   opening a PR. A green `ci` is required — it is what `test.yml` runs.
2. **Lint everything you touch.** `mise run lint` must be clean: Ruff for `*.py`,
   ShellCheck (`shellcheck -x`) for every `*.sh`. Shell code is modern bash only:
   `#!/usr/bin/env bash` + `set -euo pipefail` header on `*.sh` files and on
   multiline mise tasks that need bash features (`[[ ]]` / `(( ))`, arrays,
   process substitution); POSIX-only mise tasks omit the header and rely on
   mise's default `sh -o errexit`. Use `printf` over `echo`, arrays with
   NUL-delimited input (`git ls-files -z`, `find -print0`) — no legacy `[ ]`,
   backticks, or newline-delimited `| xargs` (enforced by the
   `script-must-have-extension` / `check-executables-have-shebangs` hooks and
   `test_mise_toml_uses_modern_bash` / `test_mise_toml_shebang_only_where_bash_needed`).
3. **Changing any file under `templates/`? Add or update a regression test in `my_tests/`.**
   Changing the task graph in `templates/mise.toml.jinja` requires updating
   `my_tests/test_conditional_sections.py`. Hook versions live in `prek.toml`
   (root) and `templates/prek.toml` (payload, shipped verbatim into generated
   projects like `templates/.github/workflows/*.yml`) — keep both in sync;
   there is no `.jinja` mirror.
4. **Keep the template contract aligned.** `mise.toml` (this repo) and `templates/mise.toml.jinja`
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
(e.g. `feat:`, `fix:`, `chore(deps):`). Prek auto-fixers may modify your files —
re-run the affected `mise` task and re-stage before committing.
