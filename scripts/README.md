# Local workflow testing

Run GitHub Actions workflows on your machine before pushing: lint them with
`actionlint`, then execute the real job in an Ubuntu container via `act`. The
harness is a stdlib-only Python module (`scripts/maintainer/workflow_test.py`);
`scripts/maintainer/test-workflow.sh` is just a thin `exec` adapter.

Cutting a release is separate: `scripts/release.sh` (see `mise run release`
and `docs/development.md`) bumps `pyproject.toml`, regenerates
`CHANGELOG.md`, amends, and tags. Version math lives in the shipped
`templates/scripts/release_version.py` module and shared logging in
`templates/scripts/lib/release-common.sh`; both release scripts source those
payload files, and the root `scripts/` entries are symlinks into `templates/`.

`scripts/maintainer/release/` holds the CI release automation (root-only,
never shipped to generated projects): `resolve-version.sh` maps a PR's
`release:*` label to a bump kind, `cleanup-tag.sh` deletes orphan tags of
unmerged PRs. Both are plain CLIs with `--help`; the release workflow wires
them together.

```bash
./scripts/maintainer/test-workflow.sh prek
./scripts/maintainer/test-workflow.sh --list
```

## Layout

`scripts/` splits into two tiers:

- **Payload adapters** at the top level: `release.sh`, `check-version-tag.sh`,
  `release_version.py` and `lib/release-common.sh` are relative symlinks into
  `templates/scripts/`, so the shipped Payload is the single source of truth.
  Only `README.md` and `maintainer/` sit beside them.
- **Root-only tooling** under `scripts/maintainer/`: local workflow testing
  (`test-workflow.sh` adapter, `workflow_test.py` harness, `workflows/` JSON
  profiles and YAML snippets), CI release automation (`release/`) and
  `update_python_versions.py`. `lib/common.sh` holds the logging/die/need_cmd
  preamble shared by the release CLIs. None of it renders into generated
  projects.

Generated projects receive the Payload copies at `scripts/` and never see
`scripts/maintainer/`.

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `docker` CLI + daemon | containers for `act` | `brew install docker` + `colima start` |
| `act` | runs workflows locally | `mise install` |
| `actionlint` | static workflow lint (fast fail gate) | `mise install` |
| `python3` (3.9+) | runs the stdlib harness | preinstalled on macOS |

The script finds a working `docker` on its own (including the Homebrew one when
a version-manager shim shadows it) and starts `colima` automatically if the
daemon is down. Missing tools abort with an install hint.

> Tested on macOS (Apple Silicon) with Docker via `colima`. Linux with a
> native Docker daemon should work the same way; Windows is untested.

## Usage

```bash
scripts/maintainer/test-workflow.sh <name> [--event EVENT] [--job JOB] [--image IMAGE] [--amd64]
scripts/maintainer/test-workflow.sh --list
scripts/maintainer/test-workflow.sh --help
```

- `<name>` selects `scripts/maintainer/workflows/<name>.json`, which pins the
  workflow file, trigger event, job, and container image. `--event`, `--job`,
  `--image` override the profile for one-off runs without editing files.
- `--amd64` forces Intel emulation on Apple Silicon (slower; default runs
  native arm64, which is fine for Python/shell jobs).
- `ACT_EXTRA_ARGS` appends extra `act` flags (word-split, so keep it to simple
  flags without spaces), after the profile and `--amd64` arguments.
- Exit code is `0` only when `act` exits `0` and its log reports
  `Job succeeded`; a failed or unmarked run exits nonzero.

What a run does:

1. Lints the workflow file with `actionlint` (fails fast, no containers needed).
2. Copies top-level `.github/workflows/*.yml` to a temp dir and runs `act`
   against the copy, so local-only patches can never leak into the repo (there
   is even a safety check that aborts if `ACT-LOCAL` markers appear in the real
   file).
3. Streams container output live, saves the full log to a temp file (path is
   printed), then prints a per-step summary.

## Adding a new workflow

Copy the prek profile and adjust the JSON data:

```bash
cp scripts/maintainer/workflows/prek.json scripts/maintainer/workflows/my-job.json
```

```json
{
  "workflow_file": ".github/workflows/my-job.yml",
  "event": "pull_request",
  "job": "build",
  "image": "catthehacker/ubuntu:act-24.04",
  "needs_git_shim": false,
  "shim_snippet": null,
  "extra_args": []
}
```

- `workflow_file` (required, string) is the repo-relative workflow path.
- `event` (required, string) must be a trigger in the workflow file.
- `job` (required, string) selects one job; use `""` to run the whole event.
- `image` (required, string) is the container for `ubuntu-latest` jobs.
- `needs_git_shim` (required, boolean) enables the git shim.
- `shim_snippet` (required, string or `null`) names a YAML snippet beside the
  profile; `null` when `needs_git_shim` is `false`.
- `extra_args` (optional, list of strings, default `[]`) adds raw `act` flags,
  e.g. `["--matrix", "os:ubuntu-latest"]`.

Then `./scripts/maintainer/test-workflow.sh my-job`. No runner changes needed.
`workflow_test.py` owns profile loading and the run; the JSON files are data
only.

### If your job needs git inside the container

`act`'s fake checkout copies files **without** the `.git` directory, and the
container runs as root (git "dubious ownership" refusal). Jobs that shell out
to `git` need the same shim the prek profile uses:

```json
{
  "needs_git_shim": true,
  "shim_snippet": "prek-shim.yml"
}
```

`shim_snippet` names a YAML step fragment beside the profile. The harness
injects it as the first step of the tested job **in the temp copy only** and
deletes the temp dir afterwards. Write your own snippet file if your job needs
different setup; keep the `[act-local]` prefix so such steps are recognizable.

## Known local-only differences

- The final `git push` cannot succeed locally (dummy token, no remote). Validate
  everything up to it here; the push itself is covered by `workflow_dispatch`
  runs in CI.
- `actions/cache` works under `act` (local cache backend), so repeat runs are fast.
- The `@v4`/`@v5` action pins are resolved from the network on first use and
  then cached under `~/.cache/act`.

## Python version choices: `update_python_versions.py`

`scripts/maintainer/update_python_versions.py` refreshes the `python_version.choices`
mapping in `copier.yaml` from <https://endoflife.date/api/python.json>. It keeps
released CPython 3.x cycles at or above 3.12 (cycles without a `latest` release
are skipped) and writes them newest first.

The choices live between the marker comments
`# python-version-choices: begin (managed by scripts/maintainer/update_python_versions.py, do not edit)`
and `# python-version-choices: end` in `copier.yaml`. The script rewrites only
that block. Never hand-edit lines between the markers: the next run overwrites
them. If a marker is missing or duplicated, the script exits non-zero and leaves
the file untouched.

The script also refuses to write (non-zero exit, file untouched) when the
refresh would drop the question's current `default` version from the choices,
for example after 3.12 reaches end of life. It reads the first `default:` line
after the end marker, which must be a quoted `X.Y` version; if that line is
missing or malformed, the script fails the same way. Change the default in
`copier.yaml` first, then rerun the script.

```bash
mise run update:python-versions
```

The script is stdlib-only (no new dependencies) and makes one HTTPS request with
a 30-second timeout. It is repo-maintenance tooling: it never ships to generated
projects (see the Copier note below).

## Copier note

The `scripts/maintainer/` tooling is template-developer tooling: it lives outside
`templates/` (`_subdirectory: templates` in `copier.yaml`) and is covered by
`tests/test_exclusions.py`, so it never lands in generated projects.
