"""Dead-code gate (vulture): rendered projects scan an explicit allowlist.

`[tool.vulture] paths` is the allowlist — anything not listed is never
scanned. Mise (`lint:deadcode`) and prek (local hook) both run bare
`vulture` so folders live in config first.
"""

from __future__ import annotations

from _projects import TEMPLATE_ROOT, ProjectRegistry, load_toml, mise_toml, pyproject, refs


def _vulture(project) -> dict:
    tool = pyproject(project)["tool"]
    assert "vulture" in tool, "rendered pyproject.toml must declare [tool.vulture]"
    return tool["vulture"]


def test_rendered_dev_deps_include_vulture(projects: ProjectRegistry):
    dev = pyproject(projects.render("basic"))["dependency-groups"]["dev"]
    assert "vulture>=2.16" in dev


def test_rendered_vulture_config_is_allowlist(projects: ProjectRegistry):
    vulture = _vulture(projects.render("basic"))
    assert vulture["min_confidence"] == 60
    assert set(vulture["paths"]) == {"src", "tests", "whitelist_vulture.py"}
    assert "test_*" in vulture["ignore_names"]
    assert "@pytest.fixture" in vulture["ignore_decorators"]


def test_rendered_app_vulture_paths_use_main(projects: ProjectRegistry):
    vulture = _vulture(projects.render("app"))
    assert set(vulture["paths"]) == {"main.py", "tests", "whitelist_vulture.py"}


def test_rendered_mise_has_deadcode_task_in_lint(projects: ProjectRegistry):
    tasks = mise_toml(projects.render("basic"))["tasks"]
    assert tasks["lint:deadcode"]["run"] == "uv run vulture"
    assert "lint:deadcode" in refs(tasks["lint"])


def test_rendered_whitelist_file_exists(projects: ProjectRegistry):
    assert (projects.render("basic") / "whitelist_vulture.py").is_file()


def test_prek_declares_vulture_hook():
    config = load_toml(TEMPLATE_ROOT / "templates" / "prek.toml")
    hooks = {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}
    assert "vulture" in hooks
    hook = hooks["vulture"]
    assert hook["entry"] == "mise run lint:deadcode"
    assert hook.get("pass_filenames") is False
    assert hook.get("always_run") is True


def test_root_mirrors_template_deadcode_gate():
    root_tasks = load_toml(TEMPLATE_ROOT / "mise.toml")["tasks"]
    assert root_tasks["lint:deadcode"]["run"] == "uv run vulture"
    assert "lint:deadcode" in refs(root_tasks["lint"])
    root_pyproject = load_toml(TEMPLATE_ROOT / "pyproject.toml")
    assert "vulture>=2.16" in root_pyproject["dependency-groups"]["dev"]
    assert root_pyproject["tool"]["vulture"]["min_confidence"] == 60
