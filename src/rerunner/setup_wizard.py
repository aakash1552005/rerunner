"""One-command MCP setup wizard for Claude Code, Cursor, and Codex."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_CLIENTS = ("claude-project", "claude", "cursor", "codex")


@dataclass(frozen=True)
class SetupAction:
    """Outcome for configuring a single agent client target."""

    client: str
    path: Path
    status: str  # "created" | "updated" | "unchanged" | "planned"
    backup_path: Path | None = None


def build_mcp_server_entry(command: str = "rerunner") -> dict[str, Any]:
    """Return the canonical MCP stdio server entry for Rerunner."""
    return {
        "command": command,
        "args": ["mcp"],
    }


def _resolve_client_path(
    client: str,
    *,
    project_dir: Path,
    home_dir: Path,
) -> Path:
    if client == "claude-project":
        return project_dir / ".mcp.json"
    if client == "claude":
        return home_dir / ".claude.json"
    if client == "cursor":
        return project_dir / ".cursor" / "mcp.json"
    if client == "codex":
        return project_dir / ".codex" / "config.toml"
    raise ValueError(
        f"Unsupported client '{client}'. Supported clients: {', '.join(SUPPORTED_CLIENTS)}"
    )


def _merge_json_mcp_config(
    target_path: Path,
    server_entry: dict[str, Any],
    *,
    dry_run: bool,
    backup: bool,
) -> tuple[str, Path | None]:
    existing_text: str | None = None
    data: dict[str, Any] = {}

    if target_path.exists():
        existing_text = target_path.read_text(encoding="utf-8")
        if existing_text.strip():
            loaded = json.loads(existing_text)
            if not isinstance(loaded, dict):
                raise ValueError(
                    f"Expected JSON object in {target_path}, found {type(loaded).__name__}"
                )
            data = loaded

    mcp_servers = data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
    elif not isinstance(mcp_servers, dict):
        raise ValueError(f"Expected 'mcpServers' object in {target_path}")

    current = mcp_servers.get("rerunner")
    if current == server_entry and target_path.exists():
        return "unchanged", None

    if dry_run:
        return "planned", None

    mcp_servers["rerunner"] = server_entry
    data["mcpServers"] = mcp_servers
    rendered = json.dumps(data, indent=2) + "\n"

    backup_path: Path | None = None
    if target_path.exists() and backup:
        backup_path = Path(f"{target_path}.bak")
        shutil.copy2(target_path, backup_path)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(rendered, encoding="utf-8")
    return ("updated" if existing_text is not None else "created"), backup_path


def _merge_codex_toml_config(
    target_path: Path,
    server_entry: dict[str, Any],
    *,
    dry_run: bool,
    backup: bool,
) -> tuple[str, Path | None]:
    existing_text = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
    cmd_json = json.dumps(server_entry["command"])
    args_json = json.dumps(server_entry["args"])
    section_block = f"[mcp_servers.rerunner]\ncommand = {cmd_json}\nargs = {args_json}\n"

    if "[mcp_servers.rerunner]" in existing_text:
        # Check whether the existing block already matches
        lines = existing_text.splitlines()
        start_idx = next(
            i for i, line in enumerate(lines) if line.strip() == "[mcp_servers.rerunner]"
        )
        end_idx = len(lines)
        for i in range(start_idx + 1, len(lines)):
            if lines[i].strip().startswith("["):
                end_idx = i
                break
        current_block = "\n".join(lines[start_idx:end_idx]).strip() + "\n"
        if current_block == section_block:
            return "unchanged", None
        if dry_run:
            return "planned", None
        updated_lines = (
            lines[:start_idx] + section_block.rstrip("\n").splitlines() + lines[end_idx:]
        )
        rendered = "\n".join(updated_lines).rstrip() + "\n"
        status = "updated"
    else:
        if dry_run:
            return "planned", None
        prefix = existing_text.rstrip()
        rendered = f"{prefix}\n\n{section_block}" if prefix else section_block
        status = "updated" if existing_text else "created"

    backup_path: Path | None = None
    if target_path.exists() and backup:
        backup_path = Path(f"{target_path}.bak")
        shutil.copy2(target_path, backup_path)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(rendered, encoding="utf-8")
    return status, backup_path


def parse_clients(raw_clients: str | list[str]) -> list[str]:
    """Normalize comma-separated client names or 'all' into validated target names."""
    if isinstance(raw_clients, str):
        tokens = [part.strip().lower() for part in raw_clients.split(",") if part.strip()]
    else:
        tokens = [part.strip().lower() for part in raw_clients if part.strip()]

    if not tokens or tokens == ["all"]:
        return list(SUPPORTED_CLIENTS)

    resolved: list[str] = []
    for tok in tokens:
        if tok == "all":
            return list(SUPPORTED_CLIENTS)
        if tok not in SUPPORTED_CLIENTS:
            raise ValueError(
                f"Unsupported client '{tok}'. Choose from: {', '.join(SUPPORTED_CLIENTS)}, or 'all'."
            )
        if tok not in resolved:
            resolved.append(tok)
    return resolved


def configure_clients(
    clients: str | list[str] = "claude-project",
    *,
    project_dir: Path | None = None,
    home_dir: Path | None = None,
    command: str = "rerunner",
    dry_run: bool = False,
    backup: bool = True,
) -> list[SetupAction]:
    """Configure Rerunner's MCP server across one or more coding-agent client configs."""
    resolved_project = (project_dir or Path.cwd()).resolve()
    resolved_home = (home_dir or Path.home()).resolve()
    selected = parse_clients(clients)
    server_entry = build_mcp_server_entry(command=command)

    actions: list[SetupAction] = []
    for client in selected:
        target = _resolve_client_path(client, project_dir=resolved_project, home_dir=resolved_home)
        if client == "codex":
            status, backup_path = _merge_codex_toml_config(
                target, server_entry, dry_run=dry_run, backup=backup
            )
        else:
            status, backup_path = _merge_json_mcp_config(
                target, server_entry, dry_run=dry_run, backup=backup
            )
        actions.append(
            SetupAction(client=client, path=target, status=status, backup_path=backup_path)
        )
    return actions
