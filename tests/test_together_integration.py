"""Tests for the Together AI SDK wrapper (wrap_together_client)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.integrations import wrap_together_client
from rerunner.transport import CassetteTransport

CHAT_RESPONSE = {
    "id": "chatcmpl-together-1",
    "choices": [{"message": {"role": "assistant", "content": "Hello from Together"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
}


class TogetherAPI(httpx.BaseTransport):
    """Stands in for api.together.xyz and counts live calls."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, json=CHAT_RESPONSE, request=request)


class AsyncTogetherAPI(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, json=CHAT_RESPONSE, request=request)


# ---- shape of the Together SDK client, without the SDK installed ---------------


class FakeTogetherClient:
    def __init__(self, inner: httpx.Client | httpx.AsyncClient) -> None:
        self._client = inner


class AsyncFakeTogetherClient:
    def __init__(self, inner: httpx.AsyncClient) -> None:
        self._client = inner


def test_wrap_together_client_sync_shape(temp_cassette_path: Path) -> None:
    inner = httpx.Client(
        base_url="https://api.together.xyz/v1",
        headers={"Authorization": "Bearer test-key"},
        mounts={"https://": httpx.HTTPTransport()},
    )
    client = FakeTogetherClient(inner)
    wrapped = wrap_together_client(client, temp_cassette_path, mode="record")

    assert wrapped is client
    assert isinstance(wrapped._client._transport, CassetteTransport)
    assert wrapped._client._transport.mode == "record"
    assert str(wrapped._client.base_url).rstrip("/") == "https://api.together.xyz/v1"
    assert wrapped._client.headers["Authorization"] == "Bearer test-key"
    assert not wrapped._client._mounts  # an HTTPS_PROXY mount would bypass the cassette


def test_wrap_together_client_async_shape(temp_cassette_path: Path) -> None:
    client = AsyncFakeTogetherClient(httpx.AsyncClient(base_url="https://api.together.xyz/v1"))
    wrapped = wrap_together_client(client, temp_cassette_path, mode="replay")

    assert isinstance(wrapped._client, httpx.AsyncClient)
    assert isinstance(wrapped._client._transport, AsyncCassetteTransport)
    assert wrapped._client._transport.mode == "replay"
    assert str(wrapped._client.base_url).rstrip("/") == "https://api.together.xyz/v1"


def test_wrap_together_client_is_exported_from_integrations() -> None:
    import rerunner.integrations as integrations

    assert "wrap_together_client" in integrations.__all__


# ---- the real Together SDK -----------------------------------------------------


def test_together_chat_records_then_replays_offline(temp_cassette_path: Path) -> None:
    together = pytest.importorskip("together")
    api = TogetherAPI()

    recorder = wrap_together_client(
        together.Together(api_key="test-key"), temp_cassette_path, mode="record"
    )
    recorder._client._transport.real_transport = api
    recorded = recorder.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.2,
    )
    assert recorded.choices[0].message.content == "Hello from Together"
    assert len(api.calls) == 1
    sent = json.loads(api.calls[0].content)
    assert sent["model"] == "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    assert sent["messages"] == [{"role": "user", "content": "Say hello"}]
    assert temp_cassette_path.exists()

    # A fresh client in replay mode answers from the cassette with no live call.
    replayer = wrap_together_client(
        together.Together(api_key="test-key"), temp_cassette_path, mode="replay"
    )
    replayer._client._transport.real_transport = api
    replayed = replayer.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.2,
    )
    assert replayed.choices[0].message.content == "Hello from Together"
    assert replayed.usage.total_tokens == 9
    assert len(api.calls) == 1


async def test_together_async_chat_records_then_replays(temp_cassette_path: Path) -> None:
    together = pytest.importorskip("together")
    api = AsyncTogetherAPI()

    recorder = wrap_together_client(
        together.AsyncTogether(api_key="test-key"), temp_cassette_path, mode="record"
    )
    recorder._client._transport.real_transport = api
    recorded = await recorder.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[{"role": "user", "content": "Say hello"}],
    )
    assert recorded.choices[0].message.content == "Hello from Together"
    assert len(api.calls) == 1

    replayer = wrap_together_client(
        together.AsyncTogether(api_key="test-key"), temp_cassette_path, mode="replay"
    )
    replayer._client._transport.real_transport = api
    replayed = await replayer.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        messages=[{"role": "user", "content": "Say hello"}],
    )
    assert replayed.choices[0].message.content == "Hello from Together"
    assert len(api.calls) == 1
