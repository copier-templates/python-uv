"""Python release and version-tag scripts: pure version helpers plus CLI safety against real repos."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
from _projects import GIT_ENV, TEMPLATE_ROOT, GitRepo, ProjectRegistry, load_toml

SCRIPTS: dict[str, Path] = {
    "release": TEMPLATE_ROOT / "templates" / "scripts" / "release.py",
    "check": TEMPLATE_ROOT / "templates" / "scripts" / "check_version_tag.py",
}


def _load(name: str) -> ModuleType:
    """Execute a payload script without importing it, so no `__pycache__` lands in `templates/`."""
    path = SCRIPTS[name]
    assert path.is_file(), f"missing Python script: {path}"
    module = ModuleType(f"{name}_under_test")
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    return module


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.1.0", (0, 1, 0)),
        ("1.2.3", (1, 2, 3)),
        ("0.10.0", (0, 10, 0)),
        ("1.2", None),
        ("v1.2.3", None),
        ("1.2.3.4", None),
        ("latest", None),
    ],
)
def test_parse_version_accepts_only_plain_xyz(raw: str, expected: tuple[int, int, int] | None):
    assert _load("release").parse_version(raw) == expected


@pytest.mark.parametrize(
    ("current", "last_tag", "remote_tag", "expected"),
    [
        ("0.2.1", "", "", "0.2.1"),
        ("0.2.1", "0.2.1", "", "0.2.2"),
        ("0.1.0", "0.9.9", "0.10.0", "0.10.1"),
        ("0.10.0", "", "0.10.0", "0.10.1"),
        ("0.3.0", "0.2.1", "", "0.3.1"),
    ],
    ids=["first-release", "above-local-tag", "above-remote-tag", "numeric-remote-sort", "pyproject-ahead"],
)
def test_suggest_version_patch_bumps_above_known_versions(current: str, last_tag: str, remote_tag: str, expected: str):
    assert _load("release").suggest_version(current, last_tag, remote_tag) == expected


def test_latest_version_picks_the_numeric_max_and_ignores_non_semver():
    latest = _load("release").latest_version(["0.9.0", "v1.0.0", "0.10.0", "latest", ""])
    assert latest == "0.10.0"


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("abc123\trefs/tags/0.2.0\n", "0.2.0"),
        ("abc123\trefs/tags/0.2.0\ndef456\trefs/tags/0.2.0^{}\n", "0.2.0"),
        (
            "a\trefs/tags/0.9.0\nb\trefs/tags/latest\nc\trefs/tags/v1.0.0\nd\trefs/tags/0.10.0\n",
            "0.10.0",
        ),
    ],
    ids=["plain", "peeled-ignored", "numeric-max"],
)
def test_latest_remote_tag_parses_ls_remote_output(output: str, expected: str):
    assert _load("release")._latest_remote_tag(output) == expected


def test_version_floor_ok_rejects_when_no_version_parses():
    assert _load("release").version_floor_ok("1.0.0", "1.0") is False


class FakeTools:
    """A temp `bin/` that shadows `uv`, `git-cliff` and `git`, recording every call."""

    def __init__(self, root: Path) -> None:
        self.bin_dir = root / "bin"
        self.bin_dir.mkdir()
        self.tool_log = root / "tools.log"
        self.git_log = root / "git.log"
        self.real_git = shutil.which("git") or "git"
        self._write(
            "uv",
            f"""#!{sys.executable}
import os
import pathlib
import sys

