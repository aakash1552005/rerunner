"""Tests for the Rerunner one-command coding-agent MCP setup wizard."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner
from rerunner.cli import app
from rerunner.setup_wizard import configure_clients, parse_clients

runner = CliRunner()


def test_parse_clients_validation() -> None:
    assert parse_clients("all") == ["claude-project", "claude", "cursor", "codex"]
    assert parse_clients("cursor, claude-project, cursor") == ["cursor", "claude-project"]


def test_configure_clients_creates_merges_backs_up_and_is_idempotent(tmp_path: Path) -> None:
    project_dir = tmp_path / "repo"
    home_dir = tmp_path / "home"
    project_dir.mkdir()
    home_dir.mkdir()

    # Pre-populate existing .mcp.json and .codex/config.toml to verify non-destructive merge + .bak
    mcp_json = project_dir / ".mcp.json"
    mcp_json.write_text(
        json.dumps({"mcpServers": {"other": {"command": "npx", "args": ["other-mcp"]}}}),
        encoding="utf-8",
    )
    codex_dir = project_dir / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text(
        '[mcp_servers.existing]\ncommand = "echo"\nargs = ["hi"]\n',
        encoding="utf-8",
    )

    actions = configure_clients(
        "all",
        project_dir=project_dir,
        home_dir=home_dir,
        command="uvx",
    )
    statuses = {a.client: a.status for a in actions}
    assert statuses == {
        "claude-project": "updated",
        "claude": "created",
        "cursor": "created",
        "codex": "updated",
    }

    # Check backup creation on pre-existing files
    assert (project_dir / ".mcp.json.bak").exists()
    assert (codex_dir / "config.toml.bak").exists()

    # Verify JSON configs preserve other servers and add rerunner
    merged_claude = json.loads(mcp_json.read_text(encoding="utf-8"))
    assert "other" in merged_claude["mcpServers"]
    assert merged_claude["mcpServers"]["rerunner"] == {"command": "uvx", "args": ["mcp"]}

    merged_global = json.loads((home_dir / ".claude.json").read_text(encoding="utf-8"))
    assert merged_global["mcpServers"]["rerunner"] == {"command": "uvx", "args": ["mcp"]}

    merged_cursor = json.loads((project_dir / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
    assert merged_cursor["mcpServers"]["rerunner"] == {"command": "uvx", "args": ["mcp"]}

    codex_text = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.existing]" in codex_text
    assert '[mcp_servers.rerunner]\ncommand = "uvx"\nargs = ["mcp"]' in codex_text

    # Re-running is idempotent
    second_run = configure_clients(
        "all",
        project_dir=project_dir,
        home_dir=home_dir,
        command="uvx",
    )
    assert all(a.status == "unchanged" for a in second_run)


def test_configure_clients_dry_run_does_not_write(tmp_path: Path) -> None:
    actions = configure_clients(
        "claude-project,cursor",
        project_dir=tmp_path,
        home_dir=tmp_path,
        dry_run=True,
    )
    assert all(a.status == "planned" for a in actions)
    assert not (tmp_path / ".mcp.json").exists()
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


def test_cli_setup_command_dry_run_abort_and_yes(tmp_path: Path) -> None:
    dry_res = runner.invoke(
        app,
        ["setup", "--clients", "claude-project", "--project-dir", str(tmp_path), "--dry-run"],
    )
    assert dry_res.exit_code == 0
    assert "PLANNED" in dry_res.output
    assert not (tmp_path / ".mcp.json").exists()

    abort_res = runner.invoke(
        app,
        ["setup", "--clients", "claude-project", "--project-dir", str(tmp_path)],
        input="n\n",
    )
    assert abort_res.exit_code == 0
    assert "cancelled" in abort_res.output.lower()
    assert not (tmp_path / ".mcp.json").exists()

    yes_res = runner.invoke(
        app,
        ["setup", "--clients", "claude-project", "--project-dir", str(tmp_path), "--yes"],
    )
    assert yes_res.exit_code == 0
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["rerunner"] == {"command": "rerunner", "args": ["mcp"]}
