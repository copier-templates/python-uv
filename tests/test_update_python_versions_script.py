"""Unit tests for `scripts/maintainer/update_python_versions.py` (network stubbed, never online)."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import yaml
from update_python_versions import BEGIN_MARKER, END_MARKER, main, parse_releases, update_copier_yaml

SAMPLE_COPIER_YAML = f"""\
project_name:
    type: str

project_type:
    type: str
    default: package

python_version:
    type: str
    choices:
        {BEGIN_MARKER}
        "3.10": "3.10"
        {END_MARKER}
    default: "3.12"

github_integration:
    type: bool
    default: true
"""

# endoflife.date-shaped records: old cycles, an unreleased cycle (`latest` empty) and a duplicate.
RELEASE_RECORDS = [
    {"cycle": "2.7", "latest": "2.7.18"},
    {"cycle": "3.8", "latest": "3.8.20"},
    {"cycle": "3.11", "latest": "3.11.9"},
    {"cycle": "3.12", "latest": "3.12.7"},
    {"cycle": "3.13", "latest": "3.13.0"},
    {"cycle": "3.14", "latest": "3.14.0"},
    {"cycle": "3.15", "latest": ""},
    {"cycle": "3.12", "latest": "3.12.7"},
]
EXPECTED_VERSIONS = ["3.14", "3.13", "3.12"]


def _serve(monkeypatch: pytest.MonkeyPatch, records: list[dict[str, Any]]) -> None:
    """Serve a canned endoflife.date payload so `main()` never touches the network."""
    response = io.BytesIO(json.dumps(records).encode())
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: response)


def _fail_fetch(*_args: object, **_kwargs: object) -> None:
    raise urllib.error.URLError("boom")


def _run_main(monkeypatch: pytest.MonkeyPatch, target: Path) -> int:
    monkeypatch.setattr(sys, "argv", ["update_python_versions.py", str(target)])
    return main()


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        (RELEASE_RECORDS, EXPECTED_VERSIONS),
        (list(reversed(RELEASE_RECORDS)), EXPECTED_VERSIONS),
        ([], []),
    ],
    ids=["drops-old-and-unreleased", "ignores-input-order", "empty"],
)
def test_parse_releases(records: list[dict[str, Any]], expected: list[str]):
    assert parse_releases(records) == expected


def test_update_copier_yaml_replaces_the_managed_block():
    """The stale block is swapped for the new choices, leaving the rest of the YAML intact."""
    updated = update_copier_yaml(SAMPLE_COPIER_YAML, EXPECTED_VERSIONS)

    parsed = yaml.safe_load(updated)
    assert list(parsed["python_version"]["choices"]) == EXPECTED_VERSIONS
    assert parsed["python_version"]["default"] == "3.12", "sibling keys must survive the rewrite"
    assert parsed["project_type"]["default"] == "package", "surrounding questions must survive the rewrite"
    assert update_copier_yaml(updated, EXPECTED_VERSIONS) == updated, "update must be idempotent"


@pytest.mark.parametrize("marker", [BEGIN_MARKER, END_MARKER], ids=["missing-begin", "missing-end"])
def test_update_copier_yaml_rejects_missing_markers(marker: str):
    """A missing marker means the file was hand-edited: refuse instead of guessing."""
    content = "".join(line for line in SAMPLE_COPIER_YAML.splitlines(keepends=True) if line.strip() != marker)
    with pytest.raises(ValueError):
        update_copier_yaml(content, EXPECTED_VERSIONS)


def test_main_rewrites_the_target_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    _serve(monkeypatch, RELEASE_RECORDS)

    assert _run_main(monkeypatch, target) == 0
    assert list(yaml.safe_load(target.read_text())["python_version"]["choices"]) == EXPECTED_VERSIONS


def test_main_rejects_missing_required_choice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """A rewrite that orphans `default` must be refused, leaving the file untouched.

    Upstream dropping the `3.12` cycle would otherwise rewrite `choices` to
    `3.14`/`3.13` while `default` stays `3.12` — an invalid Copier question.
    """
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    _serve(monkeypatch, [record for record in RELEASE_RECORDS if record["cycle"] != "3.12"])

    assert _run_main(monkeypatch, target) != 0
    assert target.read_text() == SAMPLE_COPIER_YAML


def test_main_reports_fetch_failure_without_touching_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "copier.yaml"
    target.write_text(SAMPLE_COPIER_YAML)
    monkeypatch.setattr(urllib.request, "urlopen", _fail_fetch)

    assert _run_main(monkeypatch, target) != 0
    assert target.read_text() == SAMPLE_COPIER_YAML
