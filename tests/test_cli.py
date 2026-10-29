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
