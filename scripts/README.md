# Local workflow testing

Run GitHub Actions workflows on your machine before pushing: lint them with
`actionlint`, then execute the real job in an Ubuntu container via `act`.

```bash
./scripts/test-workflow.sh pre-commit
./scripts/test-workflow.sh --list
```

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| `docker` CLI + daemon | containers for `act` | `brew install docker` + `colima start` |
| `act` | runs workflows locally | `brew install act` |
| `actionlint` | static workflow lint (fast fail gate) | `brew install actionlint` |
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

Copy the pre-commit profile and adjust four variables:

```bash
cp scripts/workflows/pre-commit.sh scripts/workflows/my-job.sh
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
to `git` need the same shim the pre-commit profile uses:

```bash
WORKFLOW_NEEDS_GIT_SHIM="yes"
WORKFLOW_SHIM_SNIPPET="$SCRIPTS_DIR/workflows/pre-commit-shim.yml"
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

## Copier note

This `scripts/` folder is template-developer tooling: it is listed in
`copier.yaml` `_exclude` and covered by `my_tests/test_exclusions.py`, so it
never lands in generated projects.
