"""Shared test harness: template snapshot, variant rendering, rendered-config reads and git state."""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from copier import run_copy

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]

# Single source of truth for the mise/shared-tooling contract (see tests/test_sync.py).
SHARED_REF = "0.2.1"
SHARED_CATEGORIES = ("core", "toml", "py", "cicd/github")
LOCAL_TASKS = frozenset({"bootstrap", "release"})

GIT = shutil.which("git") or "git"

GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "Copier Tests",
    "GIT_AUTHOR_EMAIL": "copier-tests@test.com",
    "GIT_COMMITTER_NAME": "Copier Tests",
    "GIT_COMMITTER_EMAIL": "copier-tests@test.com",
}

GIT_ISOLATION = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
GIT_ENV = GIT_IDENTITY | GIT_ISOLATION

PYTHON_VERSION_ANSWER_LINE = r"(?m)^python_version:\s*['\"]{version}['\"]\s*$"

UPDATE_MARKER = "<!-- template-update-marker-v1.0.1 -->"


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text())


@functools.lru_cache(maxsize=1)
def copier_config() -> dict[str, Any]:
    """Parse the root `copier.yaml` (Jinja lives inside quoted scalars, so it loads as YAML)."""
    return yaml.safe_load((TEMPLATE_ROOT / "copier.yaml").read_text())


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `cwd` with the fixture identity, failing the test on a non-zero exit code."""
    return subprocess.run(
        [GIT, *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=os.environ | GIT_ENV,
    )


class GitRepo:
    """A git repository under test: setup, commits, and read-only state queries."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def init(cls, path: Path, *, branch: str | None = None) -> GitRepo:
        path.mkdir(parents=True, exist_ok=True)
        args = ["init"]
        if branch is not None:
            args += ["-b", branch]
        git(path, *args)
        return cls(path)

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return git(self.path, *args)

    def commit_all(self, message: str, *, allow_empty: bool = False) -> None:
        self.run("add", "-A")
        extra = ["--allow-empty"] if allow_empty else []
        self.run("commit", *extra, "-m", message)

    def head(self) -> str:
        return self.run("rev-parse", "HEAD").stdout.strip()

    def subjects(self, rev: str = "HEAD") -> list[str]:
        return self.run("log", "--format=%s", rev).stdout.splitlines()

    def files(self, rev: str = "HEAD") -> set[str]:
        names = self.run("show", "-z", "--name-only", "--format=", rev).stdout
        return set(filter(None, names.split("\0")))

    def tracked(self, rev: str = "HEAD") -> set[str]:
        return set(filter(None, self.run("ls-tree", "-r", "--name-only", rev).stdout.splitlines()))

    def status(self) -> str:
        return self.run("status", "--porcelain").stdout

    def tags(self) -> list[str]:
        return self.run("tag").stdout.splitlines()

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags()

    def write(self, relpath: str, content: str) -> Path:
        destination = self.path / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)
        return destination


def snapshot_template_root(dest: Path, root: Path = TEMPLATE_ROOT) -> Path:
    """Copy the files git would commit under `root` (tracked + untracked non-ignored) into `dest`, preserving symlinks and modes."""
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
    """Build a git-backed template copy: `v1.0.0` is the working tree, `v1.0.1` appends `UPDATE_MARKER` to the README."""
    repo = GitRepo.init(snapshot_template_root(dest))
    readme = repo.path / "templates" / "README.md.jinja"
    existing = readme.read_text()
    marker_suffix = f"{UPDATE_MARKER}\n" if existing.endswith("\n") else f"\n{UPDATE_MARKER}\n"
    repo.commit_all("Template snapshot")
    repo.run("tag", "v1.0.0")
    with readme.open("a", encoding="utf-8") as handle:
        handle.write(marker_suffix)
    repo.commit_all("Document update marker")
    repo.run("tag", "v1.0.1")
    return repo.path


BASE_DATA: dict[str, object] = {
    "project_type": "package",
    "project_description": "Example description",
    "user_name": "Test User",
    "user_email": "test@test.com",
    "production_deps": ["httpx[http2]"],
    "github_integration": True,
}


def run_copy_from(
    source: Path,
    dst: Path,
    data: dict[str, object],
    vcs_ref: str | None = None,
    skip_tasks: bool = False,
) -> Path:
    """Render `source` into `dst`, optionally pinned to `vcs_ref`; `skip_tasks=True` renders files only."""
    # macOS may spell temp dirs `/var/...` while git reports `/private/var/...`, breaking Copier's update path math.
    dst = dst.resolve()
    extra: dict[str, Any] = {"vcs_ref": vcs_ref} if vcs_ref is not None else {}
    old_environ = {key: os.environ.get(key) for key in GIT_ENV}
    os.environ.update(GIT_ENV)
    try:
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
    finally:
        for key, value in old_environ.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return dst


@dataclass(frozen=True)
class Variant:
    """A named render: Copier answers plus whether the render runs the template's `_tasks`."""

    answers: Mapping[str, object]
    runs_tasks: bool = False


def _variant(*, runs_tasks: bool = False, **answers: object) -> Variant:
    return Variant(answers=BASE_DATA | answers, runs_tasks=runs_tasks)


# Rendered once per session with `projects.render("<variant>")`; only `basic` needs task outcomes.
# Three variants cover the matrix: package+tasks, app layout, and lib+license+hyphenated name.
VARIANTS: dict[str, Variant] = {
    "basic": _variant(runs_tasks=True, project_name="example_proj"),
    "app": _variant(project_name="console_app", project_type="app"),
    "lib-licensed": _variant(
        project_name="my-app",
        project_type="lib",
        python_version="3.13",
        production_deps=[],
        extra_dev_deps=["hypothesis>=6"],
        include_license=True,
        license_type="mit",
        github_integration=False,
    ),
}


@dataclass(frozen=True)
class RenderedProject:
    """A rendered project directory and the answers that produced it."""

    path: Path
    answers: Mapping[str, object]

    def answer(self, name: str) -> object:
        if name in self.answers:
            return self.answers[name]
        default = copier_config()[name]["default"]
        if isinstance(default, str) and "{{" in default:
            raise ValueError(
                f"{name} is a computed render fact, not an answer; read it from the rendered project instead"
            )
        return default

    @property
    def project_name(self) -> str:
        return str(self.answer("project_name"))

    @property
    def module_name(self) -> str:
        return self.project_name.replace("-", "_")

    def repo(self) -> GitRepo:
        return GitRepo(self.path)

    def read(self, relpath: str) -> str:
        return (self.path / relpath).read_text()

    def pyproject(self) -> dict[str, Any]:
        return load_toml(self.path / "pyproject.toml")

    def mise(self) -> dict[str, Any]:
        return load_toml(self.path / "mise.toml")

    def mise_tools(self) -> dict[str, str]:
        return self.mise()["tools"]


class ProjectRegistry:
    def __init__(self, source: Path, mktemp: Callable[[str], Path]) -> None:
        self._source = source
        self._mktemp = mktemp
        self._cache: dict[str, RenderedProject] = {}

    def render(self, variant: str) -> RenderedProject:
        if variant not in self._cache:
            spec = VARIANTS[variant]
            path = run_copy_from(
                self._source,
                self._mktemp(variant),
                dict(spec.answers),
                skip_tasks=not spec.runs_tasks,
            )
            self._cache[variant] = RenderedProject(path, spec.answers)
        return self._cache[variant]
