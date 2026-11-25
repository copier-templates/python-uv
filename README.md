<div align="center">

[![tests](https://github.com/patryk-gpl/copier-python-uv/actions/workflows/test.yml/badge.svg)](https://github.com/patryk-gpl/copier-python-uv/actions)
[![python](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-enabled-blue)](https://docs.astral.sh/uv/)
[![ruff](https://img.shields.io/badge/ruff-enabled-black)](https://docs.astral.sh/ruff/)
[![copier](https://img.shields.io/badge/copier-template-orange)](https://copier.readthedocs.io/)
[![mise](https://img.shields.io/badge/mise-enabled-purple)](https://mise.jdx.dev/)
[![prek](https://raw.githubusercontent.com/j178/prek/main/docs/assets/badge.svg)](https://github.com/j178/prek)
[![License](https://img.shields.io/github/license/patryk-gpl/copier-python-uv)](LICENSE)

# 🎯 Python Project Template



This template provides a standardized Python project structure with sensible defaults for project setup.

</div>

---

## 📋 Prerequisites

The following tools must be installed:
- Python 3.12 or newer
- uv or pipx (if you want to install Copier in an isolated environment, accessible everywhere)
- copier
- mise 2026.11.10 or newer (the shared task includes need `experimental = true`)

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
   Replace `/path/to/copier-template` with the path to this template, and `/path/to/your-repo` with your target repository. The template asks which Python version to target (`python_version`, default `3.12`): the answer pins `mise.toml`, `requires-python`, and Ruff's `target-version`. Testing unreleased template changes? Add `--vcs-ref=HEAD`.

3. **Generate non-interactively** with the sample data file (`examples/config-basic.yml`; duplicate and modify it for variants like `data-with-license.yml`):
   ```bash
   copier copy --trust --data-file examples/config-basic.yml /path/to/copier-template /path/to/your-repo
   ```
   `--trust` is required (the template runs conditional tasks — see [Tasks Behavior](#-tasks-behavior-with-different-copier-commands)); override single answers with `-d key=value` (e.g., `-d project_name=override_name`).

4. **Review the generated files:**
   ```bash
   cd /path/to/your-repo
   git status
   ```

   The template runs `uv sync` after rendering and commits the result,
   including `uv.lock`: an `Init commit` in a new directory, or
   `chore: scaffold from copier template` inside an existing repository.

### ⚠️ Tasks Behavior with Different Copier Commands

Safe rule: `copier update --defaults --trust` keeps your answers; changing a boolean (`include_license`, `github_integration`) on update can delete excluded paths (`.github/`, `LICENSE`) and any customizations inside them — back them up first.

### 📦 Answers Files Explained
| File | Purpose |
|------|---------|
| `.copier-answers.yml` | Auto-maintained answers file for future updates (never edit manually; generated from `templates/{{ _copier_conf.answers_file }}.jinja`). |
| `examples/config-basic.yml` | Example data file passed with `--data-file` (excluded from rendered projects). |

### ⚙️ Internal Template Artifacts Not Copied
Only `templates/` ships (`_subdirectory: templates` in `copier.yaml`). Root `scripts/*.py` files are symlinks into the `templates/scripts/` payload so they ship too — see [Excluded Directories](docs/architecture.md#excluded-directories).

## ✏️ Customization

You can edit the template files under `templates/` (`*.jinja` plus verbatim payload like `templates/prek.toml` and `templates/.github/workflows/*.yml`) to fit your team's standards. See [Copier documentation](https://copier.readthedocs.io/en/stable/) for advanced templating and options.

## 🧪 Testing the Template

```bash
mise run test
mise exec -- uv run pytest tests/test_rendered_project.py
```

See [docs/architecture.md](docs/architecture.md#testing) for what each test module covers.

## 🧹 TOML Formatting (taplo)

All `*.toml` files are formatted with [taplo](https://taplo.tamasfe.com/); the `taplo-fmt` prek hook autofixes on every commit. Check manually with `mise run prek:run -- --show-diff-on-failure`: the extra args append to the shared `prek run --all-files`, and the flag prints the failing diff.
`taplo.toml` sets `column_width = 1`, which expands every array to one item per line (empty arrays stay `[\n]`); the payload emits taplo-clean output so rendered projects pass unchanged.

## 🔄 Prek Auto-Update

The [`prek.yml`](.github/workflows/prek.yml) workflow runs monthly (`0 6 1 * *`) and on manual `workflow_dispatch`, running `prek update` on `prek.toml` with `contents: write` and a `~/.cache/prek` cache step.
It commits `chore(deps): auto-update prek hooks` via `github-actions[bot]` only when `prek.toml` changed (`git diff --quiet` gate, `timeout-minutes: 10`, `concurrency: prek-update`).
The shared `shared-dev-tooling` repo is held to the refs managed by the task includes: `[update.repos]` lists every distinct `?ref=`, and the hooks `rev` follows the newest one, so `prek update` never moves it alone. Move every pin with `uv run python scripts/sync_shared_refs.py --to X.Y.Z`, or edit the root `mise.toml` to roll categories out separately and run the script without `--to`; then clear the remote-task cache with `mise run mise:cache:clear` (see [docs/development.md](docs/development.md#tools-used)).

## 📚 Local Documentation

Project-specific guides and workflows:

| Topic | Location |
|-------|----------|
| CI/CD Pipeline | [docs/ci.md](docs/ci.md) |
| Development Setup | [docs/development.md](docs/development.md) |
| Template Architecture | [docs/architecture.md](docs/architecture.md) |

## 🔗 External References

- Copier Framework: [Copier Documentation](https://copier.readthedocs.io/en/stable/)
- UV Package Manager: [UV Documentation](https://docs.astral.sh/uv/)
- Git Hooks: [prek Documentation](https://prek.j178.dev/)
