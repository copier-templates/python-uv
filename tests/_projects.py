"""Shared test harness: template snapshot, git and Copier helpers, variant answers, config loaders.

Test modules import from here, never from `conftest.py`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import tomllib
import yaml
from copier import run_copy
from plumbum import local

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

# Absolute git path (avoids partial-path lint in subprocess calls).
GIT = shutil.which("git") or "git"

# Identity for every fixture commit, so no global git config is needed.
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Copier Tests",
    "GIT_AUTHOR_EMAIL": "copier-tests@example.com",
    "GIT_COMMITTER_NAME": "Copier Tests",
    "GIT_COMMITTER_EMAIL": "copier-tests@example.com",
}

# Regex template (`{version}` is a regex) matching the `python_version` line in `.copier-answers.yml`.
PYTHON_VERSION_ANSWER_LINE = r"(?m)^python_version:\s*['\"]{version}['\"]\s*$"

# Line appended to the README template in the `v1.0.1` tag of the git-backed fixture repo.
UPDATE_MARKER = "<!-- template-update-marker-v1.0.1 -->"


def load_toml(path: Path) -> dict[str, Any]:
    """Parse the TOML file at `path`."""
    return tomllib.loads(path.read_text())


def copier_config() -> dict[str, Any]:
    """Parse the root `copier.yaml` (Jinja lives inside quoted scalars, so it loads as YAML)."""
    return yaml.safe_load((TEMPLATE_ROOT / "copier.yaml").read_text())


def pyproject(project: Path) -> dict[str, Any]:
    """Parsed `pyproject.toml` of a rendered project."""
    return load_toml(project / "pyproject.toml")


def mise_toml(project: Path) -> dict[str, Any]:
    """Parsed `mise.toml` of a rendered project."""
    return load_toml(project / "mise.toml")


def mise_tools(project: Path) -> dict[str, str]:
    """The `[tools]` table of a rendered project's `mise.toml`."""
    return mise_toml(project)["tools"]


