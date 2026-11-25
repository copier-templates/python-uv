# Template Architecture

This document describes the structure and design of the Copier template.

## Overview

The template is built using [Copier](https://copier.readthedocs.io/), a project templating tool that uses Jinja2 for dynamic content generation.

## Configuration

### `copier.yaml`

The main template configuration file that defines:
- **Questions**: Interactive prompts, plus hidden computed render facts (see below)
- **Exclusions**: Files/directories not copied to rendered projects via `_exclude`
- **Tasks**: Post-copy/update steps via `_tasks` (see [Post-copy lifecycle](#post-copy-lifecycle))

### `python_version` Question

`python_version` is a `str` question declared directly after `project_type` and before `module_name`.

- **Default**: `3.12` (the minimum supported Python).
- **Choices**: static YAML pairs for released CPython 3.x cycles at or above 3.12, newest first.
- **Consumers**:
  - `_tasks` runs `uv python install <version>`, then `uv python pin <version>`, which writes the short `.python-version`; rendered `mise.toml` does not pin Python.
  - `templates/pyproject.toml.jinja` sets `requires-python = ">=<version>"` and Ruff `target-version = "py<major><minor>"`.
  - `.copier-answers.yml` records the answer so `copier update` replays it.

### Computed Render Facts

Hidden questions (`when: false`) derive render facts from the answers instead of prompting:

| Fact | Derived from |
|------|--------------|
| `is_app`, `is_lib`, `is_package` | `project_type` |
| `license_spdx` | `license_type`, mapped to an SPDX identifier |

- **Declaration**: `copier.yaml` keys with a Jinja `default` and `when: false`. Copier omits `when: false` questions from `.copier-answers.yml`, so facts are re-derived on every render and `copier update` never replays a stale value. `tests/test_rendered_project.py` pins this.
- **Ordering**: Each fact is declared after the answers it reads. `_envops.undefined` is `jinja2.StrictUndefined`, so an earlier default would fail to render.
- **Naming**: `_`-prefixed keys are reserved for Copier settings, so facts use plain names.
- **Consumers**: `_exclude` (`is_app`, `is_lib`, `include_license`, `github_integration`), and the templates `pyproject.toml.jinja`, `mise.toml.jinja`, `README.md.jinja`, `src/{{module_name}}/__init__.py.jinja` and `tests/unit/test_init.py.jinja`.

The `module_name` question uses the same mechanism: `type: str`, a Jinja `default`, and `when: false`.

### Post-copy Lifecycle

`_tasks` in `copier.yaml` runs, in order: `uv python install <python_version>`, `uv python pin <python_version>`, `uv sync`, `mise trust`, then `tasks/lifecycle.py {copy|update}` (copy and update only).

`tasks/lifecycle.py` is a stdlib-only script (Copier runs it with its own interpreter), invoked from the template source via `_copier_conf.src_path`. It never ships, because only `templates/` is copied.

- **Inside a Git work tree**: stage everything and commit `chore: scaffold from copier template` (copy) or `chore: update from copier template` (update), only when something is staged.
- **Outside one**: a copy runs `git init` and commits `Init commit`; an update does nothing.
- Commits bypass hooks, since hooks are installed later by `mise run install`.
- Then `mise run install`, and `mise run ci`.

Keeping this logic in a script rather than YAML shell one-liners lets `tests/test_lifecycle.py` exercise it against real Git in temporary directories.

## Template Structure

Only `templates/` ships (`_subdirectory: templates` in `copier.yaml`): `*.jinja` renders,
the rest copies verbatim per [Template contract](../CODING_STANDARDS.md#template-contract).
Everything outside `templates/` is tooling that never ships.

### Shared Task Includes

The root and every rendered `mise.toml` import task files over the network from
[`copier-templates/shared-dev-tooling`](https://github.com/copier-templates/shared-dev-tooling):

```text
git::https://github.com/copier-templates/shared-dev-tooling.git//tasks/core?ref=0.2.1
git::https://github.com/copier-templates/shared-dev-tooling.git//tasks/toml?ref=0.2.1
git::https://github.com/copier-templates/shared-dev-tooling.git//tasks/py?ref=0.2.1
git::https://github.com/copier-templates/shared-dev-tooling.git//tasks/cicd/github?ref=0.2.1
```

All four `?ref=` values must equal the `rev` (and the `[update.repos]`
`include_tags`) of the shared repo in `prek.toml`: one tag supplies the shared
hook environments and the shared task definitions, and `tests/test_sync.py`
fails when the pair drifts. `prek.toml` pins the repo through
`[update.repos]`, so `prek update` never advances it alone; moving to a new
shared release is `uv run python scripts/sync_shared_refs.py --to X.Y.Z`,
which moves the root `mise.toml`, `templates/mise.toml.jinja`,
`templates/prek.toml` and `tests/_projects.py` together. The
`sync-shared-refs` pre-commit hook runs the script with `--check` and blocks
drifted commits. mise caches remote `git::` includes, so after changing a ref
run `mise run mise:cache:clear`; the next `mise` command re-clones the include,
while a cold cache (fresh clone or CI) fetches it on first use.

## Excluded Directories

Only `templates/` is copied to rendered projects. Everything outside it —
`examples/`, `tests/`, `docs/`, `tasks/`, `copier.yaml` itself — is
template tooling and, except for the symlinked root `scripts/*.py` files
below, never lands in rendered projects. Root `scripts/*.py`
files are symlinks into the
`templates/scripts/` payload (see
[Template contract](../CODING_STANDARDS.md#template-contract)), so those
scripts ship with rendered projects. They are stdlib-only Python, run through
`uv run python`, and tested directly; the integration and workflow-lint
skips are inline bash `[[ -d ]]` tests in `mise.toml` and need no payload script.

Within `templates/`, `licenses/` partials are excluded from copy via `_exclude`
(they are only used through `{% include %}` in `LICENSE.jinja`).

## Templating Conventions

### Variable Interpolation

Use double-brace syntax for Jinja2 variables:

```jinja
Project: {{ project_name }}
Author: {{ user_name }}
Python: {{ python_version }}
```

### Conditional Sections

Make files and directories conditional by templating their names with Jinja expressions. For example, a file rendered only when the `is_app` fact is true:

```
{% if is_app %}main.py{% endif %}.jinja
```

Important: keep the template suffix (`.jinja`) outside the Jinja expression. If the suffix is inside the condition the file won't be treated as a template and will be copied verbatim.

Optional content inside a file uses Jinja conditionals; whole files are usually
gated with `_exclude` instead, as `copier.yaml` does for `src/`, `main.py`,
`LICENSE` and `.github/`. See `tests/test_rendered_project.py`,
`tests/test_rendered_pyproject.py` and `tests/test_rendered_mise.py` for expected
behavior, and the official Copier docs
("Conditional files and directories") for more details.

### File Extensions

- `.jinja` - Files that require template rendering
- No extension - Static files copied as-is

Example:
```
templates/README.md.jinja       # Rendered with Jinja2
templates/prek.toml             # Copied without processing
```

## Testing

The test suite in `tests/` validates the template by rendering it with Copier
and asserting on the output. Key modules:

| Test | Purpose |
|------|---------|
| `test_sync.py` | Root symlinks, workflow byte copies, tool pins, shared-include wiring/thin wrappers, and the payload line-ending rules (no `*.sh` rule) |
| `test_lifecycle.py` | `tasks/lifecycle.py` through `run()`/`main()` against real Git, including the fake-`mise` CLI order |
| `test_copier_update.py` | `copier update` against the git-backed template repo (`v1.0.0` → `v1.0.1`) |
| `test_rendered_project.py` | Rendered layout, project types, exclusions, payload tests, README, answers facts and `cliff.toml` |
| `test_rendered_pyproject.py` | Rendered pyproject tooling, pytest, coverage, ty, ruff and section spacing |
| `test_rendered_mise.py` | Rendered mise task graph, CI order, lint/fix, gating, entrypoints and pytest split |
| `test_release.py` | Python `release.py`/`check_version_tag.py` pure helpers and CLI against real repos with fake `uv`, `git-cliff` and `git` |
| `test_prek.py` | `prek.toml` security pins, priority tiers and formatter scope |
| `test_repo_hygiene.py` | Taplo-clean root TOML, agent roster, verbatim payload list and Copier settings |
| `test_licenses.py` | License choices, partials, SPDX identifiers and rendered license fields |
| `test_python_versions.py` | `python_version` choices, rendered pins and the short `.python-version` |

### Test Fixtures

The render pipeline lives in `tests/_projects.py`, the one harness module test
files import from. It provides `GitRepo`, `RenderedProject`, `Variant`,
`VARIANTS`, `ProjectRegistry`, the template snapshot (`snapshot_template_root`),
the git-backed template repo builder (`make_git_template_repo`), the render
entry point (`run_copy_from`) and the shared helpers (`load_toml`,
`copier_config`, `refs`, `git`, `BASE_DATA`). `tests/conftest.py` hosts only
fixtures (`template_source`, `projects`, `git_template_repo`).

- **Session-scoped `projects` registry**: `projects.render("<variant>")` renders each variant once per session, into pytest's `tmp_path_factory`
- **Task variants**: `VARIANTS` maps a name to a `Variant` holding Copier answers and `runs_tasks`; only `basic` sets `runs_tasks=True` and renders with `copier.yaml` `_tasks` (a full `uv sync` each), while all others render with `skip_tasks=True`
- **Rendered projects**: `RenderedProject` exposes `path`, `answer(name)`, `project_name`, `module_name`, `read()`, `pyproject()`, `mise()`, `mise_tools()`, plus the git queries `git()`, `subjects()`, `commit_files()`, `tracked()` and `status()`
- **Read-only operations**: All tests are non-mutating to enable fixture reuse

## References

For Copier variable types, answer files, and the update flow for rendered projects, see the [Copier Documentation](https://copier.readthedocs.io/en/stable/).

- [Copier Documentation](https://copier.readthedocs.io/en/stable/)
- [Jinja2 Template Documentation](https://jinja.palletsprojects.com/)
- [Python Packaging Guide](https://packaging.python.org/)
