"""Tests for the `rerunner inspect` --limit and --entry-type filters."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from rerunner.cassette import Cassette
from rerunner.cli import app
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

runner = CliRunner()


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rich folds long table cells at the default 80-column test width; a wide
    # console keeps URLs and function names on one line for the assertions.
    monkeypatch.setenv("COLUMNS", "220")


def _http_entry(step: int, url: str) -> CassetteEntry:
    return CassetteEntry(
        step=step,
        entry_type="http",
        request=RecordedRequest(method="GET", url=url, headers={}, body=""),
        response=RecordedResponse(status_code=200, headers={}, body="ok"),
    )


def _side_effect_entry(step: int, name: str, entry_type: str = "side_effect") -> CassetteEntry:
    return CassetteEntry(
        step=step,
        entry_type=entry_type,  # type: ignore[arg-type]
        side_effect_name=name,
        side_effect_args=[],
        side_effect_kwargs={},
        side_effect_result="done",
    )


def _mixed_cassette(tmp_path: Path) -> Path:
    path = tmp_path / "mixed.jsonl"
    cassette = Cassette(path)
    cassette.append(_http_entry(1, "http://x/1"))
    cassette.append(_side_effect_entry(2, "fn_a"))
    cassette.append(_http_entry(3, "http://x/2"))
    cassette.append(_side_effect_entry(4, "fn_b", entry_type="tool"))
    cassette.append(_http_entry(5, "http://x/3"))
    cassette.append(_side_effect_entry(6, "fn_c"))
    cassette.save()
    return path


def test_inspect_without_filters_shows_everything(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(_mixed_cassette(tmp_path))])
    assert result.exit_code == 0
    assert "Total Steps: 6" in result.output
    assert "Showing:" not in result.output
    for token in ("http://x/1", "http://x/2", "http://x/3", "fn_a", "fn_b", "fn_c"):
        assert token in result.output


def test_inspect_entry_type_http(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["inspect", str(_mixed_cassette(tmp_path)), "--entry-type", "http"]
    )
    assert result.exit_code == 0
    assert "Total Steps: 6" in result.output
    assert "Showing: 3 of 6 steps" in result.output
    assert "http://x/2" in result.output
    assert "fn_a" not in result.output
    assert "fn_b" not in result.output


def test_inspect_entry_type_side_effect(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["inspect", str(_mixed_cassette(tmp_path)), "--entry-type", "side_effect"]
    )
    assert result.exit_code == 0
    assert "Showing: 2 of 6 steps" in result.output
    assert "fn_a" in result.output
    assert "fn_c" in result.output
    assert "fn_b" not in result.output  # fn_b is a tool entry
    assert "http://x/1" not in result.output


def test_inspect_limit(tmp_path: Path) -> None:
    result = runner.invoke(app, ["inspect", str(_mixed_cassette(tmp_path)), "--limit", "2"])
    assert result.exit_code == 0
    assert "Showing: 2 of 6 steps" in result.output
    assert "http://x/1" in result.output
    assert "fn_a" in result.output
    assert "http://x/2" not in result.output


def test_inspect_entry_type_and_limit_combine(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "inspect",
            str(_mixed_cassette(tmp_path)),
            "--entry-type",
            "http",
            "--limit",
            "1",
        ],
    )
    assert result.exit_code == 0
    assert "Showing: 1 of 6 steps" in result.output
    assert "http://x/1" in result.output
    assert "http://x/2" not in result.output


def test_inspect_filter_with_no_matches(tmp_path: Path) -> None:
    path = tmp_path / "http_only.jsonl"
    cassette = Cassette(path)
    cassette.append(_http_entry(1, "http://x/1"))
    cassette.save()
    result = runner.invoke(app, ["inspect", str(path), "--entry-type", "tool"])
    assert result.exit_code == 0
    assert "Showing: 0 of 1 steps" in result.output
    assert "No steps match the active filters." in result.output


def test_inspect_rejects_invalid_entry_type(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["inspect", str(_mixed_cassette(tmp_path)), "--entry-type", "bogus"]
    )
    assert result.exit_code != 0
    assert "invalid entry type" in result.output


def test_inspect_rejects_non_positive_limit(tmp_path: Path) -> None:
    path = _mixed_cassette(tmp_path)
    for bad in ("0", "-3"):
        result = runner.invoke(app, ["inspect", str(path), "--limit", bad])
        assert result.exit_code != 0
        assert "positive integer" in result.output
