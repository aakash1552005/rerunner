"""Reproducible benchmark suite & SVG/Markdown report generator (Issue #62).

Generates:
- docs/assets/benchmark-latency.svg
- docs/assets/benchmark-compression.svg
- docs/benchmarks.md
"""

from __future__ import annotations

import argparse
import html
import json
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from rerunner import CassetteTransport
from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse


@dataclass(frozen=True)
class CompressionRow:
    label: str
    filename: str
    size_kb: float
    ratio_pct: float
    write_ms: float
    read_ms: float


@dataclass(frozen=True)
class LatencySummary:
    steps: int
    simulated_step_ms: float
    live_total_s: float
    replay_total_s: float
    speedup: float
    tokens_saved: int
    cost_saved_usd: float


def _build_synthetic_entries(num_turns: int = 200) -> list[CassetteEntry]:
    entries: list[CassetteEntry] = []
    for step in range(1, num_turns + 1):
        prompt = (
            f"Step {step}: Analyze quarterly financials, compute YoY margin delta, "
            "and evaluate APAC supply chain risks."
        )
        response_text = (
            f"Analysis for Step {step}: Revenue +14.2% YoY, operating margin 22.8% "
            "driven by deterministic CI caching and token reduction. " * 5
        )
        entries.append(
            CassetteEntry(
                step=step,
                entry_type="http",
                request=RecordedRequest(
                    method="POST",
                    url="https://api.openai.com/v1/chat/completions",
                    headers={"content-type": "application/json"},
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


def measure_compression(num_turns: int = 200) -> list[CompressionRow]:
    entries = _build_synthetic_entries(num_turns=num_turns)
    formats: list[tuple[str, str]] = [
        ("Plain JSONL", "cassette.jsonl"),
        ("Gzip (.gz)", "cassette.jsonl.gz"),
    ]
    try:
        import zstandard  # noqa: F401

        formats.append(("Zstandard (.zst)", "cassette.jsonl.zst"))
    except ImportError:
        pass

    raw_results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        for label, filename in formats:
            path = Path(tmp_dir) / filename
            cassette = Cassette(path)
            for entry in entries:
                cassette.append(entry)

            t0 = time.perf_counter()
            cassette.save()
            write_ms = max(time.perf_counter() - t0, 1e-6) * 1000.0
            size_kb = path.stat().st_size / 1024.0

            t0 = time.perf_counter()
            reloaded = Cassette.load(path, verify_integrity=False)
            read_ms = max(time.perf_counter() - t0, 1e-6) * 1000.0
            if len(reloaded.entries) != len(entries):
                raise RuntimeError("Reloaded cassette entry count mismatch")

            raw_results.append(
                {
                    "label": label,
                    "filename": filename,
                    "size_kb": size_kb,
                    "write_ms": write_ms,
                    "read_ms": read_ms,
                }
            )

    baseline_kb = raw_results[0]["size_kb"]
    rows: list[CompressionRow] = []
    for item in raw_results:
        ratio_pct = (1.0 - (item["size_kb"] / max(baseline_kb, 1e-6))) * 100.0
        rows.append(
            CompressionRow(
                label=item["label"],
                filename=item["filename"],
                size_kb=item["size_kb"],
                ratio_pct=max(ratio_pct, 0.0),
                write_ms=item["write_ms"],
                read_ms=item["read_ms"],
            )
        )
    return rows


def measure_latency(num_requests: int = 20, simulated_step_ms: float = 150.0) -> LatencySummary:
    class _SimulatedLiveTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.calls = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            time.sleep(simulated_step_ms / 1000.0)
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "id": f"chatcmpl-bench-{self.calls}",
                    "model": "gpt-4o",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": f"Verified step {self.calls}.",
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 850,
                        "completion_tokens": 180,
                        "total_tokens": 1030,
                    },
                },
            )

    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "latency_bench.jsonl"
        live_transport = _SimulatedLiveTransport()
        record_transport = CassetteTransport(
            cassette_path=cassette_path,
            mode="record",
            real_transport=live_transport,
        )

        t0 = time.perf_counter()
        with httpx.Client(transport=record_transport) as client:
            for i in range(num_requests):
                client.post("https://api.openai.com/v1/chat/completions", json={"step": i})
        live_total_s = time.perf_counter() - t0

        replay_transport = CassetteTransport(cassette_path=cassette_path, mode="replay")
        t0 = time.perf_counter()
        with httpx.Client(transport=replay_transport) as client:
            for i in range(num_requests):
                resp = client.post("https://api.openai.com/v1/chat/completions", json={"step": i})
                if resp.status_code != 200:
                    raise RuntimeError(f"Unexpected status during replay: {resp.status_code}")
        replay_total_s = time.perf_counter() - t0

    speedup = live_total_s / max(replay_total_s, 1e-6)
    tokens_saved = num_requests * 1030
    cost_saved_usd = (num_requests * 850 * 2.50 + num_requests * 180 * 10.00) / 1_000_000.0
    return LatencySummary(
        steps=num_requests,
        simulated_step_ms=simulated_step_ms,
        live_total_s=live_total_s,
        replay_total_s=replay_total_s,
        speedup=speedup,
        tokens_saved=tokens_saved,
        cost_saved_usd=cost_saved_usd,
    )


