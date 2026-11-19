"""Pytest plugin providing @pytest.mark.rerunner, auto-patching, and fixtures."""

from __future__ import annotations


import contextlib
import os
import re
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import pytest

from rerunner.config import config_cassette_dir
from rerunner.session import Session, SessionMode
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    import httpx


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI flags for pytest."""
    group = parser.getgroup("rerunner")
    group.addoption(
        "--rerunner-record",
        action="store_true",
        default=False,
        help="Record new cassettes instead of replaying existing ones",
    )
    group.addoption(
        "--rerunner-mode",
        action="store",
        choices=("auto", "record", "replay", "fork"),
        default=None,
        help="Override Rerunner session mode for marked tests and fixtures (auto|record|replay|fork)",
    )
    group.addoption(
        "--rerunner-summary",
        action="store_true",
        default=False,
        help="Generate and append savings summary to $GITHUB_STEP_SUMMARY after the test run",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "rerunner(cassette, mode='auto', auto_patch=True): Record or replay HTTP calls via Rerunner",
    )


def default_cassette_path_for_node(node: pytest.Item) -> str:
    """Derive a deterministic per-test cassette path under ``tests/cassettes/`` from ``node.nodeid``."""
    raw_nodeid = str(getattr(node, "nodeid", "test"))
    parts = raw_nodeid.split("::", 1)
    module_part = Path(parts[0]).with_suffix("").as_posix()
    module_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", module_part).strip("_") or "tests"
    test_part = parts[1] if len(parts) > 1 else getattr(node, "name", "test")
    test_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", test_part).strip("_") or "test"
    base_dir = os.getenv("RERUNNER_CASSETTE_DIR") or config_cassette_dir() or "tests/cassettes"
    return (Path(base_dir) / module_slug / f"{test_slug}.jsonl").as_posix()


def _resolve_cassette_path_for_item(node: pytest.Item) -> str:
    """Extract raw base cassette path from a test item's markers or node ID."""
    marker = node.get_closest_marker("rerunner")
    cassette_path: str | None = None
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    if not cassette_path:
        cassette_path = default_cassette_path_for_node(node)

    return cassette_path


def _resolve_pytest_cassette_and_mode(
    request: pytest.FixtureRequest,
) -> tuple[str, SessionMode, bool]:
    """Extract cassette path, effective session mode, and auto_patch flag for a test node."""
    cassette_path = _resolve_cassette_path_for_item(request.node)

    cli_mode = request.config.getoption("--rerunner-mode", None)
    is_record_mode = bool(request.config.getoption("--rerunner-record", False))
    marker = request.node.get_closest_marker("rerunner")
    marker_mode = marker.kwargs.get("mode") if marker else None

    if cli_mode in ("auto", "record", "replay", "fork"):
        raw_mode = cli_mode
    elif is_record_mode:
        raw_mode = "record"
    elif marker_mode in ("auto", "record", "replay", "fork"):
        raw_mode = marker_mode
    else:
        raw_mode = "auto"

    mode_val = cast(SessionMode, raw_mode)
    auto_patch = bool(marker.kwargs.get("auto_patch", True)) if marker else True

    # If running inside a pytest-xdist worker process, redirect writes to a worker-specific shard.
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        p = Path(cassette_path)
        if not re.search(r"[._](?:gw\d+|worker[-_]?\d+)$", p.stem) and (
            mode_val in ("record", "fork") or not p.exists()
        ):
            cassette_path = str(p.with_name(f"{p.stem}.{worker}{p.suffix}"))

    return cassette_path, mode_val, auto_patch


@pytest.fixture(autouse=True)
def _rerunner_marker_autouse(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """If the test is marked with @pytest.mark.rerunner, activate a Session with auto_patch=True by default."""
    marker = request.node.get_closest_marker("rerunner")
    if not marker:
        yield
        return

    cassette_path, mode_val, auto_patch = _resolve_pytest_cassette_and_mode(request)
    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch):
        yield


