from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_benchmark_report_generator_produces_valid_svg_and_markdown(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "benchmarks" / "generate_report.py"
    spec = importlib.util.spec_from_file_location("generate_report", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["generate_report"] = mod
    spec.loader.exec_module(mod)

    latency, compression = mod.generate_benchmark_artifacts(
        tmp_path,
        latency_steps=3,
        simulated_step_ms=5.0,
        compression_turns=10,
    )
    assert latency.steps == 3
    assert latency.tokens_saved == 3090
    assert len(compression) >= 2

    lat_svg = (tmp_path / "docs" / "assets" / "benchmark-latency.svg").read_text(encoding="utf-8")
    comp_svg = (tmp_path / "docs" / "assets" / "benchmark-compression.svg").read_text(
        encoding="utf-8"
    )
    bench_md = (tmp_path / "docs" / "benchmarks.md").read_text(encoding="utf-8")

    assert "<svg" in lat_svg and "</svg>" in lat_svg
    assert "<svg" in comp_svg and "</svg>" in comp_svg
    assert "assets/benchmark-latency.svg" in bench_md
    assert "assets/benchmark-compression.svg" in bench_md


def test_benchmark_cli_exports_json_alongside_default_artifacts(tmp_path: Path) -> None:
    script = tmp_path / "benchmarks" / "generate_report.py"
    script.parent.mkdir()
    shutil.copyfile(REPO_ROOT / "benchmarks" / script.name, script)
    output = tmp_path / "bench.json"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--steps",
            "3",
            "--step-ms",
            "5",
            "--turns",
            "10",
            "--json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    latency = report["latency"]
    assert latency["steps"] == 3
    assert latency["tokens_saved"] == 3090
    assert latency["speedup"] == pytest.approx(
        latency["live_total_s"] / max(latency["replay_total_s"], 1e-6)
    )
    compression = {row["filename"]: row for row in report["compression"]}
    plain = compression["cassette.jsonl"]
    gzip = compression["cassette.jsonl.gz"]
    assert plain["ratio_pct"] == 0
    assert gzip["ratio_pct"] == pytest.approx((1 - gzip["size_kb"] / plain["size_kb"]) * 100)
    assert (tmp_path / "docs" / "benchmarks.md").is_file()
    assert (tmp_path / "docs" / "assets" / "benchmark-latency.svg").is_file()
    assert (tmp_path / "docs" / "assets" / "benchmark-compression.svg").is_file()


def test_docs_and_localized_readmes_exist() -> None:
    for rel in [
        "mkdocs.yml",
        "docs/index.md",
        "docs/mcp-and-agents.md",
        "docs/proxy-and-ci.md",
        "docs/architecture.md",
        "docs/benchmarks.md",
        "docs/assets/benchmark-latency.svg",
        "docs/assets/benchmark-compression.svg",
        "docs/readme/README_zh.md",
        "docs/readme/README_ja.md",
        "docs/readme/README_ko.md",
        "docs/readme/README_es.md",
        "docs/readme/README_de.md",
    ]:
        assert (REPO_ROOT / rel).is_file(), f"Missing Phase 4 doc asset: {rel}"


def test_release_please_configs_match_package_version() -> None:
    manifest = json.loads((REPO_ROOT / ".release-please-manifest.json").read_text(encoding="utf-8"))
    config = json.loads((REPO_ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    server = json.loads((REPO_ROOT / "server.json").read_text(encoding="utf-8"))

    assert manifest["."] == server["version"]
    assert config["packages"]["."]["package-name"] == "rerunner"
