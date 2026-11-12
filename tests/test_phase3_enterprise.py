"""Tests for Phase 3: model pricing, volatile JSON field ignoring, cassette merge, and auto-naming."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner
from rerunner.cassette import Cassette
from rerunner.cassette_ops import estimate_entry_cost_usd, merge_cassettes, resolve_model_pricing
from rerunner.cli import app
from rerunner.matcher import compute_request_key, request_matches
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.pytest_plugin import _resolve_pytest_cassette_and_mode, default_cassette_path_for_node

runner = CliRunner()


def _make_http_entry(
    step: int, model: str, prompt_text: str, prompt_tok: int, comp_tok: int
) -> CassetteEntry:
    req_body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt_text}]})
    url = "https://api.openai.com/v1/chat/completions"
    return CassetteEntry(
        step=step,
        entry_type="http",
        request=RecordedRequest(
            method="POST",
            url=url,
            headers={"content-type": "application/json"},
            body=req_body,
            request_key=compute_request_key("POST", url, req_body),
        ),
        response=RecordedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps(
                {
                    "model": model,
                    "usage": {
                        "prompt_tokens": prompt_tok,
                        "completion_tokens": comp_tok,
                        "total_tokens": prompt_tok + comp_tok,
                    },
                }
            ),
        ),
    )


def test_model_aware_pricing_and_cost_json(tmp_path: Path) -> None:
    assert resolve_model_pricing("gpt-4o-mini-2024-07-18") == (0.15, 0.60)
    assert resolve_model_pricing("claude-3-5-sonnet-20241022") == (3.00, 15.00)

    cheap = estimate_entry_cost_usd(1_000_000, 1_000_000, 2_000_000, model="gpt-4o-mini")
    expensive = estimate_entry_cost_usd(1_000_000, 1_000_000, 2_000_000, model="claude-3-5-sonnet")
    assert cheap == pytest.approx(0.75)
    assert expensive == pytest.approx(18.0)

    c_path = tmp_path / "models.jsonl"
    c = Cassette(c_path)
    c.append_entry(_make_http_entry(1, "gpt-4o-mini", "fast", 500_000, 500_000))
    c.append_entry(_make_http_entry(2, "claude-3-5-sonnet-20241022", "smart", 500_000, 500_000))
    c.save()

    res = runner.invoke(app, ["cost", str(c_path), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["estimated_cost_usd"] == pytest.approx(9.375, rel=1e-4)
    assert "gpt-4o-mini" in data["by_model"]
    assert "claude-3-5-sonnet-20241022" in data["by_model"]


def test_volatile_json_field_ignoring(monkeypatch: pytest.MonkeyPatch) -> None:
    url = "https://api.openai.com/v1/chat/completions"
    body_a = json.dumps(
        {
            "model": "gpt-4o",
            "timestamp": "2026-01-01T00:00:00Z",
            "metadata": {"request_id": "req-111"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    )
    body_b = json.dumps(
        {
            "model": "gpt-4o",
            "timestamp": "2026-11-12T15:00:00Z",
            "metadata": {"request_id": "req-999"},
            "messages": [{"role": "user", "content": "hello"}],
        }
    )

    assert compute_request_key("POST", url, body_a) != compute_request_key("POST", url, body_b)
    assert compute_request_key(
        "POST", url, body_a, ignore_fields=["timestamp", "metadata.request_id"]
    ) == compute_request_key(
        "POST", url, body_b, ignore_fields=["timestamp", "metadata.request_id"]
    )

    recorded = RecordedRequest(
        method="POST",
        url=url,
        body=body_a,
        request_key=compute_request_key("POST", url, body_a),
    )
    assert request_matches(
        recorded,
        "POST",
        url,
        body_b,
        ignore_fields=["timestamp", "metadata.request_id"],
    )

    monkeypatch.setenv("RERUNNER_IGNORE_FIELDS", "timestamp,metadata.request_id")
    assert compute_request_key("POST", url, body_a) == compute_request_key("POST", url, body_b)


def test_merge_cassettes_and_cli_deduplicate(tmp_path: Path) -> None:
    c1_path = tmp_path / "part1.jsonl"
    c2_path = tmp_path / "part2.jsonl"

    c1 = Cassette(c1_path)
    c1.append_entry(_make_http_entry(1, "gpt-4o", "step one", 10, 5))
    c1.append_entry(
        CassetteEntry(
            step=2, entry_type="side_effect", side_effect_name="fetch", side_effect_args=["a"]
        )
    )
    c1.save()

    c2 = Cassette(c2_path)
    c2.append_entry(_make_http_entry(1, "gpt-4o", "step one", 10, 5))  # duplicate
    c2.append_entry(_make_http_entry(2, "gpt-4o", "step two", 20, 10))
    c2.save()

    merged_all = tmp_path / "merged_all.jsonl"
    summary_all = merge_cassettes([c1_path, c2_path], merged_all, deduplicate=False)
    assert summary_all["merged_steps"] == 4
    assert summary_all["deduplicated_removed"] == 0
    loaded_all = Cassette.load(merged_all, verify_integrity=True)
    assert [e.step for e in loaded_all.entries] == [1, 2, 3, 4]

    merged_dedup = tmp_path / "merged_dedup.jsonl"
    cli_res = runner.invoke(
        app,
        ["merge", str(c1_path), str(c2_path), "--output", str(merged_dedup), "--deduplicate"],
    )
    assert cli_res.exit_code == 0
    loaded_dedup = Cassette.load(merged_dedup, verify_integrity=True)
    assert [e.step for e in loaded_dedup.entries] == [1, 2, 3]


def test_auto_per_test_cassette_naming() -> None:
    fake_node: Any = SimpleNamespace(
        nodeid="tests/agents/test_checkout.py::TestCart::test_flow[fast]",
        name="test_flow[fast]",
        get_closest_marker=lambda _name: SimpleNamespace(args=(), kwargs={}),
    )
    derived = default_cassette_path_for_node(fake_node)
    assert derived == "tests/cassettes/tests_agents_test_checkout/TestCart_test_flow_fast.jsonl"

    fake_request: Any = SimpleNamespace(
        node=fake_node,
        config=SimpleNamespace(getoption=lambda _opt, default=None: default),
    )
    cassette_path, mode_val, auto_patch = _resolve_pytest_cassette_and_mode(fake_request)
    assert cassette_path == derived
    assert mode_val == "auto"
    assert auto_patch is True
