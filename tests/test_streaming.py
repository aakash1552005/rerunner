"""Tests for recording and replaying streaming SSE responses."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette
from rerunner.transport import CassetteTransport


SSE_CHUNKS = [
    b'data: {"token":"Hello"}\n\n',
    b'data: {"token":" world"}\n\n',
    b"data: [DONE]\n\n",
]

SPLIT_SSE_CHUNKS = [
    b'data: {"token":"mail alice.smith@exam',
    b'ple.org done"}\n\n',
    b"data: [DONE]\n\n",
]

REDACTED_SPLIT_SSE_CHUNKS = [
    b'data: {"token":"mail ',
    b'[REDACTED_EMAIL] done"}\n\n',
    b"data: [DONE]\n\n",
]


class SyncChunkStream(httpx.SyncByteStream):
    """Yield predefined synchronous response chunks."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks


class AsyncChunkStream(httpx.AsyncByteStream):
    """Yield predefined asynchronous response chunks."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk


class SyncSSETransport(httpx.BaseTransport):
    """Return a mocked synchronous SSE response."""

    def __init__(self) -> None:
        self.call_count = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=SyncChunkStream(SSE_CHUNKS),
            request=request,
        )


class AsyncSSETransport(httpx.AsyncBaseTransport):
    """Return a mocked asynchronous SSE response."""

    def __init__(self) -> None:
        self.call_count = 0

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=AsyncChunkStream(SSE_CHUNKS),
            request=request,
        )


def test_sync_stream_records_and_replays_chunks(tmp_path: Path) -> None:
    """Synchronous replay yields recorded SSE chunks without another network call."""
    cassette_path = tmp_path / "sync-stream.jsonl"
    network = SyncSSETransport()
    request_body = {"model": "test", "stream": True}

    record_transport = CassetteTransport(
        cassette_path,
        mode="record",
        real_transport=network,
    )

    with (
        httpx.Client(transport=record_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert list(response.iter_raw()) == SSE_CHUNKS

    cassette = Cassette.load(cassette_path)
    recorded_response = cassette.entries[0].response

    assert recorded_response is not None
    assert recorded_response.is_streaming is True
    assert recorded_response.chunks == [chunk.decode("utf-8") for chunk in SSE_CHUNKS]

    replay_transport = CassetteTransport(
        cassette_path,
        mode="replay",
        real_transport=network,
    )

    with (
        httpx.Client(transport=replay_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert list(response.iter_raw()) == SSE_CHUNKS

    assert network.call_count == 1


def test_openai_sdk_streams_replayed_chunks_without_network(tmp_path: Path) -> None:
    """The OpenAI SDK streams replayed chunks without another network call."""
    from openai import OpenAI

    openai_chunks = [
        (
            b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk",'
            b'"created":0,"model":"test-model","choices":[{"index":0,'
            b'"delta":{"role":"assistant","content":"Hello"},'
            b'"finish_reason":null}]}\n\n'
        ),
        (
            b'data: {"id":"chatcmpl-test","object":"chat.completion.chunk",'
            b'"created":0,"model":"test-model","choices":[{"index":0,'
            b'"delta":{"content":" world"},"finish_reason":null}]}\n\n'
        ),
        b"data: [DONE]\n\n",
    ]

    network_call_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal network_call_count
        network_call_count += 1

        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=SyncChunkStream(openai_chunks),
            request=request,
        )

    cassette_path = tmp_path / "openai-sdk-stream.jsonl"
    network = httpx.MockTransport(handle_request)

    record_transport = CassetteTransport(
        cassette_path,
        mode="record",
        real_transport=network,
    )

    # OpenAI 3.x types its client as httpx2.Client, but httpx.Client is runtime-compatible and required to exercise Rerunner's HTTPX transport.
    with httpx.Client(transport=record_transport) as http_client:
        client = OpenAI(
            api_key="test-key",
            base_url="https://example.test/v1",
            http_client=http_client,  # type: ignore[arg-type]
        )
        stream = client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
        recorded_tokens = [chunk.choices[0].delta.content for chunk in stream]

    assert recorded_tokens == ["Hello", " world"]
    assert network_call_count == 1

    replay_transport = CassetteTransport(
        cassette_path,
        mode="replay",
        real_transport=network,
    )

    with httpx.Client(transport=replay_transport) as http_client:
        client = OpenAI(
            api_key="test-key",
            base_url="https://example.test/v1",
            http_client=http_client,  # type: ignore[arg-type]
        )
        stream = client.chat.completions.create(
            model="test-model",
            messages=[{"role": "user", "content": "Hello"}],
            stream=True,
        )
        replayed_tokens = [chunk.choices[0].delta.content for chunk in stream]

    assert replayed_tokens == ["Hello", " world"]
    assert network_call_count == 1


@pytest.mark.asyncio
async def test_async_stream_records_and_replays_chunks(
    tmp_path: Path,
) -> None:
    """Asynchronous replay yields SSE chunks without another network call."""
    cassette_path = tmp_path / "async-stream.jsonl"
    network = AsyncSSETransport()
    request_body = {"model": "test", "stream": True}

    record_transport = AsyncCassetteTransport(
        cassette_path,
        mode="record",
        real_transport=network,
    )

    async with (
        httpx.AsyncClient(transport=record_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        recorded_chunks = [chunk async for chunk in response.aiter_raw()]

    assert recorded_chunks == SSE_CHUNKS

    cassette = Cassette.load(cassette_path)
    recorded_response = cassette.entries[0].response

    assert recorded_response is not None
    assert recorded_response.is_streaming is True
    assert recorded_response.chunks == [chunk.decode("utf-8") for chunk in SSE_CHUNKS]

    replay_transport = AsyncCassetteTransport(
        cassette_path,
        mode="replay",
        real_transport=network,
    )

    async with (
        httpx.AsyncClient(transport=replay_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        replayed_chunks = [chunk async for chunk in response.aiter_raw()]

    assert replayed_chunks == SSE_CHUNKS
    assert network.call_count == 1


@pytest.mark.parametrize(
    "transport_type",
    [CassetteTransport, AsyncCassetteTransport],
)
def test_negative_chunk_delay_is_rejected(
    tmp_path: Path,
    transport_type: type[CassetteTransport] | type[AsyncCassetteTransport],
) -> None:
    """Streaming transports reject negative simulated latency."""
    with pytest.raises(ValueError, match="chunk_delay_ms must be non-negative"):
        transport_type(tmp_path / "stream.jsonl", chunk_delay_ms=-1)


def test_sync_stream_redacts_value_split_across_chunks(tmp_path: Path) -> None:
    """A value split across network chunks never reaches the cassette or the replay."""
    cassette_path = tmp_path / "split-stream.jsonl"
    network_call_count = 0

    def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal network_call_count
        network_call_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=SyncChunkStream(SPLIT_SSE_CHUNKS),
            request=request,
        )

    network = httpx.MockTransport(handle_request)
    request_body = {"model": "test", "stream": True}

    record_transport = CassetteTransport(cassette_path, mode="record", real_transport=network)
    with (
        httpx.Client(transport=record_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert list(response.iter_raw()) == SPLIT_SSE_CHUNKS

    assert b"alice.smith" not in cassette_path.read_bytes()
    recorded_response = Cassette.load(cassette_path).entries[0].response
    assert recorded_response is not None
    assert recorded_response.chunks == [
        chunk.decode("utf-8") for chunk in REDACTED_SPLIT_SSE_CHUNKS
    ]
    assert len(recorded_response.chunk_delays_ms) == len(REDACTED_SPLIT_SSE_CHUNKS)

    replay_transport = CassetteTransport(cassette_path, mode="replay", real_transport=network)
    with (
        httpx.Client(transport=replay_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert list(response.iter_raw()) == REDACTED_SPLIT_SSE_CHUNKS

    assert network_call_count == 1


@pytest.mark.asyncio
async def test_async_stream_redacts_value_split_across_chunks(tmp_path: Path) -> None:
    """The asynchronous transport applies the same boundary-aware chunk sanitization."""
    cassette_path = tmp_path / "split-stream-async.jsonl"
    network_call_count = 0

    async def handle_request(request: httpx.Request) -> httpx.Response:
        nonlocal network_call_count
        network_call_count += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=AsyncChunkStream(SPLIT_SSE_CHUNKS),
            request=request,
        )

    network = httpx.MockTransport(handle_request)
    request_body = {"model": "test", "stream": True}

    record_transport = AsyncCassetteTransport(cassette_path, mode="record", real_transport=network)
    async with (
        httpx.AsyncClient(transport=record_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert [chunk async for chunk in response.aiter_raw()] == SPLIT_SSE_CHUNKS

    assert b"alice.smith" not in cassette_path.read_bytes()
    recorded_response = Cassette.load(cassette_path).entries[0].response
    assert recorded_response is not None
    assert recorded_response.chunks == [
        chunk.decode("utf-8") for chunk in REDACTED_SPLIT_SSE_CHUNKS
    ]

    replay_transport = AsyncCassetteTransport(cassette_path, mode="replay", real_transport=network)
    async with (
        httpx.AsyncClient(transport=replay_transport) as client,
        client.stream(
            "POST",
            "https://example.test/v1/chat/completions",
            json=request_body,
        ) as response,
    ):
        assert [chunk async for chunk in response.aiter_raw()] == REDACTED_SPLIT_SSE_CHUNKS

    assert network_call_count == 1
