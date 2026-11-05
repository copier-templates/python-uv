"""Blank-line separation between sections in rendered pyproject.toml."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from _projects import ProjectRegistry

# A new top-level section starts a TOML table header or one of the bare keys
# that follow conditional content inside [project]. Each must be preceded by
# a blank line (except at the start of file). Intra-table keys, array items,
# and comments are intentionally not matched.
_SECTION_START_RE = re.compile(r"^(?:\[|classifiers = \[|dependencies = \[|license = )")


def _assert_section_separation(path: Path) -> None:
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        if _SECTION_START_RE.match(line):
            assert i == 0 or lines[i - 1].strip() == "", (
                f"{path.name}:{i + 1} {line!r} should be preceded by a blank line"
            )


@pytest.mark.parametrize("variant", ["basic", "ruff", "app", "lib", "license"])
def test_pyproject_sections_separated_by_blank_lines(projects: ProjectRegistry, variant: str):
    """Every rendered variant (package/app/lib, with/without ruff/license)
    must separate top-level sections with at least one blank line, no matter
    which conditional blocks were skipped. Registry renders are cached: no
    extra Copier renders."""
    _assert_section_separation(projects.render(variant) / "pyproject.toml")
