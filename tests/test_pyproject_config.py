"""Tests for ``[tool.rerunner]`` defaults in pyproject.toml and their precedence order."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from rerunner.config import (
    config_cassette_dir,
    config_ignore_fields,
    config_mode,
    load_tool_config,
)
from rerunner.matcher import normalize_body
from rerunner.pytest_plugin import default_cassette_path_for_node
from rerunner.session import Session

PYPROJECT_TEMPLATE = """\
[project]
name = "demo"
version = "0.1.0"

[tool.rerunner]
cassette_dir = "{cassette_dir}"
ignore_fields = {ignore_fields}
mode = "{mode}"
"""


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chdir into an isolated project root with no ambient rerunner env vars."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("RERUNNER_MODE", raising=False)
    monkeypatch.delenv("RERUNNER_IGNORE_FIELDS", raising=False)
    monkeypatch.delenv("RERUNNER_CASSETTE_DIR", raising=False)
    return tmp_path


def _write_pyproject(
    root: Path,
    cassette_dir: str = "cfgcassettes",
    ignore_fields: str = '["ts", "request_id"]',
    mode: str = "replay",
) -> None:
    (root / "pyproject.toml").write_text(
        PYPROJECT_TEMPLATE.format(
            cassette_dir=cassette_dir, ignore_fields=ignore_fields, mode=mode
        ),
        encoding="utf-8",
    )


def test_load_tool_config_reads_rerunner_table(project_dir: Path) -> None:
    _write_pyproject(project_dir)

    table = load_tool_config()

    assert table["cassette_dir"] == "cfgcassettes"
    assert table["ignore_fields"] == ["ts", "request_id"]
    assert table["mode"] == "replay"
    assert config_cassette_dir() == "cfgcassettes"
    assert config_ignore_fields() == {"ts", "request_id"}
    assert config_mode() == "replay"


def test_missing_rerunner_table_returns_empty_defaults(project_dir: Path) -> None:
    (project_dir / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

    assert load_tool_config() == {}
    assert config_cassette_dir() is None
    assert config_ignore_fields() == set()
    assert config_mode() is None


def test_invalid_values_are_ignored(project_dir: Path) -> None:
    _write_pyproject(project_dir, cassette_dir="  ", ignore_fields='"a,b"', mode="bogus")

    assert config_cassette_dir() is None
    assert config_ignore_fields() == {"a", "b"}
    assert config_mode() is None


def test_mode_default_comes_from_pyproject(project_dir: Path) -> None:
    _write_pyproject(project_dir, mode="replay")
    cassette = project_dir / "c.jsonl"
    cassette.write_text('{"step": 1}\n', encoding="utf-8")

    session = Session(cassette_path=str(cassette), mode="auto")

    assert session._resolve_mode() == "replay"


def test_mode_precedence_env_over_pyproject(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_pyproject(project_dir, mode="replay")
    cassette = project_dir / "c.jsonl"
    cassette.write_text('{"step": 1}\n', encoding="utf-8")
    monkeypatch.setenv("RERUNNER_MODE", "record")

    session = Session(cassette_path=str(cassette), mode="auto")

    assert session._resolve_mode() == "record"


def test_mode_precedence_explicit_argument_over_pyproject(project_dir: Path) -> None:
    _write_pyproject(project_dir, mode="replay")
    cassette = project_dir / "c.jsonl"
    cassette.write_text('{"step": 1}\n', encoding="utf-8")

    session = Session(cassette_path=str(cassette), mode="fork", fork_step=0)

    assert session._resolve_mode() == "fork"


def test_ignore_fields_default_comes_from_pyproject(project_dir: Path) -> None:
    _write_pyproject(project_dir)

    normalized = normalize_body('{"ts": 123, "request_id": "abc", "keep": 1}')

    assert normalized == '{"keep":1}'


def test_ignore_fields_precedence_env_over_pyproject(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_pyproject(project_dir)
    monkeypatch.setenv("RERUNNER_IGNORE_FIELDS", "other")

    normalized = normalize_body('{"ts": 1, "other": 2, "keep": 3}')

    assert normalized == '{"keep":3,"ts":1}'


def test_ignore_fields_explicit_argument_still_applies(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_pyproject(project_dir)
    monkeypatch.setenv("RERUNNER_IGNORE_FIELDS", "other")

    normalized = normalize_body('{"ts": 1, "other": 2, "keep": 3}', ignore_fields=["ts"])

    assert normalized == '{"keep":3}'


def test_cassette_dir_default_comes_from_pyproject(project_dir: Path) -> None:
    _write_pyproject(project_dir, cassette_dir="cfgcassettes")
    node = SimpleNamespace(nodeid="tests/test_mod.py::test_case", name="test_case")

    path = default_cassette_path_for_node(node)  # type: ignore[arg-type]

    assert path.startswith("cfgcassettes")
    assert path.endswith("test_mod/test_case.jsonl")


def test_cassette_dir_precedence_env_over_pyproject(
    project_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_pyproject(project_dir, cassette_dir="cfgcassettes")
    monkeypatch.setenv("RERUNNER_CASSETTE_DIR", "envcassettes")
    node = SimpleNamespace(nodeid="tests/test_mod.py::test_case", name="test_case")

    path = default_cassette_path_for_node(node)  # type: ignore[arg-type]

    assert path.startswith("envcassettes")
