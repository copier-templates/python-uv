"""`sync_shared_refs.py` CLI: one-command shared-ref bumps with `--check` for the pre-commit guard."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _projects import SHARED_REF, TEMPLATE_ROOT

SCRIPT = TEMPLATE_ROOT / "scripts" / "sync_shared_refs.py"

OLD = SHARED_REF
NEW = "0.9.9"

SHARED_REPO = "https://github.com/copier-templates/shared-dev-tooling"
SHARED_INCLUDES = [
    f"git::{SHARED_REPO}.git//tasks/core?ref={OLD}",
    f"git::{SHARED_REPO}.git//tasks/toml?ref={OLD}",
]

MISE_TOML = f"""\
min_version = "2026.11.10"

[settings]
experimental = true

[task_config]
includes = [
  "{SHARED_INCLUDES[0]}",
  "{SHARED_INCLUDES[1]}",
]
"""

PREK_TOML = f"""\
[update.repos."{SHARED_REPO}"]
include_tags = [
  "{OLD}",
]

[[repos]]
repo = "https://example.com/unrelated-hooks"
rev = "{OLD}"
hooks = [
  {{ id = "example", priority = "checks" }},
]

[[repos]]
repo = "{SHARED_REPO}"
rev = "{OLD}"
hooks = [
  {{ id = "taplo-fmt", priority = "fix-toml" }},
]
"""

PROJECTS_PY = f"""\
SHARED_REF = "{OLD}"
UNRELATED = "{OLD}"
"""


def _write_template_tree(root: Path) -> None:
    (root / "mise.toml").write_text(MISE_TOML)
    (root / "templates").mkdir()
    (root / "templates" / "mise.toml.jinja").write_text(MISE_TOML)
    (root / "templates" / "prek.toml").write_text(PREK_TOML)
    (root / "tests").mkdir()
    (root / "tests" / "_projects.py").write_text(PROJECTS_PY)


def _write_rendered_tree(root: Path) -> None:
    (root / "mise.toml").write_text(MISE_TOML)
    (root / "prek.toml").write_text(PREK_TOML)


def _run(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tree), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_check_passes_when_every_pin_matches(tmp_path: Path):
    """A tree already at one ref is clean: exit 0, files untouched."""
    _write_template_tree(tmp_path)
    proc = _run(tmp_path, "--check")
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "templates" / "prek.toml").read_text() == PREK_TOML


def test_check_reports_the_drifted_file(tmp_path: Path):
    """`--check` exits 1 and names the file when the prek rev drifts behind mise."""
    _write_template_tree(tmp_path)
    prek = tmp_path / "templates" / "prek.toml"
    prek.write_text(
        PREK_TOML.replace(f'repo = "{SHARED_REPO}"\nrev = "{OLD}"', f'repo = "{SHARED_REPO}"\nrev = "{NEW}"')
    )
    proc = _run(tmp_path, "--check")
    assert proc.returncode == 1
    assert "templates/prek.toml" in proc.stdout


def test_to_rewrites_every_pin_and_nothing_else(tmp_path: Path):
    """`--to` moves all four pins in a template tree without touching unrelated pins."""
    _write_template_tree(tmp_path)
    proc = _run(tmp_path, "--to", NEW)
    assert proc.returncode == 0, proc.stderr
    for rel in ("mise.toml", "templates/mise.toml.jinja"):
        content = (tmp_path / rel).read_text()
        assert NEW in content, rel
        assert OLD not in content, rel
    prek = (tmp_path / "templates" / "prek.toml").read_text()
    assert prek.count(f'rev = "{NEW}"') == 1
    assert f'include_tags = [\n  "{NEW}",\n]' in prek
    assert f'repo = "https://example.com/unrelated-hooks"\nrev = "{OLD}"' in prek
    projects = (tmp_path / "tests" / "_projects.py").read_text()
    assert f'SHARED_REF = "{NEW}"' in projects
    assert f'UNRELATED = "{OLD}"' in projects
    assert _run(tmp_path, "--check").returncode == 0


def test_to_accepts_any_ref_scheme(tmp_path: Path):
    """The tag scheme is upstream's choice: `v`-prefixed (or other) refs move every pin."""
    _write_template_tree(tmp_path)
    proc = _run(tmp_path, "--to", "v9.9.9")
    assert proc.returncode == 0, proc.stderr
    for rel in ("mise.toml", "templates/mise.toml.jinja"):
        content = (tmp_path / rel).read_text()
        assert "v9.9.9" in content, rel
        assert OLD not in content, rel
    prek = (tmp_path / "templates" / "prek.toml").read_text()
    assert 'rev = "v9.9.9"' in prek
    assert 'include_tags = [\n  "v9.9.9",\n]' in prek
    assert 'SHARED_REF = "v9.9.9"' in (tmp_path / "tests" / "_projects.py").read_text()
    assert _run(tmp_path, "--check").returncode == 0


