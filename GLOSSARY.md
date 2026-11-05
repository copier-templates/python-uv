# Glossary

Domain terms for this Copier template. Use them as written.

**Payload**
: The contents of `templates/`, the only part Copier copies into generated projects.

**Verbatim payload**
: Payload files copied without Jinja rendering. Canonical list: [Template contract](CODING_STANDARDS.md#template-contract).

**Root tooling**
: Files at the repo root that develop or release this template (`prek.toml`, `cliff.toml`, `.editorconfig`, `scripts/release.sh`, workflows). Never shipped unless they are also in the payload.

**Symlink**
: A root tooling file that points into `templates/`, the single source of truth. See [ADR 0001](docs/adr/0001-symlink-root-tooling-to-payload.md).

**Mirror**
: A byte-identical copy of a payload file kept at the root. Used only for `.github/workflows/*.yml`, which Actions does not reliably load through a symlink.

**Answer**
: A value given for a question in `copier.yaml`. Recorded in `.copier-answers.yml` unless the question is a render fact.

**Render fact**
: A hidden `when: false` question whose value is computed from answers (for example `is_app`, `with_ruff`, `verify_ci`). Re-derived on every render; omitted from the answers file.

**Render**
: Copier producing a project from `templates/` and the answers. Tests render through `projects.render("<variant>")`.

**Variant**
: A named set of answers in `VARIANTS` (`tests/_projects.py`), rendered once per test session.

**Task variant**
: A variant listed in `TASK_VARIANTS`, rendered with `copier.yaml` `_tasks`. Other variants render with `skip_tasks=True`.

**Lifecycle script**
: `tasks/lifecycle.py`, run from `_tasks` after copy or update. Makes the Git commit or init and runs `mise run install` (and `mise run ci` when `verify_ci`).

**Task contract**
: The mise task names that both root `mise.toml` and generated projects expose, pinned as `TASK_CONTRACT` in `tests/test_sync.py`.

**Gate**
: `mise run ci`, the check that must be green before delivery ([AGENTS.md](AGENTS.md)).
