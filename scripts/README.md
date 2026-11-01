# Local workflow testing

Run GitHub Actions workflows on your machine before pushing: lint them with
`actionlint`, then execute the real job in an Ubuntu container via `act`.

Cutting a release is separate: `scripts/release.sh` (see `mise run release`
and `docs/development.md`) bumps `pyproject.toml`, regenerates
`CHANGELOG.md`, commits, and tags.

```bash
./scripts/test-workflow.sh prek
./scripts/test-workflow.sh --list
```

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `docker` CLI + daemon | containers for `act` | `brew install docker` + `colima start` |
| `act` | runs workflows locally | `mise install` |
| `actionlint` | static workflow lint (fast fail gate) | `mise install` |
| `python3` | scratch-copy patching | preinstalled on macOS |

The script finds a working `docker` on its own (including the Homebrew one when
a version-manager shim shadows it) and starts `colima` automatically if the
daemon is down. Missing tools abort with an install hint.

> Tested on macOS (Apple Silicon) with Docker via `colima`. Linux with a
> native Docker daemon should work the same way; Windows is untested.

## Usage

```bash
scripts/test-workflow.sh <name> [--event EVENT] [--job JOB] [--image IMAGE] [--amd64]
scripts/test-workflow.sh --list
scripts/test-workflow.sh --help
```

- `<name>` selects `scripts/workflows/<name>.sh`, which pins the workflow file,
  trigger event, job, and container image. `--event`, `--job`, `--image`
  override the profile for one-off runs without editing files.
- `--amd64` forces Intel emulation on Apple Silicon (slower; default runs
  native arm64, which is fine for Python/shell jobs).
- Exit code mirrors the container run: `0` = job succeeded.

What a run does:

1. Lints the workflow file with `actionlint` (fails fast, no containers needed).
2. Copies `.github/workflows/*.yml` to a temp dir and runs `act` against the
   copy, so local-only patches can never leak into the repo (there is even a
   safety check that aborts if `ACT-LOCAL` markers appear in the real file).
3. Streams container output live, saves the full log to a temp file (path is
   printed), then prints a per-step summary.

## Adding a new workflow

Copy the prek profile and adjust four variables:

```bash
cp scripts/workflows/prek.sh scripts/workflows/my-job.sh
```

```bash
WORKFLOW_FILE=".github/workflows/my-job.yml"  # required
WORKFLOW_EVENT="pull_request"                  # required: any trigger in the file
WORKFLOW_JOB="build"                           # optional: empty runs the whole event
ACT_IMAGE="catthehacker/ubuntu:act-24.04"      # optional container image
# ACT_EXTRA_ARGS="--matrix os:ubuntu-latest"   # optional raw `act` flags
```

Then `./scripts/test-workflow.sh my-job`. No runner changes needed.

### If your job needs git inside the container

`act`'s fake checkout copies files **without** the `.git` directory, and the
container runs as root (git "dubious ownership" refusal). Jobs that shell out
to `git` need the same shim the prek profile uses:

```bash
WORKFLOW_NEEDS_GIT_SHIM="yes"
WORKFLOW_SHIM_SNIPPET="$SCRIPTS_DIR/workflows/prek-shim.yml"
```

The snippet (a plain YAML step fragment) is injected as the first step of the
tested job **in the temp copy only**, via `scripts/lib/inject_step.py`, and the
temp dir is deleted afterwards. Write your own snippet file if your job needs
different setup; keep the `[act-local]` prefix so such steps are recognizable.

## Known local-only differences

- The final `git push` cannot succeed locally (dummy token, no remote). Validate
  everything up to it here; the push itself is covered by `workflow_dispatch`
  runs in CI.
- `actions/cache` works under `act` (local cache backend), so repeat runs are fast.
- The `@v4`/`@v5` action pins are resolved from the network on first use and
  then cached under `~/.cache/act`.

## Python version choices: `update_python_versions.py`

`scripts/update_python_versions.py` refreshes the `python_version.choices`
mapping in `copier.yaml` from <https://endoflife.date/api/python.json>. It keeps
released CPython 3.x cycles at or above 3.11 (cycles without a `latest` release
are skipped) and writes them newest first.

The choices live between the marker comments
`# python-version-choices: begin (managed by scripts/update_python_versions.py, do not edit)`
and `# python-version-choices: end` in `copier.yaml`. The script rewrites only
that block. Never hand-edit lines between the markers: the next run overwrites
them. If a marker is missing or duplicated, the script exits non-zero and leaves
the file untouched.

The script also refuses to write (non-zero exit, file untouched) when the
refresh would drop the question's current `default` version from the choices,
for example after 3.11 reaches end of life. It reads the first `default:` line
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

This `scripts/` folder is template-developer tooling: it lives outside
`templates/` (`_subdirectory: templates` in `copier.yaml`) and is covered by
`tests/test_exclusions.py`, so it never lands in generated projects.
