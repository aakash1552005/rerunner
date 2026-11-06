"""Unit tests for standalone HTML cost & savings report generator."""

from __future__ import annotations

from pathlib import Path
from rerunner.reports import export_cost_html_report, generate_cost_html_report


def test_generate_cost_html_report_contains_metrics() -> None:
    html = generate_cost_html_report(
        cassette_count=5,
        total_steps=42,
        total_http=30,
        total_tools=12,
        total_tokens=150000,
        prompt_tokens=100000,
        completion_tokens=50000,
        estimated_cost_usd=0.75,
        latency_sec=14.5,
        target_label="tests/cassettes",
    )

    assert "<!DOCTYPE html>" in html
    assert "Rerunner Replay Savings Report" in html
    assert "$0.7500" in html
    assert "150,000" in html
    assert "100,000" in html
    assert "50,000" in html
    assert "~14.5s" in html
    assert "tests/cassettes" in html
    assert "42" in html
    assert "30" in html
    assert "12" in html
    # Self-contained: check that no external CDN links are present
    assert "https://cdn." not in html
    assert "https://cdnjs." not in html
    assert "https://fonts.googleapis.com" not in html


def test_export_cost_html_report_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "report.html"
    res = export_cost_html_report(
        output_path=out,
        cassette_count=1,
        total_steps=10,
        total_http=8,
        total_tools=2,
        total_tokens=5000,
        prompt_tokens=4000,
        completion_tokens=1000,
        estimated_cost_usd=0.025,
        latency_sec=3.2,
    )

    assert res == out
    assert out.exists()
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in text
    assert "$0.0250" in text
