"""Answers-file omission contract for hidden computed facts and for facts removed by always-on tooling."""

from __future__ import annotations

import re

from _projects import ProjectRegistry

# Hidden `when: false` facts in copier.yaml: Copier must keep them out of the answers file.
COMPUTED_FACT_KEYS = (
    "is_app",
    "is_lib",
    "is_package",
    # Removed facts and question: must never reappear in the answers file.
    "dev_deps",
    "dev_dep_names",
    "verify_ci",
    "with_ruff",
    "with_pytest",
    "with_pytest_cov",
)


def test_answers_omit_computed_render_facts(projects: ProjectRegistry) -> None:
    """`.copier-answers.yml` must not record any hidden computed render fact.

    A leaked fact would be replayed verbatim by `copier update` instead of being re-derived.
    Names are matched as whole keys so `dev_deps` cannot trip on the legitimate `extra_dev_deps` answer.
    """
    answers_text = (projects.render("basic") / ".copier-answers.yml").read_text()
    for name in COMPUTED_FACT_KEYS:
        assert not re.search(rf"^{name}:", answers_text, re.MULTILINE), f"{name!r} leaked into answers:\n{answers_text}"
