"""Integration tests for the Rerunner CLI."""

from __future__ import annotations

from pathlib import Path
from typer.testing import CliRunner
from rerunner.cli import app
from rerunner.session import record

runner = CliRunner()


def test_cli_inspect_and_verify(temp_cassette_path: Path) -> None:
    # 1. Create a dummy recorded cassette
    with record(temp_cassette_path) as session:
        _ = session.get_client()
        # Dummy call or empty cassette
        pass

    # 2. Test inspect command
    result = runner.invoke(app, ["inspect", str(temp_cassette_path)])
    assert result.exit_code == 0
    assert "Rerunner Cassette Summary" in result.output

    # 3. Test verify command on clean cassette
    result_verify = runner.invoke(app, ["verify", str(temp_cassette_path)])
    assert result_verify.exit_code == 0
    assert "Cryptographic integrity verified successfully" in result_verify.output
    assert "Security scan passed" in result_verify.output
    assert "Cassette Verification & Savings Summary" in result_verify.output

    # 4. Test export-otel command
    out_otel = temp_cassette_path.with_suffix(".otel.json")
    result_otel = runner.invoke(
        app, ["export-otel", str(temp_cassette_path), "--output", str(out_otel)]
    )
    assert result_otel.exit_code == 0
    assert "Successfully exported cassette to OpenTelemetry" in result_otel.output
    assert out_otel.exists()


def test_cli_verify_detects_leaked_secret(tmp_path: Path) -> None:
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    leaky_cassette = tmp_path / "leaky.jsonl"
    c = Cassette(leaky_cassette)
    c.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={
                    "authorization": f"Bearer {'sk-proj-' + '1234567890abcdef1234567890abcdef12345'}"
                },
                body='{"prompt": "hello"}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body='{"reply": "hi"}',
            ),
        )
    )
    c.save()

    # Verify fails in strict mode
    result = runner.invoke(app, ["verify", str(leaky_cassette), "--strict"])
    assert result.exit_code == 1
    assert "SECURITY WARNING" in result.output
    assert (
        "Found unredacted pattern" in result.output
        or "Unredacted sensitive header" in result.output
    )

    # Verify passes in non-strict mode with warning
    result_non_strict = runner.invoke(app, ["verify", str(leaky_cassette), "--no-strict"])
    assert result_non_strict.exit_code == 0
    assert "SECURITY WARNING" in result_non_strict.output


def test_cli_tui_render(temp_cassette_path: Path) -> None:
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    cassette = Cassette(temp_cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST", url="https://api.openai.com/v1/chat/completions", headers={}
            ),
            response=RecordedResponse(
                status_code=200, headers={}, body='{"usage": {"total_tokens": 42}}'
            ),
        )
    )
    cassette.save()

    result = runner.invoke(app, ["tui", str(temp_cassette_path)])
    assert result.exit_code == 0
    assert "RERUNNER AGENT FLIGHT DECK" in result.output
    assert "Step 1" in result.output
    assert "Tokens Replayed: 42" in result.output


def test_cli_stats_table_and_json(temp_cassette_path: Path) -> None:
    import json
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    cassette = Cassette(temp_cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={},
                body='{"messages": [{"role": "user", "content": "hello"}]}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body='{"choices": [{"message": {"content": "world"}}]}',
            ),
        )
    )
    cassette.append(
        CassetteEntry(
            step=2,
            entry_type="side_effect",
            side_effect_name="fetch_user",
            side_effect_args=[123],
            side_effect_result={"name": "Alice"},
        )
    )
    cassette.save()

    # 1. Default table output
    result_table = runner.invoke(app, ["stats", str(temp_cassette_path)])
    assert result_table.exit_code == 0
    assert "CI Replay Efficiency & Savings" in result_table.output
    assert "Total Recorded Steps" in result_table.output

    # 2. JSON output with --json flag
    result_json = runner.invoke(app, ["stats", str(temp_cassette_path), "--json"])
    assert result_json.exit_code == 0
    data = json.loads(result_json.output)
    assert data["cassette"] == str(temp_cassette_path)
    assert data["total_steps"] == 2
    assert data["http_steps"] == 1
    assert data["side_effect_steps"] == 1
    assert data["estimated_tokens_saved"] > 0
    assert "estimated_cost_saved_usd" in data
    assert "estimated_time_saved_seconds" in data
    assert "metadata" in data
    assert data["metadata"]["format_version"] == "1.1.0"

    # 3. Short flag -j
    result_short = runner.invoke(app, ["stats", str(temp_cassette_path), "-j"])
    assert result_short.exit_code == 0
    data_short = json.loads(result_short.output)
    assert data_short == data


def test_cli_cost_export_html(tmp_path: Path) -> None:
    from rerunner.cassette import Cassette
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    cass_file = tmp_path / "test_cost.jsonl"
    cass = Cassette(cass_file)
    cass.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST", url="https://api.openai.com/v1/chat/completions", headers={}
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body='{"usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200}}',
            ),
        )
    )
    cass.save()

    html_out = tmp_path / "reports" / "savings.html"
    result = runner.invoke(app, ["cost", str(cass_file), "--export-html", str(html_out)])
    assert result.exit_code == 0
    assert "Standalone HTML savings report exported to" in result.output
    assert html_out.exists()

    content = html_out.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Rerunner Replay Savings Report" in content
    assert "200" in content
    assert "120" in content
    assert "80" in content
    assert "Detailed Replay vs Live API Comparison" in content
