"""Tests verifying thread-safety, asyncio.gather concurrency, and contextvars isolation."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import httpx

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette
from rerunner.session import Session
from rerunner.side_effects import get_active_cassette, reset_active_cassette, set_active_cassette
from rerunner.transport import CassetteTransport


def test_concurrent_threads_no_step_collisions(tmp_path: Path) -> None:
    cassette_file = tmp_path / "threads.zst"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"url": str(request.url)})

    mock_transport = httpx.MockTransport(handler)
    transport = CassetteTransport(
        cassette_file,
        mode="record",
        real_transport=mock_transport,
    )

    def worker(i: int) -> int:
        client = httpx.Client(transport=transport)
        resp = client.get(f"https://api.example.com/worker/{i}")
        assert resp.status_code == 200
        return i

    num_workers = 20
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        results = list(executor.map(worker, range(num_workers)))

    assert len(results) == num_workers
    transport.cassette.save()

    # Verify cassette entries have 20 unique steps from 1 to 20
    steps = [e.step for e in transport.cassette.entries]
    assert len(steps) == num_workers
    assert len(set(steps)) == num_workers
    assert sorted(steps) == list(range(1, num_workers + 1))


@pytest.mark.asyncio
async def test_asyncio_gather_concurrency_no_step_collisions(tmp_path: Path) -> None:
    cassette_file = tmp_path / "async_gather.zst"

    async def async_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.005)
        return httpx.Response(200, json={"url": str(request.url)})

    async_mock = httpx.MockTransport(async_handler)
    transport = AsyncCassetteTransport(
        cassette_file,
        mode="record",
        real_transport=async_mock,
    )
    client = httpx.AsyncClient(transport=transport)

    async def call_worker(i: int) -> int:
        resp = await client.get(f"https://api.example.com/item/{i}")
        assert resp.status_code == 200
        return i

    num_calls = 20
    tasks = [call_worker(i) for i in range(num_calls)]
    results = await asyncio.gather(*tasks)

    assert len(results) == num_calls
    transport.cassette.save()

    steps = [e.step for e in transport.cassette.entries]
    assert len(steps) == num_calls
    assert len(set(steps)) == num_calls
    assert sorted(steps) == list(range(1, num_calls + 1))


def test_nested_sessions_contextvars_isolation(tmp_path: Path) -> None:
    outer_path = tmp_path / "outer.jsonl"
    inner_path = tmp_path / "inner.jsonl"

    cass_outer = Cassette(outer_path)
    cass_inner = Cassette(inner_path)

    assert get_active_cassette() is None

    token_outer = set_active_cassette(cass_outer, mode="record")
    assert get_active_cassette() is cass_outer

    token_inner = set_active_cassette(cass_inner, mode="record")
    assert get_active_cassette() is cass_inner

    # Exit inner
    reset_active_cassette(token_inner)
    assert get_active_cassette() is cass_outer

    # Exit outer
    reset_active_cassette(token_outer)
    assert get_active_cassette() is None


@pytest.mark.asyncio
async def test_asyncio_contextvars_isolation_between_tasks(tmp_path: Path) -> None:
    cass_a_path = tmp_path / "task_a.jsonl"
    cass_b_path = tmp_path / "task_b.jsonl"

    observed: dict[str, str | None] = {}

    async def task_a() -> None:
        async with Session(cass_a_path, mode="record", auto_patch=False):
            await asyncio.sleep(0.01)
            active = get_active_cassette()
            observed["a"] = active.uri if active is not None else None

    async def task_b() -> None:
        async with Session(cass_b_path, mode="record", auto_patch=False):
            await asyncio.sleep(0.01)
            active = get_active_cassette()
            observed["b"] = active.uri if active is not None else None

    await asyncio.gather(asyncio.create_task(task_a()), asyncio.create_task(task_b()))

    assert observed["a"] == str(cass_a_path)
    assert observed["b"] == str(cass_b_path)
    assert get_active_cassette() is None
