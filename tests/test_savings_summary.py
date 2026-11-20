"""Unit and integration tests for CI cost & latency savings reporting and [tool.rerunner.pricing]."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rerunner.cassette_ops import (
    estimate_entry_cost_usd,
    extract_detailed_tokens_from_body,
    resolve_model_pricing,
)
from rerunner.cli import app
from rerunner.config import config_pricing
from rerunner.reports import generate_savings_markdown


runner = CliRunner()


def test_config_pricing_parses_list_and_table_formats(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pyproject_content = """\
[project]
name = "demo"
version = "0.1.0"

[tool.rerunner.pricing]
"gpt-4o" = [2.00, 8.00]
"claude-custom" = [1.50, 6.00]

[tool.rerunner.pricing.deepseek-reasoner]
input = 0.55
output = 2.19
"""
    (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    pricing = config_pricing()
    assert pricing["gpt-4o"] == (2.00, 8.00)
    assert pricing["claude-custom"] == (1.50, 6.00)
    assert pricing["deepseek-reasoner"] == (0.55, 2.19)


def test_config_pricing_empty_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert config_pricing() == {}


def test_resolve_model_pricing_with_custom_and_defaults() -> None:
    custom = {
        "my-private-llm": (1.00, 4.00),
        "free-internal-model": (0.00, 0.00),
    }

    # Custom model matched
    assert resolve_model_pricing("my-private-llm", custom_pricing=custom) == (1.00, 4.00)
    assert resolve_model_pricing("free-internal-model-v2", custom_pricing=custom) == (0.00, 0.00)

    # Built-in fallback
    assert resolve_model_pricing("gpt-4o-mini", custom_pricing=custom) == (0.15, 0.60)
    assert resolve_model_pricing("claude-3-5-sonnet", custom_pricing=custom) == (3.00, 15.00)

    # Unknown model fallback
    assert resolve_model_pricing("nonexistent-brand-x", custom_pricing=custom) == (2.50, 10.00)


def test_estimate_entry_cost_free_model_and_zero_tokens() -> None:
    custom = {"free-tier": (0.0, 0.0)}

    # Free model should cost $0.00 regardless of tokens
    cost_free = estimate_entry_cost_usd(
        prompt_tokens=5000,
        completion_tokens=2000,
        total_tokens=7000,
        model="free-tier",
        custom_pricing=custom,
    )
    assert cost_free == 0.0

    # Missing token counts (0 tokens) should cost $0.00
    cost_zero = estimate_entry_cost_usd(
        prompt_tokens=0,
        completion_tokens=0,
        total_tokens=0,
        model="gpt-4o",
    )
    assert cost_zero == 0.0


def test_extract_detailed_tokens_extracts_reasoning() -> None:
    body = json.dumps(
        {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "completion_tokens_details": {
                    "reasoning_tokens": 25,
                },
            }
        }
    )
    tokens = extract_detailed_tokens_from_body(body)
    assert tokens["prompt"] == 100
    assert tokens["completion"] == 50
    assert tokens["total"] == 150
    assert tokens["reasoning"] == 25


def test_generate_savings_markdown_formatting() -> None:
    by_model = {
        "gpt-4o": {"calls": 5, "tokens": 12000, "estimated_cost_usd": 0.084},
        "claude-3-5-sonnet": {"calls": 2, "tokens": 6000, "estimated_cost_usd": 0.060},
    }
    md = generate_savings_markdown(
        cassette_count=3,
        total_steps=10,
        total_http=7,
        total_tools=3,
        total_tokens=18000,
        prompt_tokens=14000,
        completion_tokens=4000,
        estimated_cost_usd=0.144,
        latency_sec=12.5,
        by_model=by_model,
        cache_hit_ratio=100.0,
    )

    assert "### ⚡ Rerunner CI Replay Savings Report" in md
    assert "Cassette Files Analyzed" in md
    assert "Saved ~$0.1440" in md
    assert "~12.5s Faster in CI" in md
    assert "Replay Cache Hit Ratio" in md
    assert "100.0%" in md
    assert "gpt-4o" in md
    assert "claude-3-5-sonnet" in md


def test_cli_savings_command_markdown_and_github_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    cassette_file = tmp_path / "test.jsonl"
    cassette = Cassette(cassette_file)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={},
                body='{"model": "gpt-4o"}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body='{"model": "gpt-4o", "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200}}',
                chunk_delays_ms=[500.0],
            ),
        )
    )
    cassette.save()

    # 1. Test rerunner savings with --markdown
    result = runner.invoke(app, ["savings", str(cassette_file), "--markdown"])
    assert result.exit_code == 0
    assert "### ⚡ Rerunner CI Replay Savings Report" in result.output
    assert "Saved ~$" in result.output

    # 2. Test rerunner savings with --github-summary writing to $GITHUB_STEP_SUMMARY
    summary_file = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    result_ci = runner.invoke(app, ["savings", str(cassette_file), "--github-summary"])
    assert result_ci.exit_code == 0
    assert summary_file.exists()
    content = summary_file.read_text(encoding="utf-8")
    assert "### ⚡ Rerunner CI Replay Savings Report" in content
    assert "gpt-4o" in content


def test_cli_savings_command_json_output(tmp_path: Path) -> None:
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    cassette_file = tmp_path / "test.jsonl"
    cassette = Cassette(cassette_file)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={},
                body='{"model": "gpt-4o"}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body='{"model": "gpt-4o", "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600}}',
                chunk_delays_ms=[200.0],
            ),
        )
    )
    cassette.save()

    result = runner.invoke(app, ["savings", str(cassette_file), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_steps"] == 1
    assert data["total_tokens"] == 600
    assert "estimated_cost_usd" in data
