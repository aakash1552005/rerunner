"""Command-line interface for Rerunner built with Typer and Rich."""

from __future__ import annotations

import sys
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rerunner.cassette import Cassette
from rerunner.integrity import verify_cassette_integrity
from rerunner.sanitizer import find_sensitive_leaks

app = typer.Typer(
    name="rerunner",
    help="Deterministic flight recorder, replay engine, and CI test runner for AI agents.",
    add_completion=False,
)
console = Console()


@app.command()
def inspect(
    cassette_path: Path = typer.Argument(..., help="Path to a .jsonl or .jsonl.gz cassette file"),
) -> None:
    """Inspect and summarize the contents of a recorded cassette."""
    try:
        cassette = Cassette.load(cassette_path, verify_integrity=False)
    except Exception as exc:
        console.print(f"[bold red]Failed to load cassette:[/] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel(
            f"[bold cyan]File:[/] {cassette_path}\n"
            f"[bold cyan]Format Version:[/] {cassette.metadata.format_version}\n"
            f"[bold cyan]Hash Algorithm:[/] {cassette.metadata.hash_algorithm}\n"
            f"[bold cyan]Total Steps:[/] {len(cassette.entries)}",
            title="[bold green]Rerunner Cassette Summary[/]",
            border_style="green",
        )
    )

    if not cassette.entries:
        console.print("[yellow]Cassette contains no recorded steps.[/]")
        return

    table = Table(title="Recorded Execution Steps", show_header=True, header_style="bold magenta")
    table.add_column("Step", style="dim", width=6)
    table.add_column("Type", width=12)
    table.add_column("Details", justify="left")
    table.add_column("Hash (SHA-256)", style="dim", width=12)

    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            details = f"[bold]{entry.request.method}[/] {entry.request.url} -> [green]{entry.response.status_code}[/]"
        elif entry.entry_type == "side_effect":
            details = f"[bold cyan]Tool:[/] {entry.side_effect_name}(...)"
        else:
            details = "Unknown payload"

        hash_short = f"{entry.entry_hash[:10]}..." if entry.entry_hash else "None"
        table.add_row(str(entry.step), entry.entry_type, details, hash_short)

    console.print(table)


