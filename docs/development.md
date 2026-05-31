# Development Guide

This guide covers local development setup and workflow for the Copier template project.

## Prerequisites

- Python 3.10 or newer
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

Run specific test files:
```bash
uv run pytest my_tests/test_core_structure.py
```

### Code Quality

Format and lint code:
```bash
mise run lint
```

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
- **pytest**: Testing framework
- **copier**: Project template tool
- **pre-commit**: Git hooks framework

## Troubleshooting

### UV cache issues

Clear and resync:
```bash
uv cache clean
mise run install
```
