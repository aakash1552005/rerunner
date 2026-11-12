"""Unit tests for Rerunner provider adapters and unified `rerunner.wrap`."""

from __future__ import annotations

from typing import Any
import httpx
import pytest

from rerunner import wrap
from rerunner.integrations.base import (
    get_registered_adapters,
    register_adapter,
)


def test_registered_adapters_discovered():
    """Verify built-in adapters are properly registered in the default registry."""
    adapters = get_registered_adapters()
    adapter_names = [a.adapter_name for a in adapters]
    assert "openai" in adapter_names
    assert "anthropic" in adapter_names
    assert "google_genai" in adapter_names
    assert "bedrock" in adapter_names
    assert "cohere" in adapter_names
    assert "langchain" in adapter_names
    assert "autogen" in adapter_names
    assert "semantic_kernel" in adapter_names
    assert "httpx" in adapter_names


def test_wrap_cohere_adapter_auto_detection(tmp_path):
    """Verify CohereAdapter is auto-selected by unified rerunner.wrap()."""

    class FakeHttpxWrapper:
        def __init__(self):
            self.httpx_client = httpx.Client()

    class FakeClientWrapper:
        def __init__(self):
            self.httpx_client = FakeHttpxWrapper()

    class FakeCohereClient:
        def __init__(self):
            self._client_wrapper = FakeClientWrapper()

    client = FakeCohereClient()
    cassette_file = tmp_path / "cohere_wrap.jsonl"
    wrapped = wrap(client, cassette_file, mode="record")

    assert wrapped is client
    inner_http = client._client_wrapper.httpx_client.httpx_client
    assert str(inner_http._transport.cassette_path) == str(cassette_file)


def test_wrap_sync_httpx_client(tmp_path):
    """Test unified wrap with standard sync httpx.Client."""
    cassette_file = tmp_path / "sync_httpx.jsonl"
    client = httpx.Client()
    wrapped = wrap(client, cassette_file, mode="record")

    assert wrapped is client
    assert hasattr(client._transport, "cassette_path")
    assert str(client._transport.cassette_path) == str(cassette_file)


def test_wrap_async_httpx_client(tmp_path):
    """Test unified wrap with async httpx.AsyncClient."""
    cassette_file = tmp_path / "async_httpx.jsonl"
    client = httpx.AsyncClient()
    wrapped = wrap(client, cassette_file, mode="record")

    assert wrapped is client
    assert hasattr(client._transport, "cassette_path")
    assert str(client._transport.cassette_path) == str(cassette_file)


def test_wrap_custom_provider_adapter(tmp_path):
    """Test registering a custom provider adapter and wrapping via unified API."""

    class MockCustomClient:
        def __init__(self):
            self.wrapped = False
            self.mode = None
            self.cassette = None

    class CustomModelAdapter:
        adapter_name = "mock_provider"

        @classmethod
        def can_wrap(cls, client: Any) -> bool:
            return isinstance(client, MockCustomClient)

        @classmethod
        def wrap(cls, client: Any, cassette_path: Any, mode: str = "replay", **kwargs: Any) -> Any:
            client.wrapped = True
            client.mode = mode
            client.cassette = cassette_path
            return client

    register_adapter(CustomModelAdapter)

    client = MockCustomClient()
    cassette_file = tmp_path / "custom_cassette.jsonl"
    wrapped = wrap(client, cassette_file, mode="replay")

    assert wrapped is client
    assert wrapped.wrapped is True
    assert wrapped.mode == "replay"
    assert wrapped.cassette == cassette_file


def test_wrap_unsupported_client_raises_type_error(tmp_path):
    """Test that wrapping an unwrapable object raises a descriptive TypeError."""

    class UnknownWidget:
        pass

    with pytest.raises(
        TypeError, match="Unable to auto-detect adapter for client type 'UnknownWidget'"
    ):
        wrap(UnknownWidget(), tmp_path / "err.jsonl")