def render_horizontal_bar_svg(
    title: str,
    subtitle: str,
    bars: list[tuple[str, float, str, str]],
    unit_suffix: str,
) -> str:
    width = 720
    header_h = 74
    row_h = 54
    height = header_h + len(bars) * row_h + 28
    max_val = max((v for _, v, _, _ in bars), default=1.0)
    bar_x = 210
    max_bar_w = 360

    rows_svg: list[str] = []
    for idx, (label, value, display, color) in enumerate(bars):
        y = header_h + idx * row_h
        bar_w = max(8.0, (value / max(max_val, 1e-6)) * max_bar_w)
        rows_svg.append(
            f'<text x="24" y="{y + 24}" fill="#e2e8f0" font-size="13" font-weight="600" '
            f'font-family="ui-sans-serif, system-ui, sans-serif">{html.escape(label)}</text>'
            f'<rect x="{bar_x}" y="{y + 10}" width="{max_bar_w}" height="20" rx="6" fill="#1e293b"/>'
            f'<rect x="{bar_x}" y="{y + 10}" width="{bar_w:.1f}" height="20" rx="6" fill="{color}"/>'
            f'<text x="{bar_x + max_bar_w + 14}" y="{y + 25}" fill="#f8fafc" font-size="13" '
            f'font-weight="600" font-family="ui-monospace, monospace">{html.escape(display)}{html.escape(unit_suffix)}</text>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">\n'
        f'  <rect width="{width}" height="{height}" rx="14" fill="#0f172a"/>\n'
        f'  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="13" '
        f'fill="none" stroke="#334155"/>\n'
        f'  <text x="24" y="34" fill="#f8fafc" font-size="18" font-weight="700" '
        f'font-family="ui-sans-serif, system-ui, sans-serif">{html.escape(title)}</text>\n'
        f'  <text x="24" y="54" fill="#94a3b8" font-size="12" '
        f'font-family="ui-sans-serif, system-ui, sans-serif">{html.escape(subtitle)}</text>\n'
        f"  {''.join(rows_svg)}\n"
        f"</svg>\n"
    )


