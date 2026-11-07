"""Version module shared by `release.sh` and `check-version-tag.sh`.

`templates/scripts/release_version.py` is the single source of version
knowledge: parsing, bumping, suggestion, drift and tag selection. Shell
scripts delegate to it instead of embedding semver heredocs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from _projects import TEMPLATE_ROOT

MODULE = TEMPLATE_ROOT / "templates" / "scripts" / "release_version.py"

try:
    import release_version as _release_version
except ModuleNotFoundError as exc:
    # Only the not-yet-authored payload module is expected to be missing;
    # a broken import inside it must still fail loudly at collection time.
    if exc.name != "release_version":
        raise
    _release_version = None

if _release_version is None:

    class _MissingReleaseVersion:
        """Turn every access into the expected missing-file failure, not a collection error."""

        def __getattr__(self, name: str) -> Any:
            raise AssertionError(f"Missing version module: {MODULE} (no attribute {name})")

    release_version: Any = _MissingReleaseVersion()
else:
    release_version = _release_version


def run_cli(
    *args: str,
    stdin: str = "",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the module's CLI with `python` and capture the result."""
    return subprocess.run(  # noqa: S603
        [sys.executable, str(MODULE), *args],
        check=False,
        capture_output=True,
        text=True,
        input=stdin,
        cwd=cwd,
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.0.0", (0, 0, 0)),
        ("0.1.0", (0, 1, 0)),
        ("1.2.3", (1, 2, 3)),
        ("10.20.30", (10, 20, 30)),
    ],
)
def test_parse_version_accepts_plain_semver(text: str, expected: tuple[int, int, int]):
    assert release_version.parse_version(text) == expected


@pytest.mark.parametrize("text", ["v1.2.3", "1.2", "1.2.3.4"])
def test_parse_version_rejects_non_plain_semver(text: str):
    with pytest.raises(ValueError):
        release_version.parse_version(text)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("patch", "1.2.4"),
        ("minor", "1.3.0"),
        ("major", "2.0.0"),
    ],
)
def test_bump_resets_lower_parts(kind: str, expected: str):
    assert release_version.bump("1.2.3", kind) == expected


@pytest.mark.parametrize(
    ("bump_kind", "current", "local", "remote", "expected"),
    [
        ("patch", "0.2.1", "", "", "0.2.1"),
        ("minor", "0.2.1", "", "", "0.2.1"),
        ("patch", "0.2.1", "0.2.1", "", "0.2.2"),
        ("patch", "0.2.1", "", "0.2.5", "0.2.6"),
        ("patch", "0.1.0", "0.9.9", "0.10.0", "0.10.1"),
        ("patch", "0.3.0", "0.2.1", "", "0.3.1"),
        ("minor", "0.2.1", "0.2.1", "", "0.3.0"),
        ("minor", "0.2.9", "", "0.3.4", "0.4.0"),
        ("major", "0.2.1", "0.2.1", "", "1.0.0"),
        ("major", "1.2.9", "1.9.9", "0.10.0", "2.0.0"),
    ],
    ids=[
        "first-release",
        "first-release-ignores-bump",
        "above-local",
        "above-remote",
        "numeric-never-minor",
        "pyproject-ahead",
        "minor-resets-patch",
        "minor-above-remote",
        "major-resets",
        "major-above-local",
    ],
)
def test_suggest_bumps_highest_numeric_version(bump_kind: str, current: str, local: str, remote: str, expected: str):
    assert release_version.suggest(bump_kind, current, local, remote) == expected


@pytest.mark.parametrize(
    ("version", "current", "local", "remote", "expected"),
    [
        ("0.1.0", "0.1.0", "", "", True),
        ("0.1.1", "0.1.0", "", "", True),
        ("0.1.0", "0.1.1", "", "", False),
        ("0.1.0", "0.1.0", "0.1.0", "", False),
        ("0.1.1", "0.1.0", "0.1.0", "", True),
        ("0.1.0", "0.1.0", "", "0.1.0", False),
        ("0.10.1", "0.9.9", "0.10.0", "", True),
        ("1.0.0", "0.2.1", "0.9.9", "0.10.0", True),
    ],
    ids=[
        "no-tags-allows-equal",
        "no-tags-allows-above",
        "no-tags-below-current",
        "tag-floor-rejects-equal",
        "tag-floor-allows-above",
        "remote-floor-rejects-equal",
        "numeric-ordering",
        "above-all-floors",
    ],
)
def test_is_above_floor_requires_strictly_above_tags(
    version: str, current: str, local: str, remote: str, expected: bool
):
    assert release_version.is_above_floor(version, current, local, remote) is expected


