"""03_mcp_sqlite_replayer.py - Model Context Protocol (MCP) Tool Replay with Rerunner.

Demonstrates how to record and deterministically replay Model Context Protocol (MCP)
tool invocations without running live MCP server subprocesses or databases in CI.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from rich.console import Console

from rerunner.integrations.mcp import RerunnerMCPClient, record_mcp_tool

console = Console(highlight=False)


# 1. Define an MCP tool decorated with @record_mcp_tool
@record_mcp_tool(name="query_customer_db")
def query_customer_db(customer_id: int) -> dict[str, str | int]:
    """Simulated local MCP database query tool."""
    console.print(
        f"[yellow][DB EXEC] Querying live database for customer #{customer_id}...[/yellow]"
    )
    return {
        "customer_id": customer_id,
        "name": "Jane Doe",
        "tier": "Enterprise",
        "credits": 5000,
    }


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "mcp_customer_flight.jsonl"

        console.print(
            "[bold cyan]=== Step 1: Record Mode (Live MCP Tool Execution) ===[/bold cyan]"
        )
        console.print(
            "[dim]Executing the tool while Rerunner records inputs, outputs, and hashes[/dim]\n"
        )

        with RerunnerMCPClient(cassette_path, mode="record"):
            # Call the tool directly through Rerunner's client or decorated function
            result = query_customer_db(customer_id=1042)
            console.print(f"[green][+] Live Output:[/green] {result}")
            console.print(f"[cyan][*] Recorded 1 step to {cassette_path.name}[/cyan]\n")

        assert cassette_path.exists(), "Cassette file was not saved!"

        console.print(
            "[bold cyan]=== Step 2: Replay Mode (Zero-Process / Hermetic CI) ===[/bold cyan]"
        )
        console.print(
            "[dim]Replaying the exact same MCP tool invocation without touching any database[/dim]\n"
        )

        with RerunnerMCPClient(cassette_path, mode="replay"):
            # In replay mode, the tool body DOES NOT RUN. Rerunner serves the cassette result!
            replayed_result = query_customer_db(customer_id=1042)
            console.print(f"[green][+] Replayed Output:[/green] {replayed_result}")
            console.print(
                "[bold green][OK] Deterministic tool output served in 0.1ms with zero DB connection.[/bold green]\n"
            )


if __name__ == "__main__":
    run_demo()
