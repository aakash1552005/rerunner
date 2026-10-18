"""Tests verifying rerunner CLI inspect and diff commands."""

from __future__ import annotations

from pathlib import Path
from typer.testing import CliRunner

from rerunner import Cassette
from rerunner.cli import app
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

runner = CliRunner(env={"COLUMNS": "200"})


def test_cli_inspect_command(tmp_path: Path) -> None:
    cassette_file = tmp_path / "inspect_test.zst"
    cassette = Cassette(cassette_file)

    # Add HTTP entry with tokens
    req = RecordedRequest(method="POST", url="https://api.openai.com/v1/chat", request_key="key1")
    resp = RecordedResponse(
        status_code=200,
        body='{"choices": [], "usage": {"total_tokens": 150}}',
        is_streaming=True,
        chunks=["data: chunk1", "data: chunk2"],
        chunk_delays_ms=[12.5, 15.0],
    )
    cassette.append(CassetteEntry(step=1, entry_type="http", request=req, response=resp))

    # Add Tool entry
    cassette.append(
        CassetteEntry(
            step=2,
            entry_type="tool",
            side_effect_name="query_database",
            side_effect_args=["SELECT 1"],
            side_effect_result={"ok": True},
        )
    )
    cassette.save()

    result = runner.invoke(app, ["inspect", str(cassette_file)])
    assert result.exit_code == 0
    assert "POST" in result.output
    assert "api.openai.com" in result.output
    assert "query_database(...)" in result.output
    assert "150" in result.output
    assert "27.5ms" in result.output


def test_cli_diff_identical_cassettes(tmp_path: Path) -> None:
    cassette_a = tmp_path / "a.jsonl"
    cassette_b = tmp_path / "b.jsonl"

    c1 = Cassette(cassette_a)
    req = RecordedRequest(method="GET", url="https://api.example.com", request_key="k1")
    resp = RecordedResponse(status_code=200, body='{"usage": {"total_tokens": 50}}')
    c1.append(CassetteEntry(step=1, entry_type="http", request=req, response=resp))
    c1.save()

    c2 = Cassette(cassette_b)
    c2.append(CassetteEntry(step=1, entry_type="http", request=req, response=resp))
    c2.save()

    result = runner.invoke(app, ["diff", str(cassette_a), str(cassette_b)])
    assert result.exit_code == 0
    assert "structurally identical" in result.output

    # With fail-on-drift
    result_fail = runner.invoke(app, ["diff", str(cassette_a), str(cassette_b), "--fail-on-drift"])
    assert result_fail.exit_code == 0


def test_cli_diff_with_drift_and_fail_on_drift(tmp_path: Path) -> None:
    cassette_a = tmp_path / "drift_a.jsonl"
    cassette_b = tmp_path / "drift_b.jsonl"

    c1 = Cassette(cassette_a)
    req_a = RecordedRequest(method="GET", url="https://api.example.com/v1", request_key="k1")
    resp_a = RecordedResponse(status_code=200, body='{"usage": {"total_tokens": 100}}')
    c1.append(CassetteEntry(step=1, entry_type="http", request=req_a, response=resp_a))
    c1.save()

    c2 = Cassette(cassette_b)
    req_b = RecordedRequest(method="GET", url="https://api.example.com/v2", request_key="k2")
    resp_b = RecordedResponse(status_code=200, body='{"usage": {"total_tokens": 150}}')
    c2.append(CassetteEntry(step=1, entry_type="http", request=req_b, response=resp_b))
    # Extra step in b
    c2.append(
        CassetteEntry(
            step=2,
            entry_type="tool",
            side_effect_name="search",
            side_effect_args=["query"],
            side_effect_result="found",
        )
    )
    c2.save()

    # Without --fail-on-drift: prints drift info, exits 0
    result = runner.invoke(app, ["diff", str(cassette_a), str(cassette_b)])
    assert result.exit_code == 0
    assert "Token Delta" in result.output
    assert "+50 tokens" in result.output

    # With --fail-on-drift: exits 1
    result_fail = runner.invoke(app, ["diff", str(cassette_a), str(cassette_b), "--fail-on-drift"])
    assert result_fail.exit_code == 1
    assert "Structural drift detected" in result_fail.output
