"""`project_name` validation: the name must yield a valid Python module."""

from __future__ import annotations

from pathlib import Path

import pytest
from _projects import BASE_DATA, run_copy_from


def test_project_name_with_leading_digit_is_rejected(template_source: Path, tmp_path: Path) -> None:
    """`123app` would render `module_name` `123app`, an invalid identifier."""
    data = BASE_DATA | {"project_name": "123app"}
    with pytest.raises(ValueError, match="(?i)project name.*digit"):
        run_copy_from(template_source, tmp_path / "bad-name", data)