def test_latest_tag_picks_highest_plain_semver():
    lines = iter(["0.9.0", "0.10.0", "v1.0.0", "latest", "", "1.2"])
    assert release_version.latest_tag(lines) == "0.10.0"


def test_latest_tag_is_empty_without_semver():
    assert release_version.latest_tag(iter(["", "v1.0.0", "latest"])) == ""


def test_latest_remote_tag_picks_highest_plain_semver():
    lines = iter(
        [
            "aaa\trefs/tags/0.9.0",
            "bbb\trefs/tags/0.10.0",
            "ccc\trefs/tags/0.10.0^{}",
            "ddd\trefs/tags/v1.0.0",
            "eee\trefs/tags/latest",
            "",
        ]
    )
    assert release_version.latest_remote_tag(lines) == "0.10.0"


def test_latest_remote_tag_is_empty_without_semver():
    assert release_version.latest_remote_tag(iter(["aaa\trefs/tags/v1.0.0", "bbb\trefs/tags/latest"])) == ""


@pytest.mark.parametrize(
    ("current", "latest", "expected"),
    [
        ("0.1.0", "", "no-tags"),
        ("0.1.0", "0.1.0", "ok"),
        ("0.2.0", "0.1.0", "ahead"),
        ("0.1.0", "0.2.0", "behind"),
    ],
)
def test_classify_drift_names_each_state(current: str, latest: str, expected: str):
    assert release_version.classify_drift(current, latest) == expected


def test_read_project_version_reads_project_table(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.4.2"\n', encoding="utf-8")
    assert release_version.read_project_version(pyproject) == "1.4.2"


@pytest.mark.parametrize(
    "content",
    [
        '[project]\nname = "demo"\n',
        '[project]\nname = "demo"\nversion = "1.2"\n',
        '[tool.other]\nversion = "1.2.3"\n',
    ],
    ids=["missing-version", "invalid-version", "missing-project-table"],
)
def test_read_project_version_raises_on_missing_or_invalid(tmp_path: Path, content: str):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content, encoding="utf-8")
    with pytest.raises((KeyError, ValueError)):
        release_version.read_project_version(pyproject)


def test_update_project_version_replaces_the_project_version_line():
    text = '[project]\nname = "demo"\nversion = "1.4.2"\n'
    assert release_version.update_project_version(text, "2.0.0") == '[project]\nname = "demo"\nversion = "2.0.0"\n'


def test_update_project_version_preserves_all_other_bytes():
    """Only the `[project] version` line changes; comments, spacing and other tables stay byte-identical."""
    text = (
        "# leading comment\n"
        "[project]\n"
        'name = "demo"\n'
        "dynamic = []\n"
        'version = "1.4.2"\n'
        "\n"
        "[tool.other]\n"
        'version = "9.9.9"\n'
        'target-version = "py312"\n'
    )
    expected = (
        "# leading comment\n"
        "[project]\n"
        'name = "demo"\n'
        "dynamic = []\n"
        'version = "2.0.0"\n'
        "\n"
        "[tool.other]\n"
        'version = "9.9.9"\n'
        'target-version = "py312"\n'
    )
    assert release_version.update_project_version(text, "2.0.0") == expected


@pytest.mark.parametrize(
    "text",
    [
        '[project]\nname = "demo"\n',
        '[tool.other]\nversion = "1.2.3"\n',
    ],
    ids=["missing-version", "version-only-outside-project"],
)
def test_update_project_version_raises_without_a_project_version(text: str):
    with pytest.raises(ValueError):
        release_version.update_project_version(text, "2.0.0")