with open(os.environ["TOOL_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
pathlib.Path("uv.lock").write_text("version = 1\\n", encoding="utf-8")
""",
        )
        self._write(
            "git-cliff",
            f"""#!{sys.executable}
import os
import pathlib
import sys

with open(os.environ["TOOL_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
pathlib.Path("CHANGELOG.md").write_text("# Changelog\\n", encoding="utf-8")
""",
        )
        self._write(
            "git",
            f"""#!{sys.executable}
import os
import sys

if os.environ.get("FAIL_GIT_ADD") == "1" and sys.argv[1:2] == ["add"]:
    sys.exit(1)
with open(os.environ["GIT_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
os.execv(os.environ["REAL_GIT"], [os.environ["REAL_GIT"], *sys.argv[1:]])
""",
        )

    def _write(self, name: str, content: str) -> None:
        script = self.bin_dir / name
        script.write_text(content)
        script.chmod(0o755)

    def run(
        self,
        script: Path,
        *args: str,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        merged = (
            os.environ
            | GIT_ENV
            | {
                "PATH": f"{self.bin_dir}{os.pathsep}{os.environ['PATH']}",
                "TOOL_LOG": str(self.tool_log),
                "GIT_LOG": str(self.git_log),
                "REAL_GIT": self.real_git,
            }
            | (env or {})
        )
        return subprocess.run(
            [sys.executable, str(script), *args],
            cwd=cwd,
            env=merged,
            check=False,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )

    @property
    def git_invocations(self) -> list[str]:
        return self.git_log.read_text().splitlines() if self.git_log.exists() else []

    @property
    def tool_invocations(self) -> list[str]:
        return self.tool_log.read_text().splitlines() if self.tool_log.exists() else []


def _run(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=os.environ | GIT_ENV,
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )


def _repo(
    base: Path, version: str, *, branch: str = "main", tag: str | None = None, after_tag: bool = False
) -> GitRepo:
    repo = GitRepo.init(base / "repo", branch=branch)
    repo.write("pyproject.toml", f'[project]\nname = "demo"\nversion = "{version}"\n')
    repo.commit_all("init")
    if tag is not None:
        repo.run("tag", tag)
    if after_tag:
        repo.write("notes.txt", "after tag\n")
        repo.commit_all("after tag")
    return repo


def _bare_origin(base: Path, tags: tuple[str, ...] = ()) -> Path:
    """A local bare remote seeded with a commit and the requested tags (no network)."""
    origin = base / "origin.git"
    GitRepo(base).run("init", "--bare", str(origin))
    seed = GitRepo.init(base / "seed")
    seed.write("README.md", "seed\n")
    seed.commit_all("seed")
    seed.run("push", str(origin), "HEAD:refs/heads/main")
    for tag in tags:
        seed.run("tag", "-a", tag, "-m", tag)
        seed.run("push", str(origin), f"refs/tags/{tag}")
    return origin


def test_release_amends_head_tags_and_never_pushes(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")

    proc = tools.run(SCRIPTS["release"], "--version", "0.1.0", cwd=repo.path)

    assert proc.returncode == 0, proc.stderr
    assert repo.has_tag("0.1.0")
    assert repo.run("rev-parse", "0.1.0^{commit}").stdout.strip() == repo.head(), (
        "the tag must point at the amended HEAD"
    )
    assert repo.subjects() == ["init"], "release files must be amended into HEAD"
    assert {"pyproject.toml", "uv.lock", "CHANGELOG.md"} <= repo.files()
    assert load_toml(repo.path / "pyproject.toml")["project"]["version"] == "0.1.0"
    assert "Released 0.1.0" in proc.stdout
    assert "git push --follow-tags" in proc.stdout
    assert "lock" in tools.tool_invocations
    assert any("--tag 0.1.0" in command for command in tools.tool_invocations)
    assert not [command for command in tools.git_invocations if command.startswith("push")]


def test_release_honours_environment_overrides(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")

    proc = tools.run(
        SCRIPTS["release"],
        cwd=repo.path,
        env={"RELEASE_VERSION": "0.1.0", "RELEASE_YES": "1"},
    )

    assert proc.returncode == 0, proc.stderr
    assert repo.has_tag("0.1.0")


def test_release_yes_uses_the_suggested_patch(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0", tag="0.1.0", after_tag=True)

    proc = tools.run(SCRIPTS["release"], "--yes", cwd=repo.path)

    assert proc.returncode == 0, proc.stderr
    assert repo.has_tag("0.1.1")


def test_release_yes_suggests_a_patch_above_the_remote_tag(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")
    repo.run("remote", "add", "origin", str(_bare_origin(tmp_path, ("0.2.0",))))

    proc = tools.run(SCRIPTS["release"], "--yes", cwd=repo.path)

    assert proc.returncode == 0, proc.stderr
    assert repo.has_tag("0.2.1")


def test_release_rejects_existing_tag(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0", tag="0.1.0", after_tag=True)

    proc = tools.run(SCRIPTS["release"], "--version", "0.1.0", cwd=repo.path)

    assert proc.returncode == 1
    assert "already exists" in proc.stderr


def test_release_rejects_version_not_above_known(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.2.0", tag="0.3.0", after_tag=True)

    proc = tools.run(SCRIPTS["release"], "--version", "0.2.5", cwd=repo.path)

    assert proc.returncode == 1
    assert "must be above" in proc.stderr


def test_release_rejects_unparseable_pyproject_version_without_traceback(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "1.0")

    proc = tools.run(SCRIPTS["release"], "--version", "1.0.0", cwd=repo.path)

    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "pyproject" in proc.stderr.lower()


def test_release_restores_when_git_add_fails(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")

    proc = tools.run(
        SCRIPTS["release"],
        "--version",
        "0.1.0",
        "--yes",
        cwd=repo.path,
        env={"FAIL_GIT_ADD": "1"},
    )

    assert proc.returncode == 1
    assert "git add" in proc.stderr
    assert "git checkout --" in proc.stderr


def test_release_rejects_dirty_tree(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")
    repo.write("pyproject.toml", '[project]\nname = "demo"\nversion = "0.2.0"\n')

    proc = tools.run(SCRIPTS["release"], "--version", "0.2.0", cwd=repo.path)

    assert proc.returncode == 1
    assert "dirty" in proc.stderr.lower()


def test_release_rejects_release_commit_head(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")
    repo.commit_all("chore(release): prepare for 0.1.0", allow_empty=True)

    proc = tools.run(SCRIPTS["release"], "--version", "0.1.0", cwd=repo.path)

    assert proc.returncode == 1
    assert "already a release commit" in proc.stderr


@pytest.mark.parametrize(
    ("branch", "args", "blocked"),
    [("feat/side-quest", (), True), ("main", ("--version", "0.1.0", "--yes"), False)],
    ids=["off-main", "main"],
)
def test_release_branch_gate(tmp_path: Path, branch: str, args: tuple[str, ...], blocked: bool):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0", branch=branch)
    before = (repo.path / "pyproject.toml").read_text()

    proc = tools.run(SCRIPTS["release"], *args, cwd=repo.path)

    if blocked:
        assert proc.returncode == 1
        assert "expected main/master" in proc.stderr and branch in proc.stderr
        assert (repo.path / "pyproject.toml").read_text() == before
        assert not (repo.path / "CHANGELOG.md").exists()
    else:
        assert proc.returncode == 0, proc.stderr
        assert "expected main/master" not in proc.stderr
        assert repo.has_tag("0.1.0")


def test_release_rejects_tag_already_on_origin(tmp_path: Path):
    tools = FakeTools(tmp_path)
    repo = _repo(tmp_path, "0.1.0")
    repo.run("remote", "add", "origin", str(_bare_origin(tmp_path, ("0.1.0",))))

    proc = tools.run(SCRIPTS["release"], "--version", "0.1.0", "--yes", cwd=repo.path)

    assert proc.returncode == 1
    assert "already exists on origin" in proc.stderr


def _check_case(base: Path, version: str, tags: tuple[str, ...], *, origin_tags: tuple[str, ...] | None = None) -> Path:
    repo = GitRepo.init(base / "repo", branch="main")
    repo.write("pyproject.toml", f'[project]\nname = "demo"\nversion = "{version}"\n')
    repo.commit_all("init")
    for tag in tags:
        repo.run("tag", tag)
    if origin_tags is not None:
        repo.run("remote", "add", "origin", str(_bare_origin(base, origin_tags)))
    return repo.path


@pytest.mark.parametrize(
    ("version", "tags", "origin_tags", "code", "stream", "fragments"),
    [
        ("0.1.0", (), None, 0, "stdout", ("No X.Y.Z tags",)),
        ("0.1.0", ("0.1.0",), None, 0, "stdout", ("matches latest tag 0.1.0",)),
        ("0.2.0", ("0.1.0",), None, 1, "stderr", ("You bumped without tagging",)),
        ("0.1.0", ("0.2.0",), None, 1, "stderr", ("Never delete the tag", "--version above 0.2.0")),
        ("0.10.0", ("0.9.0", "0.10.0"), None, 0, "stdout", ("matches latest tag 0.10.0",)),
        ("1.0", (), None, 1, "stderr", ("Invalid pyproject version",)),
        ("0.1.0", ("0.1.0",), (), 0, "stdout", ("git push --follow-tags",)),
    ],
    ids=[
        "no-tags",
        "matching",
        "ahead",
        "tag-ahead",
        "semver-max",
        "invalid-version",
        "tag-not-on-origin",
    ],
)
def test_check_version_tag_behaviour(
    tmp_path: Path,
    version: str,
    tags: tuple[str, ...],
    origin_tags: tuple[str, ...] | None,
    code: int,
    stream: str,
    fragments: tuple[str, ...],
):
    repo = _check_case(tmp_path, version, tags, origin_tags=origin_tags)

    proc = _run(SCRIPTS["check"], cwd=repo)

    assert proc.returncode == code, proc.stderr
    output = proc.stdout if stream == "stdout" else proc.stderr
    for fragment in fragments:
        assert fragment in output
    if code == 1 and version != "1.0":
        assert "--follow-tags" in proc.stderr


def test_check_version_tag_rejects_outside_git_repo(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.1.0"\n')

    proc = _run(SCRIPTS["check"], cwd=tmp_path)

    assert proc.returncode == 1
    assert "Not inside a git repository" in proc.stderr


@pytest.mark.parametrize(
    ("name", "args", "code", "stdout"),
    [
        ("release", ("--help",), 0, ("--version", "--yes")),
        ("release", ("--bogus",), 2, ()),
        ("check", ("--help",), 0, ("pyproject",)),
        ("check", ("--bogus",), 2, ()),
    ],
    ids=["release-help", "release-unknown-flag", "check-help", "check-unknown-flag"],
)
def test_scripts_cli_contract(name: str, args: tuple[str, ...], code: int, stdout: tuple[str, ...]):
    proc = _run(SCRIPTS[name], *args)
    assert proc.returncode == code, proc.stderr
    for token in stdout:
        assert token in proc.stdout.lower()


def test_release_tasks_and_hooks_wire_python_scripts(projects: ProjectRegistry):
    root_tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert root_tasks["release"]["run"] == "uv run python scripts/release.py"
    assert root_tasks["check:version-tag"]["run"] == "uv run python scripts/check_version_tag.py"

    for variant in ("basic", "python313-licensed"):
        project = projects.render(variant)
        scripts = project.path / "scripts"
        assert {path.name for path in scripts.iterdir()} == {"release.py", "check_version_tag.py"}, (
            f"{variant}: the payload ships exactly the two Python release scripts"
        )
        for name in ("release.py", "check_version_tag.py"):
            script = scripts / name
            assert os.access(script, os.X_OK), f"{name} must be executable"
            assert script.read_text(encoding="utf-8").splitlines()[0] == "#!/usr/bin/env python3"
        data = project.mise()
        assert "gum" in data["tools"]
        assert "uv run python scripts/release.py" in data["tasks"]["release"]["run"]
        assert "uv run python scripts/check_version_tag.py" in data["tasks"]["check:version-tag"]["run"]

    hooks = {
        hook["id"]: hook
        for repo in load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")["repos"]
        for hook in repo["hooks"]
    }
    assert hooks["check-version-tag"].get("stages") == ["pre-push"]
    assert hooks["check-version-tag"]["entry"] == "mise run check:version-tag"


def test_inline_shell_tasks_use_bash_skip_guards(projects: ProjectRegistry):
    """Root and rendered manifests open inline tasks with a bash header and `[[ -d ]]` skips."""
    root_tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    rendered_tasks = projects.render("github").mise()["tasks"]
    for label, tasks in (("root", root_tasks), ("rendered", rendered_tasks)):
        integration = tasks["test:integration"]["run"]
        assert integration.startswith("#!/usr/bin/env bash\n"), label
        assert "set -euo pipefail" in integration, label
        assert "[[ -d tests/integration ]]" in integration, label
    workflows = rendered_tasks["lint:workflows"]["run"]
    assert workflows.startswith("#!/usr/bin/env bash\n"), "rendered"
    assert "set -euo pipefail" in workflows, "rendered"
    assert "[[ -d .github/workflows ]]" in workflows, "rendered"