def test_conflicting_mise_refs_are_an_error(tmp_path: Path):
    """Without `--to`, mixed `?ref=` values fail instead of guessing a winner."""
    _write_template_tree(tmp_path)
    mise = tmp_path / "mise.toml"
    mise.write_text(MISE_TOML.replace(f"?ref={OLD}", f"?ref={NEW}", 1))
    proc = _run(tmp_path, "--check")
    assert proc.returncode == 2
    assert "one ref" in proc.stderr


def test_new_task_category_is_picked_up_automatically(tmp_path: Path):
    """A category the script never heard of is still managed: drift fails, `--to` moves it."""
    _write_template_tree(tmp_path)
    extra = f'  "git::{SHARED_REPO}.git//tasks/security?ref={NEW}",\n'
    for rel in ("mise.toml", "templates/mise.toml.jinja"):
        path = tmp_path / rel
        lines = path.read_text().splitlines(keepends=True)
        index = next(i for i, line in enumerate(lines) if SHARED_INCLUDES[0] in line)
        lines.insert(index + 1, extra)
        path.write_text("".join(lines))
    proc = _run(tmp_path, "--check")
    assert proc.returncode == 2
    assert "one ref" in proc.stderr
    assert _run(tmp_path, "--to", NEW).returncode == 0
    for rel in ("mise.toml", "templates/mise.toml.jinja"):
        content = (tmp_path / rel).read_text()
        assert f"//tasks/security?ref={NEW}" in content, rel
    assert _run(tmp_path, "--check").returncode == 0


def test_rendered_mode_syncs_only_the_local_prek_toml(tmp_path: Path):
    """Rendered projects have no payload: only the local prek rev follows the local includes."""
    _write_rendered_tree(tmp_path)
    prek = tmp_path / "prek.toml"
    prek.write_text(
        PREK_TOML.replace(f'repo = "{SHARED_REPO}"\nrev = "{OLD}"', f'repo = "{SHARED_REPO}"\nrev = "{NEW}"')
    )
    assert _run(tmp_path, "--check").returncode == 1
    assert _run(tmp_path, "--to", NEW).returncode == 0
    assert f'rev = "{NEW}"' in prek.read_text()
    assert not (tmp_path / "templates").exists()


def test_check_passes_on_the_real_template_tree():
    """The guard must be green on this repo itself; `test_sync.py` owns the drift assertions."""
    proc = _run(TEMPLATE_ROOT, "--check")
    assert proc.returncode == 0, proc.stdout + proc.stderr


OTHER_REPO = "https://example.com/other-tools"
OTHER_MISE_TOML = f"""\
[task_config]
includes = [
  "{SHARED_INCLUDES[0]}",
  "git::{OTHER_REPO}.git//tasks/extra?ref=1.0.0",
]
"""

OTHER_PREK_TOML = f"""\
[update.repos."{OTHER_REPO}"]
include_tags = [
  "1.0.0",
]

[update.repos."{SHARED_REPO}"]
include_tags = [
  "{OLD}",
]

[[repos]]
repo = "{SHARED_REPO}"
rev = "{OLD}"
hooks = [
  {{ id = "taplo-fmt", priority = "fix-toml" }},
]

[[repos]]
repo = "{OTHER_REPO}"
rev = "1.0.0"
hooks = [
  {{ id = "other-hook", priority = "checks" }},
]
"""


def _write_two_source_tree(root: Path) -> None:
    (root / "mise.toml").write_text(OTHER_MISE_TOML)
    (root / "templates").mkdir()
    (root / "templates" / "mise.toml.jinja").write_text(OTHER_MISE_TOML)
    (root / "templates" / "prek.toml").write_text(OTHER_PREK_TOML)
    (root / "tests").mkdir()
    (root / "tests" / "_projects.py").write_text(PROJECTS_PY)


def test_second_upstream_groups_independently(tmp_path: Path):
    """Different refs across different sources are fine; `--to` moves every source."""
    _write_two_source_tree(tmp_path)
    assert _run(tmp_path, "--check").returncode == 0
    assert _run(tmp_path, "--to", NEW).returncode == 0
    for rel in ("mise.toml", "templates/mise.toml.jinja"):
        content = (tmp_path / rel).read_text()
        assert content.count(f"?ref={NEW}") == 2, rel
        assert "?ref=1.0.0" not in content, rel
    prek = (tmp_path / "templates" / "prek.toml").read_text()
    assert prek.count(f'rev = "{NEW}"') == 2
    assert '"1.0.0"' not in prek
    assert _run(tmp_path, "--check").returncode == 0


def test_include_tags_glob_patterns_are_preserved(tmp_path: Path):
    """`--to` moves exact pins but never rewrites glob patterns such as `v*`."""
    _write_template_tree(tmp_path)
    prek = tmp_path / "templates" / "prek.toml"
    prek.write_text(PREK_TOML.replace(f'  "{OLD}",\n', f'  "v*",\n  "{OLD}",\n'))
    assert _run(tmp_path, "--to", NEW).returncode == 0
    content = prek.read_text()
    assert f'include_tags = [\n  "v*",\n  "{NEW}",\n]' in content
    assert f'repo = "{SHARED_REPO}"\nrev = "{NEW}"' in content
    assert _run(tmp_path, "--check").returncode == 0