def test_update_project_version_raises_on_duplicate_project_versions():
    text = '[project]\nname = "demo"\nversion = "1.4.2"\nversion = "1.4.3"\n'
    with pytest.raises(ValueError):
        release_version.update_project_version(text, "2.0.0")


def test_set_project_version_rewrites_the_file(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.4.2"\n', encoding="utf-8")
    release_version.set_project_version(pyproject, "2.0.0")
    assert pyproject.read_text(encoding="utf-8") == '[project]\nname = "demo"\nversion = "2.0.0"\n'


def test_cli_set_version_is_idempotent(tmp_path: Path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "1.4.2"\n', encoding="utf-8")

    first = run_cli("set-version", "2.0.0", str(pyproject))
    assert first.returncode == 0, first.stderr
    rewritten = pyproject.read_text(encoding="utf-8")
    assert rewritten == '[project]\nname = "demo"\nversion = "2.0.0"\n'

    second = run_cli("set-version", "2.0.0", str(pyproject))
    assert second.returncode == 0, second.stderr
    assert pyproject.read_text(encoding="utf-8") == rewritten


def test_cli_project_version_reads_explicit_path(tmp_path: Path):
    pyproject = tmp_path / "custom.toml"
    pyproject.write_text('[project]\nname = "demo"\nversion = "2.3.4"\n', encoding="utf-8")
    proc = run_cli("project-version", str(pyproject))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "2.3.4"


def test_cli_project_version_defaults_to_cwd(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.4.0"\n', encoding="utf-8")
    proc = run_cli("project-version", cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0.4.0"


def test_cli_latest_tag_reads_stdin():
    proc = run_cli("latest-tag", stdin="0.9.0\n0.10.0\nv1.0.0\n")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0.10.0"


def test_cli_latest_remote_tag_reads_stdin():
    proc = run_cli("latest-remote-tag", stdin="aaa\trefs/tags/0.9.0\nbbb\trefs/tags/0.10.0\n")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "0.10.0"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("--bump", "patch", "--current", "0.2.1"), "0.2.1"),
        (("--bump", "patch", "--current", "0.2.1", "--local", "0.2.1"), "0.2.2"),
        (
            ("--bump", "patch", "--current", "0.1.0", "--local", "0.9.9", "--remote", "0.10.0"),
            "0.10.1",
        ),
        (("--bump", "minor", "--current", "0.2.9", "--remote", "0.3.4"), "0.4.0"),
        (("--bump", "major", "--current", "1.2.9", "--local", "1.9.9"), "2.0.0"),
    ],
)
def test_cli_suggest_matches_module(args: tuple[str, ...], expected: str):
    proc = run_cli("suggest", *args)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("--version", "0.1.0", "--current", "0.1.0"), 0),
        (("--version", "0.1.1", "--current", "0.1.0"), 0),
        (("--version", "0.1.0", "--current", "0.2.0"), 1),
        (("--version", "0.1.0", "--current", "0.1.0", "--local", "0.1.0"), 1),
        (("--version", "0.1.1", "--current", "0.1.0", "--local", "0.1.0"), 0),
        (("--version", "0.1.0", "--current", "0.1.0", "--remote", "0.1.0"), 1),
        (("--version", "0.10.1", "--current", "0.9.9", "--local", "0.10.0"), 0),
    ],
    ids=[
        "no-tags-equal",
        "no-tags-above",
        "no-tags-below",
        "local-equal",
        "local-above",
        "remote-equal",
        "numeric-above",
    ],
)
def test_cli_check_floor_exit_codes(args: tuple[str, ...], expected: int):
    proc = run_cli("check-floor", *args)
    assert proc.returncode == expected, proc.stderr


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (("--current", "0.1.0"), "no-tags"),
        (("--current", "0.1.0", "--latest", "0.1.0"), "ok"),
        (("--current", "0.2.0", "--latest", "0.1.0"), "ahead"),
        (("--current", "0.1.0", "--latest", "0.2.0"), "behind"),
    ],
)
def test_cli_classify_prints_state(args: tuple[str, ...], expected: str):
    proc = run_cli("classify", *args)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == expected
