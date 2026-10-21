<div align="center">

[![tests](https://github.com/patryk-gpl/copier-python-uv/actions/workflows/test.yml/badge.svg)](https://github.com/patryk-gpl/copier-python-uv/actions)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-enabled-blue)](https://docs.astral.sh/uv/)
[![ruff](https://img.shields.io/badge/ruff-enabled-black)](https://docs.astral.sh/ruff/)
[![copier](https://img.shields.io/badge/copier-template-orange)](https://copier.readthedocs.io/)
[![mise](https://img.shields.io/badge/mise-enabled-purple)](https://mise.jdx.dev/)
[![prek](https://raw.githubusercontent.com/j178/prek/main/docs/assets/badge.svg)](https://github.com/j178/prek)
[![License](https://img.shields.io/github/license/patryk-gpl/copier-python-uv)](LICENSE)

# 🎯 Python Project Template



This template provides a standardized Python project structure with sensible defaults, tailored to use in Python projects. It streamlines project setup and encourages best practices from the start.

</div>

---

## 📋 Prerequisites

The following tools must be installed:
- Python 3.10 or newer
- uv or pipx (if you want to install Copier in an isolated environment, accessible everywhere)
- copier

## 🚀 Usage

1. **Install Copier** (if not already):
   ```bash
   pipx install copier
   ```

   or

   ```bash
   uv tool install copier
   ```

2. **Generate files in your target repository (interactive):**
   ```bash
   copier copy /path/to/copier-template /path/to/your-repo
   ```
   Replace `/path/to/copier-template` with the path to this template, and `/path/to/your-repo` with your target repository.

   **Note:** If you're testing with unreleased template changes, use `--vcs-ref=HEAD`:
   ```bash
   copier copy --vcs-ref=HEAD /path/to/copier-template /path/to/your-repo
   ```

3. **Generate non-interactively using the provided sample data file:**
   A sample data file is provided at `examples/config-basic.yml`.
   ```bash
   copier copy --data-file examples/config-basic.yml /path/to/copier-template /path/to/your-repo
   ```
   You can duplicate and modify that file to create variants (e.g., `data-with-ruff.yml`).

   **Note:** This template uses conditional tasks (see [Tasks Behavior](#-tasks-behavior-with-different-copier-commands)), which require the `--trust` flag:
   ```bash
   copier copy --trust --data-file examples/config-basic.yml /path/to/copier-template /path/to/your-repo
   ```

4. **(Optional) Override specific values at the CLI:**
   You can still override one or more answers on the fly:
   ```bash
   copier copy --trust --data-file examples/config-basic.yml -d project_name=override_name /path/to/template /dest
   ```

5. **Review the generated files:**
   ```bash
   cd /path/to/your-repo
   git status
   ```

   The template runs `uv sync` after bootstrapping and commits the generated
   `uv.lock` in the initial Git commit.

### ⚠️ Tasks Behavior with Different Copier Commands

This template uses **templated `_exclude`** to manage optional features (LICENSE file, GitHub integration, `src` vs `main.py`, `py.typed`). Understanding their behavior is important for safe updates:

#### Render Process
Exclusions are evaluated during rendering, **before** tasks run. This means:
- Optional files are never created when excluded
- `uv sync` installs the project and generates or refreshes `uv.lock`
- Remaining `_tasks` (`uv sync`, `git init`, `mise trust`) run after rendering

#### Initial Project Generation (`copier copy`)
When you generate a new project with conditions set:
- ✅ `include_license=true` → LICENSE file is rendered
- ✅ `include_license=false` → `LICENSE` is excluded, never created
- ✅ `github_integration=true` → `.github/` workflow files are rendered
- ✅ `github_integration=false` → `.github/` is excluded, never created

#### Project Updates (`copier update`)
**Tasks are executed again** during updates. This is important:
- ✅ Safe with `--defaults` (keeps your previous answers as-is)
- ✅ Safe if you keep boolean settings unchanged
- ⚠️ **Dangerous if you change boolean settings** when you have customizations

#### Safe Update Commands

**Recommended - Keeps all previous answers:**
```bash
copier update --defaults --trust  
# Your github_integration and include_license settings remain unchanged
```

**Safe if no customizations in affected directories:**
```bash
copier update --trust --data github_integration=false
# OK if you haven't customized .github/ subdirectories
```

#### Dangerous Update Scenario ⚠️

```bash
# Initial generation WITH GitHub integration
copier copy --trust --vcs-ref=HEAD \
  --data project_name=myproject \
  --data github_integration=true \
  /template /myproject

# Later: You customize workflows in .github/workflows/

# Then: Update but accidentally change github_integration to false
copier update --trust --data github_integration=false
# Result: 🔴 excluded .github paths are removed, DELETING CUSTOM WORKFLOWS!
```

#### Safe Alternative for Disabling Features

If you need to disable GitHub integration after customizing `.github/`:

1. **Manually back up your customizations:**
   ```bash
   cp -r .github/workflows /tmp/my-workflows-backup
   cp LICENSE /tmp/my-license-backup  # if customized
   ```

2. **Run the update to disable features:**
   ```bash
   copier update --trust --data github_integration=false
   ```

3. **Restore your customizations:**
   ```bash
   cp -r /tmp/my-workflows-backup /path/to/.github/workflows
   ```

4. **Commit your changes:**
   ```bash
   git add .github/
   git commit -m "Restore custom workflows"
   ```

### 📦 Answers Files Explained
| File | Purpose |
|------|---------|
| `.copier-answers.yml` | Auto-maintained answers file for future updates (never edit manually). Now explicitly generated because the template includes `templates/{{ _copier_conf.answers_file }}.jinja`. |
| `examples/config-basic.yml` | Example data file passed with `--data-file` (excluded from rendered projects). |

### ⚙️ Internal Template Artifacts Not Copied
Only `templates/` is copied into generated projects (`_subdirectory: templates` in `copier.yaml`). Helper folders (`examples/`, `my_tests/`, `docs/`, `scripts/`) stay outside `templates/` so consumer projects stay clean. License partials under `templates/licenses/` are excluded from copy via `_exclude`.

To create a new variant template from existing data file configuration:
```bash
copier copy --data-file /path/to/config-basic.yml /path/to/template /dest
```
For advanced configuration (tasks, migrations, multiple templates) see the Copier docs sections: tasks, migrations, applying multiple templates.

## ✏️ Customization

You can edit the template files under `templates/` (`*.jinja` plus verbatim payload like `templates/prek.toml` and `templates/.github/workflows/*.yml`) to fit your team's standards. See [Copier documentation](https://copier.readthedocs.io/en/stable/) for advanced templating and options.

## 🧪 Testing the Template

This template includes comprehensive validation tests to ensure generated projects meet expected standards.

### ▶️ Running Tests

```bash
# Run all validation tests
mise run test
```

### ⚡ Test Performance

Tests use session-scoped fixtures for optimal performance:
- **Session-scoped fixtures:** Generated projects created once per test session, reused across all test modules
- **Module-scoped wrappers:** Clean test API with ~50% faster execution vs module scope alone
- **All tests read-only:** No mutations to generated projects ensures fixture reuse is safe

### 📁 Test Files

Test files are located in `my_tests/` folder.

| File | Purpose |
|------|---------|
| `test_core_structure.py` | Validates required files, directories, and project structure |
| `test_exclusions.py` | Ensures excluded files (`copier.yaml`, etc.) are not rendered |
| `test_conditional_sections.py` | Tests conditional rendering based on dependencies (e.g., Ruff) |

See `my_tests/conftest.py` for fixture definitions.

## 🔄 Prek Auto-Update

The [`prek.yml`](.github/workflows/prek.yml) workflow keeps hook
versions fresh without manual effort.

| Aspect | Detail |
|--------|--------|
| Schedule | Monthly, 06:00 UTC on the 1st (`0 6 1 * *`) |
| Manual run | Actions tab → *Scheduled Prek Auto-Update* → *Run workflow* (`workflow_dispatch`) |
| Runner | `ubuntu-latest` with latest stable Python 3 (`3.x` floating spec, resolved on every run) |
| Permissions | `contents: write` so `GITHUB_TOKEN` can push the bump commit |
| Caching | `~/.cache/prek` via one `actions/cache` step — hook envs are reused instead of rebuilt each run |
| Safety | `timeout-minutes: 10`; `concurrency` group serializes overlapping scheduled/manual runs |
| Commit | `chore(deps): auto-update prek hooks` via `github-actions[bot]`, only when the config actually changed |

How it works:

1. Checks out with `fetch-depth: 0` (avoids shallow-clone push issues).
2. Runs `prek update` on `prek.toml` — the single
   config, shipped verbatim into projects generated from this Copier template.
3. Detects changes via `git diff --quiet` (step output `changes`, not env vars);
   commits and pushes only when something changed — no empty commits.

### 🧪 Testing it locally

Local testing is automated — see [scripts/README.md](scripts/README.md).

## 📚 Local Documentation

Project-specific guides and workflows:

| Topic | Location |
|-------|----------|
| CI/CD Pipeline | [docs/ci.md](docs/ci.md) |
| Development Setup | [docs/development.md](docs/development.md) |
| Template Architecture | [docs/architecture.md](docs/architecture.md) |

## 🔗 External References

For framework and tool documentation:

### Python packaging
- Overview of [Python Packaging](https://packaging.python.org/en/latest/overview/)
- Python classifiers: [PyPI Classifiers](https://pypi.org/classifiers/)
- Python Packaging: [PEP 621 - pyproject.toml](https://peps.python.org/pep-0621/)
- System Package Data Exchange: [SPDX License List](https://spdx.org/licenses/)
- Writing your [pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#writing-pyproject-toml)

### Tools
- Copier Framework: [Copier Documentation](https://copier.readthedocs.io/en/stable/)
- Git Hooks: [prek Documentation](https://prek.j178.dev/)
- Ruff Formatter: [Ruff Documentation](https://docs.astral.sh/ruff/)
- UV Package Manager: [UV Documentation](https://docs.astral.sh/uv/)
