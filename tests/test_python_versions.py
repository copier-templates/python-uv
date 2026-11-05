"""Static regression tests for the `python_version` question in `copier.yaml`."""

from __future__ import annotations

import re

from _projects import TEMPLATE_ROOT, copier_config
from update_python_versions import BEGIN_MARKER, END_MARKER, update_copier_yaml


def test_python_version_choices_are_released_quoted_versions():
    """Choices are `"3.x": "3.x"` string pairs at or above 3.11, and the default is one of them."""
    question = copier_config()["python_version"]
    choices = question["choices"]

    assert all(key == value for key, value in choices.items()), f"choice keys must equal their values: {choices!r}"
    assert all(isinstance(v, str) and re.fullmatch(r"3\.(\d+)", v) for v in choices.values()), choices
    assert all(int(v.split(".")[1]) >= 11 for v in choices.values()), f"choices must be >= 3.11: {choices!r}"
    assert question["default"] in choices


def test_python_version_choices_block_round_trips_through_the_update_script():
    """The managed marker block holds exactly the parsed choices, in the script's own format."""
    text = (TEMPLATE_ROOT / "copier.yaml").read_text()
    versions = list(copier_config()["python_version"]["choices"])

    assert BEGIN_MARKER in text
    assert END_MARKER in text
    assert update_copier_yaml(text, versions) == text


def test_copier_tasks_install_selected_python_before_sync():
    """`uv python install <python_version>` must run before `uv sync`."""
    tasks = copier_config()["_tasks"]

    install = next(task for task in tasks if isinstance(task, list) and task[:3] == ["uv", "python", "install"])
    assert "python_version" in install[3]
    assert tasks.index(install) < tasks.index(["uv", "sync"])
