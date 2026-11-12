from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_benchmark_report_generator_produces_valid_svg_and_markdown(tmp_path: Path) -> None:
    script_path = REPO_ROOT / "benchmarks" / "generate_report.py"
    spec = importlib.util.spec_from_file_location("generate_report", script_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    import sys

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
