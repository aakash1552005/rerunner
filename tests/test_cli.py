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

    # 3. Test verify command
    result_verify = runner.invoke(app, ["verify", str(temp_cassette_path)])
    assert result_verify.exit_code == 0
    assert "Cassette integrity verified successfully" in result_verify.output

    # 4. Test export-otel command
    out_otel = temp_cassette_path.with_suffix(".otel.json")
    result_otel = runner.invoke(app, ["export-otel", str(temp_cassette_path), "--output", str(out_otel)])
    assert result_otel.exit_code == 0
    assert "Successfully exported cassette to OpenTelemetry" in result_otel.output
    assert out_otel.exists()