@pytest.fixture
def rerunner_transport(
    request: pytest.FixtureRequest,
) -> Generator[httpx.BaseTransport, None, None]:
    """Pytest fixture providing a pre-configured CassetteTransport for the current test."""
    from rerunner.patcher import get_active_session

    active_session = get_active_session()
    if active_session is not None:
        yield active_session.transport
        return

    cassette_path, mode_val, _ = _resolve_pytest_cassette_and_mode(request)
    # CassetteTransport does not accept 'auto'; default standalone fixture to 'replay' unless recorded
    transport_mode: Literal["record", "replay", "fork"] = (
        "record" if mode_val == "record" else ("fork" if mode_val == "fork" else "replay")
    )

    transport = CassetteTransport(cassette_path=cassette_path, mode=transport_mode)
    yield transport
    transport.close()


@pytest.fixture
def rerunner_session(
    request: pytest.FixtureRequest,
) -> Generator[Session, None, None]:
    """Pytest fixture providing an active Session."""
    from rerunner.patcher import get_active_session

    active_session = get_active_session()
    if active_session is not None:
        yield cast(Session, active_session)
        return

    cassette_path, mode_val, auto_patch = _resolve_pytest_cassette_and_mode(request)
    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch) as session:
        yield session


def merge_worker_shards(
    session: pytest.Session | None = None,
    root_dir: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Merge worker shards generated during pytest-xdist runs into unified cassettes."""
    from rerunner.cassette_ops import merge_cassettes

    targets_to_shards: dict[Path, set[Path]] = {}

    def _register_shard(shard_file: Path) -> None:
        if not shard_file.is_file() or shard_file.stat().st_size == 0:
            return
        match = re.search(r"[._](?:gw\d+|worker[-_]?\d+)$", shard_file.stem)
        if not match:
            return
        base_stem = re.sub(r"[._](?:gw\d+|worker[-_]?\d+)$", "", shard_file.stem)
        target = shard_file.with_name(f"{base_stem}{shard_file.suffix}").resolve()
        targets_to_shards.setdefault(target, set()).add(shard_file.resolve())

    # 1. Search near cassettes of collected items in session
    if session is not None:
        for item in getattr(session, "items", []):
            with contextlib.suppress(Exception):
                base_path_str = _resolve_cassette_path_for_item(item)
                base_path = Path(base_path_str).resolve()
                parent_dir = base_path.parent
                if parent_dir.is_dir():
                    for candidate in parent_dir.glob(f"{base_path.stem}.gw*.jsonl"):
                        _register_shard(candidate)
                    for candidate in parent_dir.glob(f"{base_path.stem}_gw*.jsonl"):
                        _register_shard(candidate)

    # 2. Search root_dir or common cassette directories
    search_dirs: list[Path] = []
    if root_dir is not None:
        search_dirs.append(Path(root_dir))
    elif session is not None and hasattr(session.config, "rootpath"):
        search_dirs.append(Path(session.config.rootpath))
    else:
        search_dirs.append(Path.cwd())

    default_dir = Path("tests/cassettes")
    if default_dir.is_dir() and default_dir not in search_dirs:
        search_dirs.append(default_dir)

    for sdir in search_dirs:
        if sdir.is_dir():
            for shard_candidate in sdir.rglob("*.gw*.jsonl"):
                _register_shard(shard_candidate)

    results: list[dict[str, Any]] = []
    for target_path, shard_set in sorted(targets_to_shards.items(), key=lambda x: str(x[0])):
        if not shard_set:
            continue
        sorted_shards = sorted(shard_set, key=lambda s: str(s))
        target_path.parent.mkdir(parents=True, exist_ok=True)
        res = merge_cassettes(sorted_shards, target_path, deduplicate=False)
        for s in sorted_shards:
            with contextlib.suppress(OSError):
                s.unlink(missing_ok=True)
        results.append(res)

    return results


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Merge worker cassette shards and optionally generate replay savings summary."""
    if os.environ.get("PYTEST_XDIST_WORKER") or hasattr(session.config, "workerinput"):
        return
    merge_worker_shards(session=session)

    if session.config.getoption("--rerunner-summary", False):
        try:
            from rerunner.cassette import Cassette
            from rerunner.cassette_ops import (
                estimate_entry_cost_usd,
                extract_detailed_tokens_from_body,
                extract_model_from_bodies,
            )
            from rerunner.reports import generate_savings_markdown

            cassette_dir = (
                os.getenv("RERUNNER_CASSETTE_DIR") or config_cassette_dir() or "tests/cassettes"
            )
            target_path = Path(cassette_dir)
            if not target_path.exists():
                return

            cassette_files: list[Path] = []
            if target_path.is_file():
                cassette_files.append(target_path)
            elif target_path.is_dir():
                for ext in ("*.zst", "*.gz", "*.jsonl", "*.json"):
                    cassette_files.extend(target_path.glob(ext))
                    cassette_files.extend(target_path.glob(f"**/{ext}"))
                cassette_files = sorted(dict.fromkeys(cassette_files))

            if not cassette_files:
                return

            total_steps = 0
            total_http = 0
            total_tools = 0
            total_tokens = 0
            prompt_tokens = 0
            completion_tokens = 0
            cache_creation_tokens = 0
            cache_read_tokens = 0
            total_latency_ms = 0.0
            estimated_cost_usd = 0.0
            by_model: dict[str, dict[str, Any]] = {}

            for path in cassette_files:
                try:
                    c = Cassette.load(path, verify_integrity=False)
                    total_steps += len(c.entries)
                    for entry in c.entries:
                        if entry.entry_type == "http" and entry.response:
                            total_http += 1
                            t_info = extract_detailed_tokens_from_body(entry.response.body)
                            req_body = entry.request.body if entry.request else ""
                            model_name = extract_model_from_bodies(req_body, entry.response.body)
                            cache_creation = t_info.get("cache_creation_input_tokens", 0)
                            cache_read = t_info.get("cache_read_input_tokens", 0)
                            if t_info["total"] or cache_creation or cache_read:
                                total_tokens += t_info["total"]
                                prompt_tokens += t_info["prompt"]
                                completion_tokens += t_info["completion"]
                                cache_creation_tokens += cache_creation
                                cache_read_tokens += cache_read
                                step_cost = estimate_entry_cost_usd(
                                    t_info["prompt"],
                                    t_info["completion"],
                                    t_info["total"],
                                    model=model_name,
                                    cache_creation_input_tokens=cache_creation,
                                    cache_read_input_tokens=cache_read,
                                )
                                estimated_cost_usd += step_cost
                                model_key = model_name or "unknown"
                                bucket = by_model.setdefault(
                                    model_key,
                                    {"calls": 0, "tokens": 0, "estimated_cost_usd": 0.0},
                                )
                                bucket["calls"] += 1
                                bucket["tokens"] += t_info["total"]
                                bucket["estimated_cost_usd"] = round(
                                    float(bucket["estimated_cost_usd"]) + step_cost, 6
                                )
                            total_latency_ms += (
                                sum(entry.response.chunk_delays_ms)
                                if entry.response.chunk_delays_ms
                                else 1800.0
                            )
                        elif entry.entry_type in ("side_effect", "tool"):
                            total_tools += 1
                except Exception:
                    continue

            md_text = generate_savings_markdown(
                cassette_count=len(cassette_files),
                total_steps=total_steps,
                total_http=total_http,
                total_tools=total_tools,
                total_tokens=total_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cache_creation_tokens=cache_creation_tokens,
                cache_read_tokens=cache_read_tokens,
                estimated_cost_usd=estimated_cost_usd,
                latency_sec=total_latency_ms / 1000.0,
                by_model=by_model,
            )

            step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
            if step_summary_path:
                with open(step_summary_path, "a", encoding="utf-8") as f:
                    f.write("\n" + md_text + "\n")
        except Exception:
            pass
