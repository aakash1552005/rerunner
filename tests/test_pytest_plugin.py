"""Tests for the Rerunner pytest plugin CLI flags and marker precedence."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rerunner.cassette import Cassette
from rerunner.matcher import compute_request_key
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.pytest_plugin import (
    _resolve_pytest_cassette_and_mode,
    merge_worker_shards,
)

pytest_plugins = ["pytester"]


def test_pytest_rerunner_mode_flag_overrides_marker(pytester: pytest.Pytester) -> None:
    cassette_path = pytester.path / "missing_strict.jsonl"
    pytester.makepyfile(
        f"""
        import httpx
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_strict_replay_fails_when_missing():
            httpx.get("https://api.example.com/hello")
        """
    )

    result = pytester.runpytest("--rerunner-mode=replay")
    # Fixture setup raises CassetteMissingError because --rerunner-mode=replay overrides mode="auto"
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*CassetteMissingError*"])


def test_pytest_rerunner_mode_precedence_over_record_flag(pytester: pytest.Pytester) -> None:
    cassette_path = pytester.path / "precedence.jsonl"
    cassette_path.write_text("", encoding="utf-8")
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_session_mode(rerunner_session):
            assert rerunner_session.mode == "replay"
        """
    )

    # Empty cassette still raises CassetteMissingError in replay mode even if --rerunner-record is passed
    result = pytester.runpytest("--rerunner-record", "--rerunner-mode=replay")
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*CassetteMissingError*"])


def test_pytest_rerunner_transport_respects_mode_flag(pytester: pytest.Pytester) -> None:
    cassette_path = Path(pytester.path) / "transport_mode.jsonl"
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_transport_mode(rerunner_transport):
            assert rerunner_transport.mode == "record"
        """
    )

    result = pytester.runpytest("--rerunner-mode=record")
    assert result.ret == 0


def _make_dummy_entry(step: int, text: str) -> CassetteEntry:
    req_body = json.dumps({"query": text})
    url = "https://api.example.com/data"
    return CassetteEntry(
        step=step,
        entry_type="http",
        request=RecordedRequest(
            method="POST",
            url=url,
            headers={"content-type": "application/json"},
            body=req_body,
            request_key=compute_request_key("POST", url, req_body),
        ),
        response=RecordedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=json.dumps({"result": f"ack_{text}"}),
        ),
    )


def test_pytest_xdist_worker_sharding_resolution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cassette_file = tmp_path / "parallel_suite.jsonl"
    fake_node: Any = SimpleNamespace(
        nodeid="tests/test_worker.py::test_one",
        name="test_one",
        get_closest_marker=lambda _name: SimpleNamespace(
            args=(str(cassette_file),), kwargs={"mode": "record"}
        ),
    )
    fake_request: Any = SimpleNamespace(
        node=fake_node,
        config=SimpleNamespace(getoption=lambda _opt, default=None: default),
    )

    # 1. Without PYTEST_XDIST_WORKER: uses base path
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    path_no_worker, _, _ = _resolve_pytest_cassette_and_mode(fake_request)
    assert path_no_worker == str(cassette_file)

    # 2. With PYTEST_XDIST_WORKER="gw0" in record mode: shards to parallel_suite.gw0.jsonl
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    path_gw0, _, _ = _resolve_pytest_cassette_and_mode(fake_request)
    assert path_gw0 == str(tmp_path / "parallel_suite.gw0.jsonl")

    # 3. With PYTEST_XDIST_WORKER="gw1" in record mode: shards to parallel_suite.gw1.jsonl
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    path_gw1, _, _ = _resolve_pytest_cassette_and_mode(fake_request)
    assert path_gw1 == str(tmp_path / "parallel_suite.gw1.jsonl")

    # 4. In replay mode when base file already exists, workers share the base cassette
    cassette_file.write_text("{}", encoding="utf-8")
    replay_node: Any = SimpleNamespace(
        nodeid="tests/test_worker.py::test_one",
        name="test_one",
        get_closest_marker=lambda _name: SimpleNamespace(
            args=(str(cassette_file),), kwargs={"mode": "replay"}
        ),
    )
    replay_request: Any = SimpleNamespace(
        node=replay_node,
        config=SimpleNamespace(getoption=lambda _opt, default=None: default),
    )
    path_replay, _, _ = _resolve_pytest_cassette_and_mode(replay_request)
    assert path_replay == str(cassette_file)


def test_merge_worker_shards_produces_unified_verified_cassette(tmp_path: Path) -> None:
    cassette_dir = tmp_path / "cassettes"
    cassette_dir.mkdir(parents=True)
    target_cassette = cassette_dir / "xdist_merged.jsonl"
    shard0 = cassette_dir / "xdist_merged.gw0.jsonl"
    shard1 = cassette_dir / "xdist_merged.gw1.jsonl"

    c0 = Cassette(shard0)
    c0.append_entry(_make_dummy_entry(1, "worker_0_call"))
    c0.save()

    c1 = Cassette(shard1)
    c1.append_entry(_make_dummy_entry(1, "worker_1_call"))
    c1.save()

    assert shard0.exists()
    assert shard1.exists()
    assert not target_cassette.exists()

    # Run merge_worker_shards
    results = merge_worker_shards(root_dir=cassette_dir)
    assert len(results) == 1
    assert results[0]["merged_steps"] == 2

    # Target cassette must now exist and verify 100% cryptographic SHA-256 hash chaining
    assert target_cassette.exists()
    loaded = Cassette.load(target_cassette, verify_integrity=True)
    assert len(loaded.entries) == 2
    assert [e.step for e in loaded.entries] == [1, 2]
    assert loaded.entries[0].prev_hash == "GENESIS"
    assert loaded.entries[1].prev_hash == loaded.entries[0].entry_hash

    # Worker shards should be cleaned up
    assert not shard0.exists()
    assert not shard1.exists()


def test_pytest_sessionfinish_hook_executes_on_controller(pytester: pytest.Pytester) -> None:
    cassette_dir = pytester.path / "cassettes"
    cassette_dir.mkdir(parents=True)
    target_cassette = cassette_dir / "controller_merge.jsonl"
    shard0 = cassette_dir / "controller_merge.gw0.jsonl"
    shard1 = cassette_dir / "controller_merge.gw1.jsonl"

    c0 = Cassette(shard0)
    c0.append_entry(_make_dummy_entry(1, "first"))
    c0.save()

    c1 = Cassette(shard1)
    c1.append_entry(_make_dummy_entry(1, "second"))
    c1.save()

    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.rerunner(cassette={str(target_cassette)!r}, mode="auto")
        def test_dummy():
            pass
        """
    )

    # Controller run executes pytest_sessionfinish
    res = pytester.runpytest()
    assert res.ret == 0

    assert target_cassette.exists()
    loaded = Cassette.load(target_cassette, verify_integrity=True)
    assert len(loaded.entries) == 2
    assert not shard0.exists()
    assert not shard1.exists()
