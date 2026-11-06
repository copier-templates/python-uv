# Template Architecture

This document describes the structure and design of the Copier template.

## Overview

The template is built using [Copier](https://copier.readthedocs.io/), a project templating tool that uses Jinja2 for dynamic content generation.

## Configuration

### `copier.yaml`

The main template configuration file that defines:
- **Questions**: Interactive prompts, plus hidden computed render facts (see below)
- **Exclusions**: Files/directories not copied to generated projects via `_exclude`
- **Tasks**: Post-copy/update steps via `_tasks` (see [Post-copy lifecycle](#post-copy-lifecycle))

### `python_version` Question

`python_version` is a `str` question declared directly after `project_type` and before `module_name`.

- **Default**: `3.12` (the minimum supported Python).
- **Choices**: released CPython 3.x cycles at or above 3.12, newest first. They live in a marker block delimited by `# python-version-choices: begin (managed by scripts/update_python_versions.py, do not edit)` and `# python-version-choices: end`.
- **Maintenance**: `scripts/update_python_versions.py` (run via `mise run update:python-versions`) fetches <https://endoflife.date/api/python.json> and rewrites only the lines between the markers. Never hand-edit between the markers; the script refuses to write when a marker is missing or duplicated, and it is idempotent.
- **Consumers**:
  - `_tasks` runs `uv python install <version>` before `uv sync`.
  - `templates/mise.toml.jinja` pins `python = "<version>"`.
  - `templates/pyproject.toml.jinja` sets `requires-python = ">=<version>"` and Ruff `target-version = "py<major><minor>"`.
  - `.copier-answers.yml` records the answer so `copier update` replays it.

### Computed Render Facts

Hidden questions (`when: false`) derive render facts from the answers instead of prompting:

| Fact | Derived from |
|------|--------------|
| `is_app`, `is_lib`, `is_package` | `project_type` |
| `license_spdx` | `license_type`, mapped to an SPDX identifier |

- **Declaration**: `copier.yaml` keys with a Jinja `default` and `when: false`. Copier omits `when: false` questions from `.copier-answers.yml`, so facts are re-derived on every render and `copier update` never replays a stale value. `tests/test_render_variants.py` pins this.
- **Ordering**: Each fact is declared after the answers it reads. `_envops.undefined` is `jinja2.StrictUndefined`, so an earlier default would fail to render.
- **Naming**: `_`-prefixed keys are reserved for Copier settings, so facts use plain names.
- **Consumers**: `_exclude` (`is_app`, `is_lib`, `include_license`, `github_integration`), and the templates `pyproject.toml.jinja`, `mise.toml.jinja`, `README.md.jinja`, `src/{{module_name}}/__init__.py.jinja` and `tests/unit/test_init.py.jinja`.

The `module_name` question uses the same mechanism: `type: str`, a Jinja `default`, and `when: false`.

### Post-copy Lifecycle

`_tasks` in `copier.yaml` runs, in order: `uv python install <python_version>`, `uv sync`, `mise trust`, then `tasks/lifecycle.py {copy|update}` (copy and update only).

`tasks/lifecycle.py` is a stdlib-only script (Copier runs it with its own interpreter), invoked from the template source via `_copier_conf.src_path`. It never ships, because only `templates/` is copied.

- **Inside a Git work tree**: stage everything and commit `chore: scaffold from copier template` (copy) or `chore: update from copier template` (update), only when something is staged.
- **Outside one**: a copy runs `git init` and commits `Init commit`; an update does nothing.
- Commits bypass hooks, since hooks are installed later by `mise run install`.
- Then `mise run install`, and `mise run ci`.

Keeping this logic in a script rather than YAML shell one-liners lets `tests/test_git_tasks.py` exercise it against real Git in temporary directories.

## Template Structure

Copier renders only `templates/` (`_subdirectory: templates` in `copier.yaml`).
All `*.jinja` files live under `templates/`; verbatim payload files live
alongside them (canonical list in
[Template contract](../CODING_STANDARDS.md#template-contract)).
License partials under `templates/licenses/` are Jinja includes excluded from copy.

```
├── templates/                   # Copier payload (_subdirectory)
│   ├── src/{{module_name}}/     # Package source (app excludes it; lib keeps py.typed)
│   │   ├── __init__.py.jinja
│   │   └── py.typed.jinja
│   ├── tests/unit/test_init.py.jinja  # Test payload of generated projects
│   ├── .github/workflows/       # test.yml, prek.yml (verbatim; excluded unless github_integration)
│   ├── licenses/                # License partials (Jinja includes, excluded from copy)
│   ├── prek.toml                # Git hooks (verbatim; root is a symlink)
│   ├── cliff.toml               # Changelog config (verbatim; root is a symlink)
│   ├── taplo.toml               # TOML formatting (verbatim; root is a symlink)
│   ├── .editorconfig            # Editor config (verbatim; root is a symlink)
│   ├── scripts/release.sh       # Release script (verbatim; root is a symlink)
│   ├── scripts/check-version-tag.sh  # Version-tag gate (verbatim; root is a symlink)
│   ├── .gitattributes.jinja
│   ├── .gitignore.jinja
│   ├── pyproject.toml.jinja     # Project configuration (templated)
│   ├── README.md.jinja          # Project README (templated)
│   ├── mise.toml.jinja          # Task runner config (templated)
│   ├── main.py.jinja            # App entrypoint (app only)
│   ├── LICENSE.jinja            # License file (optional, includes licenses/*)
│   └── {{ _copier_conf.answers_file }}.jinja  # Answers file
│
├── tasks/lifecycle.py           # Post-copy Git lifecycle script (never ships)
├── scripts/                     # Maintainer scripts (never ships)
├── examples/                    # Sample data files (never ships)
│   └── config-basic.yml
├── tests/                       # Test suite (never ships; see Testing)
├── docs/                        # Documentation and ADRs (never ships)
├── copier.yaml                  # Template configuration (_subdirectory: templates)
└── README.md                    # Template documentation
```

Root files listed as symlinks in the [verbatim payload table](../CODING_STANDARDS.md#template-contract)
are relative symlinks into `templates/`, so there is one source of truth. Root
`.github/workflows/*.yml` are byte copies of the payload instead, because
GitHub Actions does not reliably follow symlinked workflow files. Drift is
guarded by `tests/test_sync.py`; see [ADR 0001](adr/0001-symlink-root-tooling-to-payload.md).

## Excluded Directories

Only `templates/` is copied to generated projects. Everything outside it —
`examples/`, `tests/`, `docs/`, `scripts/`, `tasks/`, `copier.yaml` itself — is
template tooling and never lands in generated projects.

Within `templates/`, `licenses/` partials are excluded from copy via `_exclude`
(they are only used through `{% include %}` in `LICENSE.jinja`).

## Templating Conventions

### Variable Interpolation

Use double-brace syntax for Jinja2 variables:

```jinja
Project: {{ project_name }}
Author: {{ author_name }}
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
`LICENSE` and `.github/`. See `tests/test_conditional_sections.py` and
`tests/test_exclusions.py` for expected behavior, and the official Copier docs
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
| `test_sync.py` | Root symlinks, workflow byte copies, tool pins and `TASK_CONTRACT` against a rendered `mise.toml` |
| `test_agent_sync.py` | `.agents/` roster and the verbatim payload list stay in sync with the tree |
| `test_copier_settings.py` | Only real Copier settings appear as `_` keys in `copier.yaml` |
| `test_render_variants.py` | Computed render facts and the answers-file omission contract |
| `test_git_tasks.py` | `tasks/lifecycle.py` commits, `git init` and verification, against real Git |
| `test_update.py` | `copier update` of a project generated from the git-backed template repo |
| `test_core_structure.py`, `test_exclusions.py`, `test_conditional_sections.py` | Rendered structure, excluded paths and conditional sections |
| `test_python_versions.py`, `test_python_version_render.py`, `test_update_python_versions_script.py` | `python_version` question, its rendered pins, and the marker-block script |

### Test Fixtures

The render pipeline lives in `tests/_projects.py`, the one harness module test
files import from. It provides `VARIANTS`, `TASK_VARIANTS`, `ProjectRegistry`,
the template snapshot, and the shared loaders (`load_toml`, `copier_config`,
`pyproject`, `mise_toml`, `mise_tools`, `git()`). `tests/conftest.py` hosts only
fixtures (`template_source`, `projects`, `git_template_repo`).

- **Session-scoped `projects` registry**: `projects.render("<variant>")` renders each variant once per session, into pytest's `tmp_path_factory`
- **Task variants**: `TASK_VARIANTS` render with `copier.yaml` `_tasks` (a full `uv sync` each); all others render with `skip_tasks=True`
- **Read-only operations**: All tests are non-mutating to enable fixture reuse

## Variable Types

Variables are defined in `copier.yaml` with type hints:

- **String**: Simple text values
- **Boolean**: Yes/No choices
- **Choice**: Dropdown selection from predefined options
- **Integer**: Numeric values
- **Float**: Decimal values

## Answer Files

### `.copier-answers.yml`

Auto-maintained file created in generated projects. Used for:
- Tracking user responses
- Enabling future template updates via `copier update`
- Never manually edited

### Sample Configuration

`examples/config-basic.yml` provides:
- Example variable values
- Used with `copier copy --data-file` for non-interactive generation
- Excluded from generated projects

## Best Practices

1. **Always use relative paths** in template files
2. **Keep templates DRY**: Use Jinja2 includes for shared content
3. **Test conditionals thoroughly**: Edge cases matter
4. **Document variables**: Include helpful descriptions in `copier.yaml`
5. **Version templates**: Use Git tags for reproducible generations
6. **Commit before testing**: Copier uses Git to detect files
7. **Keep exclusions updated**: Remove deprecated files from templates

## Common Tasks

### Add a New Template Variable

1. Add question in `copier.yaml`:
   ```yaml
   my_variable:
     type: str
     help: "Description of this variable"
   ```

   Questions are top-level keys in `copier.yaml`; there is no `_questions` block.

2. Use in template files:
   ```jinja
   {{ my_variable }}
   ```

3. Add test case in `tests/`


### Update Generated Projects

Users can sync with template changes:
```bash
copier update --answers-file .copier-answers.yml
```

## References

- [Copier Documentation](https://copier.readthedocs.io/en/stable/)
- [Jinja2 Template Documentation](https://jinja.palletsprojects.com/)
- [Python Packaging Guide](https://packaging.python.org/)
