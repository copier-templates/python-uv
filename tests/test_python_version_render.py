"""Rendered projects: the selected `python_version` reaches every payload file that pins it."""

from __future__ import annotations

import re

import pytest
from _projects import PYTHON_VERSION_ANSWER_LINE, ProjectRegistry, mise_tools, pyproject


@pytest.mark.parametrize(("variant", "version"), [("basic", "3.12"), ("python313", "3.13")])
def test_render_pins_selected_python_version(projects: ProjectRegistry, variant: str, version: str):
    """The question default (3.12) and an explicit answer drive every pin."""
    project = projects.render(variant)
    config = pyproject(project)

    assert mise_tools(project)["python"] == version
    assert config["project"]["requires-python"] == f">={version}"
    assert config["tool"]["ruff"]["target-version"] == f"py{version.replace('.', '')}"
    answers = (project / ".copier-answers.yml").read_text()
    assert re.search(PYTHON_VERSION_ANSWER_LINE.format(version=re.escape(version)), answers), answers
