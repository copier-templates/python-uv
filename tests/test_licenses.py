"""License choices, `templates/licenses/` partials, SPDX identifiers and rendered license fields in lockstep."""

from __future__ import annotations

import jinja2
import pytest
from _projects import TEMPLATE_ROOT, ProjectRegistry, copier_config

SPDX_BY_LICENSE = {
    "mit": "MIT",
    "apache-2.0": "Apache-2.0",
    "gpl-2.0": "GPL-2.0-only",
    "gpl-3.0": "GPL-3.0-only",
    "lgpl-2.0": "LGPL-2.0-only",
    "lgpl-2.1": "LGPL-2.1-only",
    "lgpl-3.0": "LGPL-3.0-only",
    "mpl-2.0": "MPL-2.0",
}
LICENSES_DIR = TEMPLATE_ROOT / "templates" / "licenses"


def test_license_choices_match_partials_and_spdx_table():
    choices = set(copier_config()["license_type"]["choices"].values())
    assert choices == set(SPDX_BY_LICENSE) == {p.name for p in LICENSES_DIR.iterdir()}


@pytest.mark.parametrize(("license_type", "spdx"), SPDX_BY_LICENSE.items())
def test_license_partial_and_spdx_default(license_type: str, spdx: str):
    """Each partial ends with exactly one newline (else `end-of-file-fixer` fails every licensed project)."""
    content = (LICENSES_DIR / license_type).read_bytes()
    assert content.endswith(b"\n") and not content.endswith(b"\n\n")

    default = copier_config()["license_spdx"]["default"]
    env = jinja2.Environment(autoescape=False)  # noqa: S701 (plain-text YAML default)
    assert env.from_string(default).render(license_type=license_type) == spdx


def test_rendered_license_fields_follow_selection(projects: ProjectRegistry):
    licensed = projects.render("python313-licensed")
    selected = licensed.pyproject()["project"]
    assert selected["license"] == SPDX_BY_LICENSE[str(licensed.answer("license_type"))]
    assert selected["license-files"] == ["LICENSE"]

    unselected = projects.render("basic").pyproject()["project"]
    assert not {"license", "license-files"} & set(unselected)


def test_rendered_license_is_hook_clean(projects: ProjectRegistry):
    """Regression: the include tag once appended its own newline, so `end-of-file-fixer` failed CI."""
    content = (projects.render("python313-licensed").path / "LICENSE").read_bytes()
    assert content.endswith(b"\n") and not content.endswith(b"\n\n"), "LICENSE must end with exactly one newline"
    offenders = [n for n, line in enumerate(content.decode("utf-8").split("\n"), 1) if line != line.rstrip(" \t")]
    assert not offenders, f"LICENSE has trailing whitespace on lines {offenders}"
