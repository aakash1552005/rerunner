"""Tests verifying non-blocking, pass-through streaming for both sync and async HTTPX transports."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
import pytest
import httpx

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport


def test_sync_streaming_passthrough_yields_incrementally(tmp_path: Path) -> None:
    cassette_file = tmp_path / "stream_sync.jsonl"
    chunks_produced: list[str] = []

    def mock_stream_handler(request: httpx.Request) -> httpx.Response:
        def generate_sse() -> Iterator[bytes]:
            for i in range(3):
                chunk = f"data: token_{i}\n\n".encode()
                chunks_produced.append(f"token_{i}")
                yield chunk

        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=httpx.ByteStream(b"".join(generate_sse())),  # or custom stream
        )

    class CustomSyncStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.step = 0

        def __iter__(self) -> Iterator[bytes]:
            for i in range(3):
                self.step = i + 1
                chunks_produced.append(f"produced_{i}")
                yield f"data: {i}\n\n".encode()

        def close(self) -> None:
            pass

    def real_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=CustomSyncStream(),
        )

    transport = CassetteTransport(
        cassette_file,
        mode="record",
        real_transport=httpx.MockTransport(real_handler),
    )

    client = httpx.Client(transport=transport)
    received_chunks: list[str] = []

    with client.stream("GET", "https://api.openai.com/v1/chat/completions") as response:
        assert response.status_code == 200
        # Cassette shouldn't have recorded completed entry yet
        assert len(transport.cassette.entries) == 0

        for line in response.iter_lines():
            if line:
                received_chunks.append(line)
                # Verify chunks were produced as we consumed
                assert len(chunks_produced) > 0

    # Stream closed, now entry must be in cassette
    assert len(transport.cassette.entries) == 1
    entry = transport.cassette.entries[0]
    assert entry.response is not None
    assert entry.response.is_streaming is True
    assert len(entry.response.chunks) == 3
    assert len(entry.response.chunk_delays_ms) == 3

    # Now verify replay
    replay_transport = CassetteTransport(cassette_file, mode="replay")
    replay_client = httpx.Client(transport=replay_transport)
    replayed_chunks: list[str] = []
    with replay_client.stream("GET", "https://api.openai.com/v1/chat/completions") as response:
        for line in response.iter_lines():
            if line:
                replayed_chunks.append(line)

    assert replayed_chunks == received_chunks


@pytest.mark.asyncio
async def test_async_streaming_passthrough_yields_incrementally(tmp_path: Path) -> None:
    cassette_file = tmp_path / "stream_async.jsonl"
    chunks_produced: list[str] = []

    class CustomAsyncStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for i in range(3):
                chunks_produced.append(f"async_{i}")
                yield f"data: async_{i}\n\n".encode()

        async def aclose(self) -> None:
            pass

    async def async_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=CustomAsyncStream(),
        )

    transport = AsyncCassetteTransport(
        cassette_file,
        mode="record",
        real_transport=httpx.MockTransport(async_handler),
    )

    client = httpx.AsyncClient(transport=transport)
    received_chunks: list[str] = []

    async with client.stream("GET", "https://api.anthropic.com/v1/messages") as response:
        assert response.status_code == 200
        assert len(transport.cassette.entries) == 0

        async for line in response.aiter_lines():
            if line:
                received_chunks.append(line)

    assert len(transport.cassette.entries) == 1
    entry = transport.cassette.entries[0]
    assert entry.response is not None
    assert entry.response.is_streaming is True
    assert len(entry.response.chunks) == 3

    # Replay
    replay_transport = AsyncCassetteTransport(cassette_file, mode="replay")
    replay_client = httpx.AsyncClient(transport=replay_transport)
    replayed_chunks: list[str] = []
    async with replay_client.stream("GET", "https://api.anthropic.com/v1/messages") as response:
        async for line in response.aiter_lines():
            if line:
                replayed_chunks.append(line)

    assert replayed_chunks == received_chunks


def test_streaming_drop_mid_stream_partial_flag(tmp_path: Path) -> None:
    cassette_file = tmp_path / "dropped_stream.jsonl"

    class FailingStream(httpx.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b"data: chunk1\n\n"
            raise ConnectionResetError("Connection lost mid-flight")

        def close(self) -> None:
            pass

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=FailingStream(),
        )

    # 1. Default: record_partial_streams=False -> no entry written
    transport_no_partial = CassetteTransport(
        cassette_file,
        mode="record",
        real_transport=httpx.MockTransport(handler),
        record_partial_streams=False,
    )
    client_no_partial = httpx.Client(transport=transport_no_partial)
    with (
        pytest.raises(ConnectionResetError),
        client_no_partial.stream("GET", "https://api.example.com/stream") as resp,
    ):
        list(resp.iter_lines())

    assert len(transport_no_partial.cassette.entries) == 0

    # 2. record_partial_streams=True -> partial entry is preserved
    cassette_partial = tmp_path / "partial.jsonl"
    transport_partial = CassetteTransport(
        cassette_partial,
        mode="record",
        real_transport=httpx.MockTransport(handler),
        record_partial_streams=True,
    )
    client_partial = httpx.Client(transport=transport_partial)
    with (
        pytest.raises(ConnectionResetError),
        client_partial.stream("GET", "https://api.example.com/stream") as resp,
    ):
        list(resp.iter_lines())

    assert len(transport_partial.cassette.entries) == 1
    assert len(transport_partial.cassette.entries[0].response.chunks) == 1  # type: ignore[union-attr]
