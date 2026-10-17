"""Integration tests for CLI help screens and version flag (Issue #24)."""

from __future__ import annotations

from typer.testing import CliRunner
from rerunner.cli import app

runner = CliRunner()


def test_cli_help() -> None:
    """Invoking `rerunner --help` exits with code 0 and lists subcommands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Deterministic flight recorder" in result.output
    assert "inspect" in result.output
    assert "verify" in result.output
    assert "export-otel" in result.output


def test_cli_version() -> None:
    """Invoking `rerunner --version` or `-v` displays the version number."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "rerunner version" in result.output

    result_short = runner.invoke(app, ["-v"])
    assert result_short.exit_code == 0
    assert "rerunner version" in result_short.output


def test_cli_subcommands_help() -> None:
    """Invoking `--help` on individual subcommands renders option flags and usage."""
    for subcommand in ["inspect", "verify", "export-otel"]:
        result = runner.invoke(app, [subcommand, "--help"])
        assert result.exit_code == 0
        assert f"Usage: rerunner {subcommand}" in result.output
