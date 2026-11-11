"""Tests for the Cohere SDK wrapper (wrap_cohere / wrap_cohere_client)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from rerunner.async_transport import AsyncCassetteTransport
from rerunner import wrap
from rerunner.integrations import wrap_cohere, wrap_cohere_client
from rerunner.transport import CassetteTransport

CHAT_RESPONSE = {
    "id": "chat-test-1",
    "finish_reason": "COMPLETE",
    "message": {"role": "assistant", "content": [{"type": "text", "text": "Hello from Cohere"}]},
    "usage": {
        "billed_units": {"input_tokens": 5, "output_tokens": 4},
        "tokens": {"input_tokens": 70, "output_tokens": 4},
    },
}


class CohereAPI(httpx.BaseTransport):
    """Stands in for api.cohere.com and counts live calls."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, json=CHAT_RESPONSE, request=request)


class AsyncCohereAPI(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(200, json=CHAT_RESPONSE, request=request)


# ---- shape of the Cohere SDK client, without the SDK installed ---------------


class _HttpClient:
    def __init__(self, inner: httpx.Client | httpx.AsyncClient) -> None:
        self.httpx_client = inner


class _ClientWrapper:
    def __init__(self, inner: httpx.Client | httpx.AsyncClient) -> None:
        self.httpx_client = _HttpClient(inner)


class FakeCohereClient:
    def __init__(self, inner: httpx.Client | httpx.AsyncClient) -> None:
        self._client_wrapper = _ClientWrapper(inner)


def _inner(client: Any) -> Any:
    return client._client_wrapper.httpx_client.httpx_client


def test_wrap_cohere_sync_client_shape(temp_cassette_path: Path) -> None:
    inner = httpx.Client(mounts={"https://": httpx.HTTPTransport()})
    client = FakeCohereClient(inner)
    wrapped = wrap_cohere(client, temp_cassette_path, mode="record")

    assert wrapped is client
    assert _inner(wrapped) is inner  # patched in place, settings kept
    assert isinstance(inner._transport, CassetteTransport)
    assert inner._transport.mode == "record"
    assert not inner._mounts  # an HTTPS_PROXY mount would bypass the cassette


def test_wrap_cohere_async_client_shape(temp_cassette_path: Path) -> None:
    inner = httpx.AsyncClient()
    wrapped = wrap_cohere(FakeCohereClient(inner), temp_cassette_path, mode="replay")
    assert isinstance(_inner(wrapped)._transport, AsyncCassetteTransport)


def test_wrap_cohere_client_alias() -> None:
    assert wrap_cohere_client is wrap_cohere


@pytest.mark.parametrize("name", ["Client", "ClientV2", "AsyncClient", "AsyncClientV2"])
@pytest.mark.parametrize("use_sdk", [False, True], ids=["fake", "sdk"])
async def test_unified_wrap_cohere_client(
    name: str, use_sdk: bool, temp_cassette_path: Path
) -> None:
    client_type = type(name, (FakeCohereClient,), {"__module__": "cohere.client"})
    is_async = name.startswith("Async")
    inner = httpx.AsyncClient() if is_async else httpx.Client()
    if use_sdk:
        cohere = pytest.importorskip("cohere")
        client = getattr(cohere, name)(api_key="test-key", httpx_client=inner)
    else:
        client = client_type(inner)
    try:
        assert wrap(client, temp_cassette_path, mode="fork", fork_step=2) is client
        expected = AsyncCassetteTransport if is_async else CassetteTransport
        assert isinstance(inner._transport, expected)
        assert inner._transport.cassette_path == temp_cassette_path
        assert inner._transport.mode == "fork"
        assert inner._transport.fork_step == 2
        assert not inner._mounts
    finally:
        if isinstance(inner, httpx.AsyncClient):
            await inner.aclose()
        else:
            inner.close()


def test_unified_wrap_does_not_accept_unrelated_client(temp_cassette_path: Path) -> None:
    client_type = type("Client", (), {"__module__": "not_cohere.client"})
    with pytest.raises(TypeError, match="Unable to auto-detect adapter"):
        wrap(client_type(), temp_cassette_path)


def test_import_does_not_load_cohere_sdk() -> None:
    subprocess.run(
        [sys.executable, "-c", "import sys; import rerunner; assert 'cohere' not in sys.modules"],
        check=True,
    )


@pytest.mark.parametrize("client", [object(), httpx.Client(), FakeCohereClient(None)])  # type: ignore[arg-type]
def test_wrap_cohere_rejects_other_clients(client: Any, temp_cassette_path: Path) -> None:
    with pytest.raises(TypeError, match="wrap_cohere expects a cohere"):
        wrap_cohere(client, temp_cassette_path)


def test_wrap_cohere_is_exported_from_integrations() -> None:
    import rerunner.integrations as integrations

    assert "wrap_cohere" in integrations.__all__
    assert "wrap_cohere_client" in integrations.__all__


# ---- the real Cohere SDK -----------------------------------------------------


@pytest.mark.parametrize("wrapper", [wrap_cohere, wrap])
def test_cohere_v2_chat_records_then_replays_offline(
    temp_cassette_path: Path, wrapper: Any
) -> None:
    cohere = pytest.importorskip("cohere")
    api = CohereAPI()

    recorder = wrapper(cohere.ClientV2(api_key="test-key"), temp_cassette_path, mode="record")
    _inner(recorder)._transport.real_transport = api
    recorded = recorder.chat(
        model="command-a-03-2025",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.2,
    )
    assert recorded.message.content[0].text == "Hello from Cohere"
    assert len(api.calls) == 1
    sent = json.loads(api.calls[0].content)
    assert sent["model"] == "command-a-03-2025"
    assert sent["messages"] == [{"role": "user", "content": "Say hello"}]
    assert temp_cassette_path.exists()

    # A fresh client in replay mode answers from the cassette with no live call.
    replayer = wrapper(cohere.ClientV2(api_key="test-key"), temp_cassette_path, mode="replay")
    _inner(replayer)._transport.real_transport = api
    replayed = replayer.chat(
        model="command-a-03-2025",
        messages=[{"role": "user", "content": "Say hello"}],
        temperature=0.2,
    )
    assert replayed.message.content[0].text == "Hello from Cohere"
    assert replayed.usage.billed_units.output_tokens == 4
    assert len(api.calls) == 1


def test_cohere_v1_client_v2_namespace_is_covered(temp_cassette_path: Path) -> None:
    cohere = pytest.importorskip("cohere")
    api = CohereAPI()
    client = wrap_cohere(cohere.Client(api_key="test-key"), temp_cassette_path, mode="record")
    _inner(client)._transport.real_transport = api

    resp = client.v2.chat(model="command-a-03-2025", messages=[{"role": "user", "content": "hi"}])
    assert resp.message.content[0].text == "Hello from Cohere"
    assert len(api.calls) == 1


@pytest.mark.parametrize("wrapper", [wrap_cohere, wrap])
async def test_cohere_async_v2_chat_records_then_replays(
    temp_cassette_path: Path, wrapper: Any
) -> None:
    cohere = pytest.importorskip("cohere")
    api = AsyncCohereAPI()

    recorder = wrapper(cohere.AsyncClientV2(api_key="test-key"), temp_cassette_path, mode="record")
    _inner(recorder)._transport.real_transport = api
    recorded = await recorder.chat(
        model="command-a-03-2025", messages=[{"role": "user", "content": "Say hello"}]
    )
    assert recorded.message.content[0].text == "Hello from Cohere"
    assert len(api.calls) == 1

    replayer = wrapper(cohere.AsyncClientV2(api_key="test-key"), temp_cassette_path, mode="replay")
    _inner(replayer)._transport.real_transport = api
    replayed = await replayer.chat(
        model="command-a-03-2025", messages=[{"role": "user", "content": "Say hello"}]
    )
    assert replayed.message.content[0].text == "Hello from Cohere"
    assert len(api.calls) == 1