def refs(task: dict[str, Any]) -> list[str]:
    """Subtask names `task` aggregates via `depends` or ordered `run` steps."""
    if "depends" in task:
        return list(task["depends"])
    run = task.get("run")
    return [step["task"] for step in run if isinstance(step, dict)] if isinstance(run, list) else []


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd` with the fixture identity, failing the test on a non-zero exit code."""
    return subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ | GIT_IDENTITY,
    )


def snapshot_template_root(dest: Path, root: Path = TEMPLATE_ROOT) -> Path:
    """Copy the files git would commit under `root` into the non-git directory `dest`.

    Tracked files and untracked non-ignored files are included, so uncommitted
    template edits still render, while git-ignored leftovers never leak in.
    Symlinks are copied as symlinks and file modes are preserved.
    """
    listing = subprocess.run(
        [GIT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    dest.mkdir(parents=True, exist_ok=True)
    for raw_name in listing.split(b"\0"):
        if not raw_name:
            continue
        name = Path(os.fsdecode(raw_name))
        source = root / name
        # Tracked-but-deleted paths are still listed by `ls-files --cached`.
        if not os.path.lexists(source):
            continue
        destination = dest / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)
    return dest


def make_git_template_repo(dest: Path) -> Path:
    """Build a git-backed copy of this template in `dest` with two release tags.

    `v1.0.0` is the current working tree; `v1.0.1` appends `UPDATE_MARKER` to
    `templates/README.md.jinja`. Copier `update` tests copy from `v1.0.0` and
    expect the `v1.0.1` change to land in the generated project.
    """
    repo = snapshot_template_root(dest)
    readme = repo / "templates" / "README.md.jinja"
    existing = readme.read_text()
    marker_suffix = f"{UPDATE_MARKER}\n" if existing.endswith("\n") else f"\n{UPDATE_MARKER}\n"
    git(repo, "init")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Template snapshot")
    git(repo, "tag", "v1.0.0")
    with readme.open("a", encoding="utf-8") as handle:
        handle.write(marker_suffix)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "Document update marker")
    git(repo, "tag", "v1.0.1")
    return repo


BASE_DATA: dict[str, object] = {
    "project_type": "package",
    "project_description": "Example description",
    "author_name": "Test User",
    "author_email": "test@test.com",
    "production_deps": ["httpx[http2]"],
    "dev_deps": ["pytest", "pytest-cov"],
    "github_integration": True,
}


def run_copy_from(
    source: Path,
    dst: Path,
    data: dict[str, object],
    vcs_ref: str | None = None,
    skip_tasks: bool = False,
) -> Path:
    """Render `source` with Copier into `dst`, optionally pinned to `vcs_ref`; return the resolved `dst`.

    `skip_tasks=True` skips the `copier.yaml` `_tasks` (python install, `uv sync`,
    git lifecycle, `mise run install`/`ci`): the render holds the files only.
    """
    # Resolve the destination: on macOS temp dirs may be spelled `/var/...` while
    # git reports `/private/var/...`, which breaks Copier's `update` path math.
    dst = dst.resolve()
    extra: dict[str, object] = {"vcs_ref": vcs_ref} if vcs_ref is not None else {}
    with local.env(**GIT_IDENTITY):
        run_copy(
            str(source),
            str(dst),
            data=data,
            defaults=True,
            overwrite=True,
            unsafe=True,
            skip_tasks=skip_tasks,
            **extra,
        )
    return dst


# Per-variant answers layered over BASE_DATA, rendered with `projects.render("<variant>")`.
VARIANTS: dict[str, dict[str, object]] = {
    "basic": {"project_name": "example_proj"},
    "ruff": {"project_name": "ruff_proj", "production_deps": [], "dev_deps": ["pytest", "pytest-cov", "ruff"]},
    # Ruff without pytest: pytest-gated sections must not render.
    "ruff-only": {"project_name": "ruff_only_proj", "production_deps": [], "dev_deps": ["ruff"]},
    # Pytest without pytest-cov: coverage-gated sections must not render.
    "pytest-no-cov": {"project_name": "pytest_nocov_proj", "production_deps": [], "dev_deps": ["pytest"]},
    # Specifiers, extras and non-canonical spelling (PEP 503) must still enable the tooling.
    "pinned-dev-deps": {
        "project_name": "pinned_deps_proj",
        "production_deps": [],
        "dev_deps": ["Ruff>=0.6", "pytest[toml]>=8", "pytest_cov==6.0"],
    },
    "python313": {
        "project_name": "py313_proj",
        "python_version": "3.13",
        "production_deps": [],
        "dev_deps": ["pytest", "pytest-cov", "ruff"],
    },
    "license": {"project_name": "license_proj", "include_license": True, "license_type": "mit"},
    # Only variant combining a LICENSE with ruff, so `mise run ci` hooks run against a rendered LICENSE.
    "license-ruff": {
        "project_name": "license_ruff_proj",
        "include_license": True,
        "license_type": "mit",
        "production_deps": [],
        "dev_deps": ["pytest", "pytest-cov", "ruff"],
    },
    "github": {"project_name": "github_proj", "github_integration": True},
    "no-github": {"project_name": "no_github_proj", "github_integration": False},
    "hyphenated-package": {"project_name": "my-app", "project_type": "package"},
    "app": {"project_name": "console_app", "project_type": "app"},
    "lib": {"project_name": "example_lib", "project_type": "lib"},
}

# Variants rendered with `copier.yaml` `_tasks` (a full `uv sync` each): one proof per project type plus
# those whose tests assert task outcomes. All others render with `skip_tasks=True` (files only).
TASK_VARIANTS: frozenset[str] = frozenset(
    {"basic", "ruff", "pinned-dev-deps", "python313", "license-ruff", "app", "lib"}
)


class ProjectRegistry:
    """Session-scoped cache that renders each variant exactly once."""

    def __init__(self, source: Path, mktemp: Callable[[str], Path]) -> None:
        self._source = source
        self._mktemp = mktemp
        self._cache: dict[str, Path] = {}

    def render(self, variant: str) -> Path:
        """Return the rendered project for `variant` (a key of `VARIANTS`)."""
        if variant not in self._cache:
            self._cache[variant] = run_copy_from(
                self._source,
                self._mktemp(variant),
                BASE_DATA | VARIANTS[variant],
                skip_tasks=variant not in TASK_VARIANTS,
            )
        return self._cache[variant]
