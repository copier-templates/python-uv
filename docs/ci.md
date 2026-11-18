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
  E --> F["📋 check:version-tag + lint + format:check + test:unit"]:::summary
```

## Workflow Summary

Triggers on push/PR to `main` plus `workflow_dispatch`; single Ubuntu job runs `mise run ci`.

- **Pinned toolchain**: `mise.toml` via `jdx/mise-action`, the same gate `AGENTS.md` requires locally.
- **Bash skips inline**: multiline shell steps open with `#!/usr/bin/env bash` and `set -euo pipefail`, and guard with `[[ -d ]]`; no separate bash version-floor task.
- **Single job, no matrix**: rendering is platform-independent.
- **No prek in CI**: hooks run locally (`mise run hooks:run`); CI uses check-only `lint` and `format:check`.
