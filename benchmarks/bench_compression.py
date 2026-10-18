"""Automated serialization and compression benchmarks for Rerunner (Issue #22).

Compares Plain JSONL, Gzip (.gz), and Zstandard (.zst) formats across:
- Compression Ratio (%)
- Write Speed (MB/s)
- Decompression/Read Speed (MB/s)
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

console = Console()


def generate_synthetic_agent_cassette(num_turns: int = 100) -> list[CassetteEntry]:
    """Generate realistic synthetic multi-turn LLM agent execution entries."""
    entries: list[CassetteEntry] = []
    for step in range(1, num_turns + 1):
        prompt = (
            f"Step {step}: Analyze financial quarterly reports, calculate YoY net profit margin, "
            f"and evaluate supply chain disruption risks across APAC regions."
        )
        response_text = (
            f"Report analysis for Step {step}: YoY revenue grew by 14.2%. Operating margin expanded "
            f"to 22.8% due to automated cloud infrastructure efficiencies and token cost reduction. "
            f"Recommended risk mitigation: diversify multi-region backup vendors." * 5
        )
        entries.append(
            CassetteEntry(
                step=step,
                entry_type="http",
                request=RecordedRequest(
                    method="POST",
                    url="https://api.openai.com/v1/chat/completions",
                    headers={
                        "authorization": "Bearer sk-test-key",
                        "content-type": "application/json",
                    },
                    body=prompt,
                ),
                response=RecordedResponse(
                    status_code=200,
                    headers={"content-type": "application/json"},
                    body=response_text,
                ),
            )
        )
    return entries


def benchmark_format(filename: str, entries: list[CassetteEntry]) -> dict[str, float | str]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / filename
        cassette = Cassette(cassette_path)
        for e in entries:
            cassette.append(e)

        # 1. Benchmark Save / Write
        t0 = time.perf_counter()
        cassette.save()
        write_time = max(time.perf_counter() - t0, 1e-6)

        file_size_kb = cassette_path.stat().st_size / 1024

        # 2. Benchmark Load / Read
        t0 = time.perf_counter()
        reloaded = Cassette.load(cassette_path, verify_integrity=False)
        read_time = max(time.perf_counter() - t0, 1e-6)
        assert len(reloaded.entries) == len(entries)

    return {
        "filename": filename,
        "size_kb": file_size_kb,
        "write_time_ms": write_time * 1000,
        "read_time_ms": read_time * 1000,
    }


def run_benchmark() -> None:
    console.print("\n[bold cyan]🚀 Running Rerunner Cassette Serialization Benchmarks...[/]")
    entries = generate_synthetic_agent_cassette(num_turns=200)

    results = []
    results.append(benchmark_format("cassette.jsonl", entries))
    results.append(benchmark_format("cassette.jsonl.gz", entries))

    has_zstd = False
    try:
        import zstandard  # noqa: F401

        has_zstd = True
        results.append(benchmark_format("cassette.jsonl.zst", entries))
    except ImportError:
        pass

    baseline_size = results[0]["size_kb"]
    assert isinstance(baseline_size, float)

    table = Table(
        title="Cassette Compression & Throughput Performance",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Format", style="cyan", width=16)
    table.add_column("Size (KB)", justify="right", width=12)
    table.add_column("Compression", justify="right", width=14)
    table.add_column("Write Time", justify="right", width=14)
    table.add_column("Read Time", justify="right", width=14)

    for r in results:
        size = float(r["size_kb"])
        ratio = ((baseline_size - size) / baseline_size) * 100 if baseline_size else 0
        comp_str = f"{ratio:.1f}% reduction" if ratio > 0 else "Baseline (0%)"
        table.add_row(
            str(r["filename"]),
            f"{size:.1f} KB",
            comp_str,
            f"{float(r['write_time_ms']):.2f} ms",
            f"{float(r['read_time_ms']):.2f} ms",
        )

    console.print(table)
    if not has_zstd:
        console.print(
            "[yellow]Note: Install `pip install zstandard` to benchmark Zstandard format.[/]\n"
        )


if __name__ == "__main__":
    run_benchmark()
