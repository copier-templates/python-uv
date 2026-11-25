# Development Guide

This guide covers local development setup and workflow for the Copier template project.

## Prerequisites

- Python 3.12 or newer
- Git
- uv (recommended) or pip/pipx

## Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/patryk-gpl/copier-python-uv.git
   cd copier-python-uv
   ```

2. **Install dependencies:**
   ```bash
   mise run install
   ```

3. **Run tests:**
   ```bash
   mise run test
   ```

## Development Workflow

### Running Tests Locally

Execute the full test suite:
```bash
mise run test
```

Run specific test files (through mise, never bare `pytest`):
```bash
mise exec -- uv run pytest tests/test_rendered_project.py
```

### Code Quality

Format and lint code:
```bash
mise run lint
```

### Cutting a Release

Preview first (`mise run changelog`), then run the interactive release flow:

```bash
mise run release
```

On a TTY with `gum` it prompts to confirm/edit the suggested version
(always the next patch above the latest tag; conventional commits only
shape the changelog) and to approve the amend. Pass `--version` when a
minor or major release is intended. Non-interactive (or without `gum`):

```bash
mise run release -- --version 0.4.0 --yes
# or: RELEASE_YES=1 RELEASE_VERSION=0.4.0 mise run release
```

The script bumps `[project] version` in `pyproject.toml`, re-locks
`uv.lock`, regenerates `CHANGELOG.md`, amends `HEAD`, and tags the release
version — it never pushes.
A repo with no tags yet (first release) defaults to the `pyproject.toml`
version. Afterwards: `git push --follow-tags`.

## Important Notes

### Git Repository Requirement for Testing

**Copier requires Git-tracked files when using `vcs_ref="HEAD"`**

When running tests locally:
- Ensure all template files are **committed to Git** before running tests
- Copier uses Git to determine which files to include
- Uncommitted files in the working directory are **ignored** by Copier

Before running tests:
```bash
git add .
git commit -m "WIP: template changes"
```

## Tools Used

- **uv**: Fast Python package installer and resolver
- **ruff**: Fast Python linter and formatter
- **ty**: Extremely fast Python type checker
- **pytest**: Testing framework
- **copier**: Project template tool
- **prek**: Git hooks framework
- **git-cliff**: Changelog generator (`mise run changelog` previews, `cliff.toml` configures)
- **shared-dev-tooling**: both `mise.toml` files import `tasks/core`, `tasks/toml`,
  `tasks/py` and (when GitHub integration is enabled) `tasks/cicd/github` over
  the network from
  [`copier-templates/shared-dev-tooling`](https://github.com/copier-templates/shared-dev-tooling),
  and `prek.toml` pins the same tag as the shared hooks `rev` (plus a matching
  `[update.repos]` `include_tags` so `prek update` never moves it alone).
  Bump with one command — never by hand:
  ```bash
  uv run python scripts/sync_shared_refs.py --to 0.2.2
  ```
  It moves the root `mise.toml` includes, `templates/mise.toml.jinja`,
  `templates/prek.toml` and `tests/_projects.py` together;
  `uv run python scripts/sync_shared_refs.py --check` verifies without writing,
  and the `sync-shared-refs` pre-commit hook runs that check on every commit
  (`tests/test_sync.py` still guards the lockstep in CI). After a bump run
  `mise run mise:cache:clear` so the next `mise` command refetches the
  cached remote tasks.

## Troubleshooting

### UV cache issues

Clear and resync:
```bash
uv cache clean
mise run install
```
