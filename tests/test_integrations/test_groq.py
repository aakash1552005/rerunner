"""Tests for the Groq SDK integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.integrations.groq import wrap_groq_client
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


groq = pytest.importorskip("groq")
Groq = groq.Groq
AsyncGroq = groq.AsyncGroq


GROQ_RESPONSE = {
    "id": "chatcmpl-groq-test",
    "object": "chat.completion",
    "created": 1730000000,
    "model": "llama-3.3-70b-versatile",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello from Groq",
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {
        "prompt_tokens": 5,
        "completion_tokens": 4,
        "total_tokens": 9,
    },
}


class FakeGroqAPI(httpx.BaseTransport):
    """Simulate Groq HTTP responses without network access."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)

        return httpx.Response(
            200,
            json=GROQ_RESPONSE,
            request=request,
        )


class AsyncFakeGroqAPI(httpx.AsyncBaseTransport):
    """Asynchronous fake Groq HTTP transport."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        self.calls.append(request)

        return httpx.Response(
            200,
            json=GROQ_RESPONSE,
            request=request,
        )


# ---------------------------------------------------------
# Test 1: Synchronous Groq wrapper
# ---------------------------------------------------------


def test_wrap_groq_sync(tmp_path: Path) -> None:
    client = Groq(api_key="fake-api-key")

    try:
        result = wrap_groq_client(
            client,
            cassette_path=tmp_path / "groq.jsonl",
            mode="replay",
        )

        assert result is client
        assert isinstance(client._client, httpx.Client)
        assert isinstance(
            client._client._transport,
            CassetteTransport,
        )
        assert client._client._transport.mode == "replay"

    finally:
        client.close()


# ---------------------------------------------------------
# Test 2: Asynchronous Groq wrapper
# ---------------------------------------------------------


async def test_wrap_groq_async(tmp_path: Path) -> None:
    client = AsyncGroq(api_key="fake-api-key")

    try:
        result = wrap_groq_client(
            client,
            cassette_path=tmp_path / "groq_async.jsonl",
            mode="replay",
        )

        assert result is client
        assert isinstance(client._client, httpx.AsyncClient)
        assert isinstance(
            client._client._transport,
            AsyncCassetteTransport,
        )
        assert client._client._transport.mode == "replay"

    finally:
        await client.close()


# ---------------------------------------------------------
# Test 3: Synchronous recording and replay
# ---------------------------------------------------------


def test_groq_chat_records_then_replays(tmp_path: Path) -> None:
    cassette_path = tmp_path / "groq_recording.jsonl"
    api = FakeGroqAPI()

    recorder = wrap_groq_client(
        Groq(api_key="fake-api-key"),
        cassette_path,
        mode="record",
    )

    replayer = None

    try:
        recorder._client._transport.real_transport = api

        recorded = recorder.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "Say hello"},
            ],
        )

        assert recorded.choices[0].message.content == "Hello from Groq"
        assert recorded.usage.total_tokens == 9
        assert len(api.calls) == 1
        assert cassette_path.exists()

        # Verify the outgoing request.
        sent = json.loads(api.calls[0].content)

        assert sent["model"] == "llama-3.3-70b-versatile"
        assert sent["messages"] == [{"role": "user", "content": "Say hello"}]

        # Create a fresh client in replay mode.
        replayer = wrap_groq_client(
            Groq(api_key="fake-api-key"),
            cassette_path,
            mode="replay",
        )

        # If replay incorrectly forwards requests,
        # the fake API call count will increase.
        replayer._client._transport.real_transport = api

        replayed = replayer.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "Say hello"},
            ],
        )

        assert replayed.choices[0].message.content == "Hello from Groq"
        assert replayed.usage.total_tokens == 9

        # Only the record phase should reach the fake API.
        assert len(api.calls) == 1

    finally:
        recorder.close()

        if replayer is not None:
            replayer.close()


# ---------------------------------------------------------
# Test 4: Asynchronous recording and replay
# ---------------------------------------------------------


async def test_groq_async_chat_records_then_replays(
    tmp_path: Path,
) -> None:
    cassette_path = tmp_path / "groq_async_recording.jsonl"
    api = AsyncFakeGroqAPI()

    recorder = wrap_groq_client(
        AsyncGroq(api_key="fake-api-key"),
        cassette_path,
        mode="record",
    )

    replayer = None

    try:
        recorder._client._transport.real_transport = api

        recorded = await recorder.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "Say hello"},
            ],
        )

        assert recorded.choices[0].message.content == "Hello from Groq"
        assert recorded.usage.total_tokens == 9
        assert len(api.calls) == 1
        assert cassette_path.exists()

        # Validate the recorded request.
        sent = json.loads(api.calls[0].content)

        assert sent["model"] == "llama-3.3-70b-versatile"
        assert sent["messages"] == [{"role": "user", "content": "Say hello"}]

        # Replay the previously recorded interaction.
        replayer = wrap_groq_client(
            AsyncGroq(api_key="fake-api-key"),
            cassette_path,
            mode="replay",
        )

        replayer._client._transport.real_transport = api

        replayed = await replayer.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": "Say hello"},
            ],
        )

        assert replayed.choices[0].message.content == "Hello from Groq"
        assert replayed.usage.total_tokens == 9

        # Replay must not call the API again.
        assert len(api.calls) == 1

    finally:
        await recorder.close()

        if replayer is not None:
            await replayer.close()


# ---------------------------------------------------------
# Test 5: Verify public package export
# ---------------------------------------------------------


def test_wrap_groq_client_is_exported() -> None:
    import rerunner.integrations as integrations

    assert "wrap_groq_client" in integrations.__all__
    assert callable(integrations.wrap_groq_client)