@app.command()
def verify(
    cassette_path: Path = typer.Argument(..., help="Path to the .jsonl cassette file"),
    strict_security: bool = typer.Option(
        True,
        "--strict/--no-strict",
        help="Fail with exit code 1 if unredacted API keys or PII are found.",
    ),
) -> None:
    """Verify cryptographic integrity, scan for leaked API keys/PII, and display savings summary."""
    try:
        cassette = Cassette.load(cassette_path, verify_integrity=False)
    except Exception as exc:
        console.print(f"[bold red]Error loading cassette:[/] {exc}")
        sys.exit(1)

    # 1. Cryptographic SHA-256 integrity check
    is_valid, error = verify_cassette_integrity(cassette.entries)
    if not is_valid:
        console.print(f"[bold red]❌ INTEGRITY FAILURE:[/] {error}")
        sys.exit(1)
    console.print(
        f"[bold green]✔ Cryptographic integrity verified successfully ({len(cassette.entries)} chained steps).[/]"
    )

    # 2. Scan for unredacted API keys and PII leaks
    all_leaks: list[str] = []
    total_chars = 0
    http_steps = 0
    side_effect_steps = 0

    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            http_steps += 1
            total_chars += len(entry.request.body) + len(entry.response.body)
            all_leaks.extend(find_sensitive_leaks(entry.request.headers))
            all_leaks.extend(find_sensitive_leaks(entry.request.body))
            all_leaks.extend(find_sensitive_leaks(entry.response.headers))
            all_leaks.extend(find_sensitive_leaks(entry.response.body))
        elif entry.entry_type == "side_effect":
            side_effect_steps += 1
            if entry.side_effect_args:
                all_leaks.extend(find_sensitive_leaks(entry.side_effect_args))
            if entry.side_effect_result:
                all_leaks.extend(find_sensitive_leaks(entry.side_effect_result))

    all_leaks = list(dict.fromkeys(all_leaks))

    if all_leaks:
        console.print("[bold red]❌ SECURITY WARNING - Leaks Detected:[!]")
        for leak in all_leaks:
            console.print(f"  [red]• {leak}[/]")
        if strict_security:
            console.print("[bold red]Failing verification due to detected unredacted sensitive data.[/]")
            sys.exit(1)
    else:
        console.print("[bold green]✔ Security scan passed: Zero leaked API keys or PII detected.[/]")

    # 3. Calculate and display savings summary
    est_tokens = max(0, total_chars // 4)
    est_dollars_saved = (est_tokens / 1_000_000) * 10.0
    est_duration_saved = http_steps * 1.8

    summary_table = Table(title="Cassette Verification & Savings Summary", show_header=True, header_style="bold green")
    summary_table.add_column("Property", style="cyan")
    summary_table.add_column("Value", style="bold yellow")
    summary_table.add_row("Cassette File", cassette_path.name)
    summary_table.add_row("Total Steps", str(len(cassette.entries)))
    summary_table.add_row("HTTP Requests", str(http_steps))
    summary_table.add_row("Side Effects", str(side_effect_steps))
    summary_table.add_row("SHA-256 Hash Chaining", "Verified ✔")
    summary_table.add_row("PII / Secret Redaction", "Passed ✔" if not all_leaks else "Failed ❌")
    summary_table.add_row("Estimated Tokens Saved", f"{est_tokens:,}")
    summary_table.add_row("Estimated API Cost Saved", f"${est_dollars_saved:.4f}")
    summary_table.add_row("Estimated CI Time Saved", f"{est_duration_saved:.1f}s")

    console.print(summary_table)
    console.print("[bold green]✔ Cassette verified successfully! Ready for Git commit.[/]")


@app.command()
def diff(
    cassette_a: Path = typer.Argument(..., help="First cassette file"),
    cassette_b: Path = typer.Argument(..., help="Second cassette file"),
) -> None:
    """Compare two cassettes and highlight divergences in prompt execution and outputs."""
    try:
        c1 = Cassette.load(cassette_a, verify_integrity=False)
        c2 = Cassette.load(cassette_b, verify_integrity=False)
    except Exception as exc:
        console.print(f"[bold red]Error loading cassettes for comparison:[/] {exc}")
        sys.exit(1)

    table = Table(title="Cassette Divergence Diff", show_header=True, header_style="bold cyan")
    table.add_column("Step", width=6)
    table.add_column(f"{cassette_a.name}", style="yellow")
    table.add_column(f"{cassette_b.name}", style="green")

    max_len = max(len(c1.entries), len(c2.entries))
    for i in range(max_len):
        e1 = c1.entries[i] if i < len(c1.entries) else None
        e2 = c2.entries[i] if i < len(c2.entries) else None

        desc1 = f"{e1.entry_type}: {e1.entry_hash[:8]}" if e1 else "[red]<Missing>[/]"
        desc2 = f"{e2.entry_type}: {e2.entry_hash[:8]}" if e2 else "[red]<Missing>[/]"

        table.add_row(str(i + 1), desc1, desc2)

    console.print(table)


@app.command()
def stats(
    cassette_path: Path = typer.Argument(..., help="Path to the .jsonl cassette file"),
) -> None:
    """Calculate token savings, latency savings, and cost reductions achieved by replaying."""
    try:
        cassette = Cassette.load(cassette_path, verify_integrity=False)
    except Exception as exc:
        console.print(f"[bold red]Error loading cassette:[/] {exc}")
        sys.exit(1)

    total_chars = 0
    http_steps = 0
    side_effect_steps = 0

    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            http_steps += 1
            total_chars += len(entry.request.body) + len(entry.response.body)
        elif entry.entry_type == "side_effect":
            side_effect_steps += 1

    est_tokens = max(1, total_chars // 4)
    # Estimate based on blend of Claude 3.5 Sonnet / GPT-4o pricing (~$10/M tokens)
    est_dollars_saved = (est_tokens / 1_000_000) * 10.0
    # Average live LLM network call takes ~1.8 seconds vs 0.001s replay
    time_saved_seconds = http_steps * 1.8

    stats_table = Table(
        title="CI Replay Efficiency & Savings", show_header=True, header_style="bold green"
    )
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="bold yellow")

    stats_table.add_row("Total Recorded Steps", str(len(cassette.entries)))
    stats_table.add_row("HTTP LLM Calls Avoided", str(http_steps))
    stats_table.add_row("Side-Effects Safely Stubbed", str(side_effect_steps))
    stats_table.add_row("Estimated Tokens Saved", f"{est_tokens:,}")
    stats_table.add_row("Estimated API Cost Saved (per test run)", f"${est_dollars_saved:.4f}")
    stats_table.add_row("CI Pipeline Time Saved (per test run)", f"{time_saved_seconds:.1f}s")

    console.print(stats_table)


@app.command()
def play(
    cassette_path: Path = typer.Argument(..., help="Path to the .jsonl cassette file"),
) -> None:
    """Visually step through recorded agent steps in the terminal."""
    try:
        cassette = Cassette.load(cassette_path, verify_integrity=False)
    except Exception as exc:
        console.print(f"[bold red]Error loading cassette:[/] {exc}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold green]Replaying {len(cassette.entries)} recorded agent steps...[/]",
            title="📼 Flight Playback",
        )
    )

    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            console.print(
                Panel(
                    f"[bold yellow]Method:[/] {entry.request.method} {entry.request.url}\n"
                    f"[bold yellow]Response Code:[/] [green]{entry.response.status_code}[/]\n"
                    f"[dim]Body Preview:[/] {entry.response.body[:180]}...",
                    title=f"Step {entry.step}: LLM Network Interaction",
                    border_style="blue",
                )
            )
        elif entry.entry_type == "side_effect":
            console.print(
                Panel(
                    f"[bold cyan]Function:[/] {entry.side_effect_name}\n"
                    f"[bold cyan]Result:[/] {entry.side_effect_result}",
                    title=f"Step {entry.step}: Guarded Side-Effect",
                    border_style="magenta",
                )
            )


@app.command(name="export-otel")
def export_otel(
    cassette_path: Path = typer.Argument(..., help="Path to the .jsonl cassette file"),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Destination path for the OpenTelemetry JSON file. Defaults to stdout or <cassette>.otel.json",
    ),
    service_name: str = typer.Option(
        "rerunner-agent",
        "--service-name",
        "-s",
        help="Service name to attribute in OpenTelemetry resource attributes",
    ),
) -> None:
    """Export a recorded cassette into an OpenTelemetry (OTel) OTLP-compliant trace file."""
    from rerunner.otel import export_cassette_to_otel_file

    try:
        target = output_path or cassette_path.with_suffix(".otel.json")
        export_cassette_to_otel_file(cassette_path, target, service_name=service_name)

        console.print(
            Panel(
                f"[bold green]✔ Successfully exported cassette to OpenTelemetry trace format![/]\n"
                f"[bold cyan]Source:[/] {cassette_path}\n"
                f"[bold cyan]Destination:[/] {target}\n"
                f"[bold cyan]Service Name:[/] {service_name}\n"
                f"[dim]Compatible with Datadog, Jaeger, Grafana Tempo, and Dynatrace.[/]",
                title="🔭 OpenTelemetry Export",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Error exporting to OpenTelemetry:[/] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    app()

