"""Maintainer release CLIs share one logging/die/need_cmd preamble.

`scripts/maintainer/lib/common.sh` is the single implementation. Both release
scripts source it through a script-relative path and keep only their own
`usage`/`usage_error` (which print script-specific text). End-to-end behavior
stays covered by `test_release_workflow.py`; these tests pin the shared seam.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
from _projects import TEMPLATE_ROOT

MAINTAINER = TEMPLATE_ROOT / "scripts" / "maintainer"
COMMON = MAINTAINER / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"
RELEASE_SCRIPTS = (
    MAINTAINER / "release" / "resolve-version.sh",
    MAINTAINER / "release" / "cleanup-tag.sh",
)
SCRIPT_IDS = tuple(script.name for script in RELEASE_SCRIPTS)

# `source "$SCRIPT_DIR/../lib/common.sh"` (quoting/braces may vary).
SCRIPT_RELATIVE_SOURCE_RE = re.compile(
    r"""^\s*(?:source|\.)\s+["']?\$\{?SCRIPT_DIR\}?/\.\./lib/common\.sh["']?\s*$""",
    re.MULTILINE,
)


@pytest.mark.parametrize("script", RELEASE_SCRIPTS, ids=SCRIPT_IDS)
def test_release_script_sources_shared_common_relative_to_script_dir(script: Path):
    content = script.read_text()
    assert SCRIPT_RELATIVE_SOURCE_RE.search(content), (
        f"{script.name} must source ../lib/common.sh via a SCRIPT_DIR-relative path"
    )


@pytest.mark.parametrize("script", RELEASE_SCRIPTS, ids=SCRIPT_IDS)
def test_release_script_does_not_redefine_shared_helpers(script: Path):
    content = script.read_text()
    for helper in ("die", "need_cmd"):
        assert not re.search(rf"^{helper}\(\)", content, re.MULTILINE), (
            f"{script.name} still defines {helper}(); source lib/common.sh instead"
        )


def test_common_script_defines_shared_helpers():
    content = COMMON.read_text()
    for helper in ("die", "need_cmd"):
        assert re.search(rf"^{helper}\(\)", content, re.MULTILINE), f"lib/common.sh must define {helper}()"


@pytest.mark.parametrize("script", RELEASE_SCRIPTS, ids=SCRIPT_IDS)
def test_release_script_keeps_usage_error_local(script: Path):
    content = script.read_text()
    assert re.search(r"^usage_error\(\)", content, re.MULTILINE), (
        f"{script.name} must keep its own usage_error() so usage prints this script's text"
    )


def _run_common(snippet: str) -> subprocess.CompletedProcess[str]:
    """Run a snippet right after sourcing lib/common.sh in a fresh bash."""
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{COMMON}"\n{snippet}'],
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("script_name", ["release-resolve-version", "cleanup-tag"])
def test_die_with_script_name_prefixes_message_and_exits_one(script_name: str):
    proc = _run_common(f'SCRIPT_NAME="{script_name}"\ndie "boom"')
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == f"{script_name}: boom\n"


def test_die_without_script_name_keeps_default_error_prefix():
    proc = _run_common('die "boom"')
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == "✗ boom\n"


def test_need_cmd_missing_tool_without_hint_has_no_trailing_space():
    proc = _run_common('SCRIPT_NAME="cleanup-tag"\nneed_cmd definitely-not-a-tool')
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == "cleanup-tag: Required tool 'definitely-not-a-tool' not found.\n"


def test_need_cmd_missing_tool_with_hint_appends_hint():
    proc = _run_common('SCRIPT_NAME="cleanup-tag"\nneed_cmd definitely-not-a-tool "Install it: brew install x"')
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert proc.stderr == ("cleanup-tag: Required tool 'definitely-not-a-tool' not found. Install it: brew install x\n")


@pytest.mark.parametrize("script", RELEASE_SCRIPTS, ids=SCRIPT_IDS)
def test_release_script_help_and_unknown_flag_from_unrelated_cwd(script: Path, tmp_path: Path):
    """Help must work from any CWD, then reject unknown flags with exit 2."""
    help_proc = subprocess.run(  # noqa: S603
        [str(script), "--help"], check=False, capture_output=True, text=True, cwd=tmp_path
    )
    assert help_proc.returncode == 0, help_proc.stderr
    assert "Usage:" in help_proc.stdout
    assert "--sha" in help_proc.stdout

    bad_flag = subprocess.run(  # noqa: S603
        [str(script), "--bogus"], check=False, capture_output=True, text=True, cwd=tmp_path
    )
    assert bad_flag.returncode == 2
    assert "Unknown option: --bogus" in bad_flag.stderr