def generate_benchmark_artifacts(
    repo_root: Path,
    *,
    latency_steps: int = 20,
    simulated_step_ms: float = 150.0,
    compression_turns: int = 200,
) -> tuple[LatencySummary, list[CompressionRow]]:
    latency = measure_latency(num_requests=latency_steps, simulated_step_ms=simulated_step_ms)
    compression = measure_compression(num_turns=compression_turns)

    assets_dir = repo_root / "docs" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    latency_svg = render_horizontal_bar_svg(
        title="Rerunner Deterministic Replay vs. Live LLM API",
        subtitle=f"{latency.steps} agent turns ({latency.simulated_step_ms:.0f}ms simulated network RTT/turn) · {latency.speedup:.1f}x faster · $0.00 token spend",
        bars=[
            ("Live API Calls", latency.live_total_s, f"{latency.live_total_s:.2f}", "#ef4444"),
            (
                "Rerunner Replay",
                latency.replay_total_s,
                f"{latency.replay_total_s:.3f}",
                "#22c55e",
            ),
        ],
        unit_suffix="s",
    )
    (assets_dir / "benchmark-latency.svg").write_text(latency_svg, encoding="utf-8")

    palette = ["#64748b", "#3b82f6", "#10b981"]
    comp_bars = [
        (
            row.label,
            row.size_kb,
            f"{row.size_kb:.1f}",
            palette[idx % len(palette)],
        )
        for idx, row in enumerate(compression)
    ]
    comp_svg = render_horizontal_bar_svg(
        title="Cassette Storage Footprint by Format",
        subtitle=f"{compression_turns}-turn multi-step agent trajectory (JSONL vs. Gzip vs. Zstandard)",
        bars=comp_bars,
        unit_suffix=" KB",
    )
    (assets_dir / "benchmark-compression.svg").write_text(comp_svg, encoding="utf-8")

    comp_table_rows = "\n".join(
        f"| {row.label} | `{row.filename}` | {row.size_kb:.2f} KB | {row.ratio_pct:.1f}% | "
        f"{row.write_ms:.2f} ms | {row.read_ms:.2f} ms |"
        for row in compression
    )
    markdown = f"""# Benchmarks

All numbers below are generated reproducibly by running:

```bash
python benchmarks/generate_report.py
```

## 1. Deterministic Replay vs. Live LLM API Latency

![Replay vs Live Latency](assets/benchmark-latency.svg)

| Metric | Live API (`{latency.steps}` turns @ `{latency.simulated_step_ms:.0f}ms` RTT) | Rerunner Replay |
| :--- | :--- | :--- |
| **Total Wall Time** | {latency.live_total_s:.2f}s | **{latency.replay_total_s:.3f}s** |
| **Speedup** | 1.0x | **{latency.speedup:.1f}x faster** |
| **Tokens Consumed** | {latency.tokens_saved:,} tokens | **0 tokens** |
| **Estimated Cost (gpt-4o)** | ${latency.cost_saved_usd:.4f} | **$0.0000** |

## 2. Cassette Serialization & Compression ({compression_turns} Turns)

![Compression Footprint](assets/benchmark-compression.svg)

| Format | Extension | File Size | Space Saved | Write Time | Read Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
{comp_table_rows}
"""
    (repo_root / "docs" / "benchmarks.md").write_text(markdown, encoding="utf-8")
    return latency, compression


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Rerunner benchmark SVG/Markdown reports."
    )
    parser.add_argument("--steps", type=int, default=20, help="Number of turns for latency bench.")
    parser.add_argument("--step-ms", type=float, default=150.0, help="Simulated RTT ms per turn.")
    parser.add_argument("--turns", type=int, default=200, help="Number of turns for compression.")
    parser.add_argument(
        "--json", type=Path, metavar="PATH", help="Also write benchmark metrics as JSON."
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    latency, compression = generate_benchmark_artifacts(
        repo_root,
        latency_steps=args.steps,
        simulated_step_ms=args.step_ms,
        compression_turns=args.turns,
    )
    if args.json is not None:
        report = {
            "latency": asdict(latency),
            "compression": [asdict(row) for row in compression],
        }
        args.json.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    print(
        f"Generated benchmarks: {latency.speedup:.1f}x speedup "
        f"({latency.live_total_s:.2f}s -> {latency.replay_total_s:.3f}s), "
        f"{len(compression)} compression formats."
    )


if __name__ == "__main__":
    main()
