"""`python_version` question, rendered pins and `copier.yaml` settings."""

from __future__ import annotations

import re

import pytest
from _projects import PYTHON_VERSION_ANSWER_LINE, ProjectRegistry, copier_config


def test_python_version_choices_are_released_quoted_versions():
    """Choices are `"3.x": "3.x"` string pairs at or above 3.12, and the default is one of them."""
    question = copier_config()["python_version"]
    choices = question["choices"]
    assert all(key == value for key, value in choices.items()), f"choice keys must equal their values: {choices!r}"
    assert all(isinstance(v, str) and re.fullmatch(r"3\.(\d+)", v) for v in choices.values()), choices
    assert all(int(v.split(".")[1]) >= 12 for v in choices.values()), f"choices must be >= 3.12: {choices!r}"
    assert question["default"] in choices


def test_copier_tasks_install_then_pin_uv_sync_to_selected_python():
    """The pin step must consume the selected answer and run before sync, which reads that pin."""
    tasks = copier_config()["_tasks"]
    install = next(task for task in tasks if isinstance(task, list) and task[:3] == ["uv", "python", "install"])
    pin = next(task for task in tasks if isinstance(task, list) and task[:3] == ["uv", "python", "pin"])
    sync = next(task for task in tasks if isinstance(task, list) and task[:2] == ["uv", "sync"])
    assert install[3] == "{{ python_version }}"
    assert pin[3] == "{{ python_version }}"
    assert sync[2:] == [], "uv sync must read the uv-managed .python-version, not a --python flag"
    assert tasks.index(install) < tasks.index(pin) < tasks.index(sync)


def test_files_only_render_ships_no_python_version_file(projects: ProjectRegistry):
    """`uv python pin` is the only creator: a files-only render must not ship a pin of its own."""
    project = projects.render("lib-licensed")
    assert not (project.path / ".python-version").exists()


@pytest.mark.parametrize("variant", ["basic", "lib-licensed"])
def test_render_pins_selected_python_version(projects: ProjectRegistry, variant: str):
    """The question default (3.12) and an explicit answer drive every pin."""
    project = projects.render(variant)
    version = str(project.answer("python_version"))
    config = project.pyproject()
    assert config["project"]["requires-python"] == f">={version}"
    assert config["tool"]["ruff"]["target-version"] == f"py{version.replace('.', '')}"
    answers = project.read(".copier-answers.yml")
    assert re.search(PYTHON_VERSION_ANSWER_LINE.format(version=re.escape(version)), answers), answers


def test_render_moves_python_pin_from_mise_to_short_python_version_file(projects: ProjectRegistry):
    """uv owns the interpreter pin: a short `.python-version` replaces mise's `python` tool."""
    project = projects.render("basic")
    version = str(project.answer("python_version"))
    assert "python" not in project.mise_tools(), f"mise.toml must not pin Python: {project.mise_tools()}"
    assert project.read(".python-version") == f"{version}\n", "uv pin must be the short version only"


def test_copy_with_tasks_commits_short_uv_pin_file(projects: ProjectRegistry):
    """A task-running copy leaves the pin's short `.python-version` inside the scaffold commit."""
    project = projects.render("basic")
    version = str(project.answer("python_version"))

    assert project.read(".python-version") == f"{version}\n", "uv pin must be the short version only"
    assert project.repo().subjects()[0] == "chore: scaffold from copier template"
    committed = project.repo().files()
    assert ".python-version" in committed, f"scaffold commit must carry the pin: {committed}"
    assert "uv.lock" in committed, f"scaffold commit must carry the generated lock: {committed}"
