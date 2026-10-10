# CI Flow (GitHub Actions)

This document shows the CI flow used in `.github/workflows/test.yml`.

```mermaid
flowchart TD
  classDef trigger fill:#1F2937,stroke:#111827,color:#FFFFFF,font-weight:bold,stroke-width:3px;
  classDef checkout fill:#0369A1,stroke:#024873,color:#FFFFFF,stroke-width:2px;
  classDef setup fill:#10B981,stroke:#059669,color:#FFFFFF,stroke-width:2px;
  classDef cache fill:#F59E0B,stroke:#D97706,color:#FFFFFF,stroke-width:2px;
  classDef test fill:#8B5CF6,stroke:#7C3AED,color:#FFFFFF,stroke-width:2px;
  classDef summary fill:#6B7280,stroke:#4B5563,color:#FFFFFF,stroke-width:2px;

  A["🚀 GitHub Actions Trigger"]:::trigger
  A -->|push, pull_request<br/>or workflow_dispatch| B["📥 Checkout Repository"]:::checkout
  B --> C["⚙️ Install pinned toolchain (mise)"]:::setup
  C --> D["💾 Cache UV Downloads"]:::cache
  D --> E["🧪 Run CI checks (mise run ci)"]:::test
  E --> F["📋 lint + unit + format"]:::summary
```

## Workflow Summary

The CI pipeline triggers on every push and pull request to `main` (plus manual
`workflow_dispatch` runs) and validates the template in a single Ubuntu job.
Key features:

- **Pinned toolchain**: Python, `uv`, and `shellcheck` versions come from
  `mise.toml` via `jdx/mise-action`, so CI uses exactly the toolchain pinned
  for local development (`mise run ci` is the same gate as `AGENTS.md` requires
  before pushing).
- **Single job, no matrix**: one OS, one Python (the mise pin) — the old
  10-job grid (2 OS × 5 Pythons) multiplied Copier-render cost for no signal,
  since rendering is platform-independent Python and the interpreter is pinned.
- **Dependency caching**: uv download caches are cached for faster runs.
- **Test execution**: `mise run ci` runs `lint` + `unit` + `format`, where
  `unit` is the Copier template validation suite in `my_tests/`.

## Key Stages

| Stage | Purpose |
|-------|---------|
| 🚀 Trigger | Initiates workflow on code changes |
| 📥 Checkout | Retrieves repository code |
| ⚙️ Setup | Installs pinned toolchain via mise |
| 💾 Cache | Optimizes dependency installation |
| 🧪 Tests | Executes `mise run ci` (lint + unit + format) |
