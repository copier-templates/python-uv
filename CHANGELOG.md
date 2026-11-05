## [0.2.1] - 2026-11-05

### 🐛 Bug Fixes

- *(template)* Pin uv sync to selected Python and commit only rendered files
- *(lifecycle)* Commit only this run's paths and surface render errors
- *(lifecycle)* Read deleted paths NUL-delimited so odd filenames commit
## [0.2.0] - 2026-11-05

### 🚀 Features

- *(lifecycle)* Move post-copy git and mise steps into tasks/lifecycle.py
- *(template)* Migrate appomni ruff, ty and pytest settings, raise minimum Python to 3.12
- *(prek)* Hold back hook revs with 7-day update cooldown

### 🐛 Bug Fixes

- *(copier)* Reject project names that start with a digit
- *(scripts)* Disable OpenSSL strict X.509 checks in update_python_versions

### 🚜 Refactor

- Symlink root tooling to templates payload
- *(tests)* Consolidate harness helpers in _projects
- *(template)* Compute render facts once in copier.yaml
- *(scripts)* Dedupe python version marker handling
- *(template)* [**breaking**] Make pytest, pytest-cov and ruff always-on

### 📚 Documentation

- Document architecture, glossary and ADRs

### ⚡ Performance

- *(prek)* Run pre-commit hooks as builtins with priority tiers

### 🧪 Testing

- *(sync)* Guard root symlink and task-contract drift
## [0.1.0] - 2026-11-03

### 🚀 Features

- *(template)* Add Copier payload with mise/prek/workflows
- *(template)* Add copier config with python_version and conditional tasks
- Add AGENTS.md and agent definitions to portable .agents dir
- *(hooks)* Add gitleaks secret scanning

### 🐛 Bug Fixes

- *(template)* Sync prek ruff pin and guard root-template drift

### 🚜 Refactor

- *(tests)* Deepen mise task-graph contract assertions
- Derive tool pins from canonical sources and unify act image
- *(tests)* Collapse render fixtures into a project registry
- *(template)* Compute render facts once in copier.yaml

### 📚 Documentation

- Add architecture/ci/dev guides, example config, security policy and usage README
- Configure issue tracker, triage labels, and domain docs

### 🧪 Testing

- Add template validation suite with session fixtures

### ⚙️ Miscellaneous Tasks

- Add .gitignore and editorconfig
- Add mise and prek hooks
- Bootstrap git-cliff changelog config
- *(scripts)* Add local CI entrypoints and release tooling
