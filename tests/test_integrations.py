"""Unit tests for official framework adapters and wrappers."""

from __future__ import annotations

import httpx
from pathlib import Path
from rerunner.integrations.anthropic import wrap_anthropic
from rerunner.integrations.langchain import RerunnerCallbackHandler
from rerunner.integrations.openai import wrap_openai


class DummyClient:
    def __init__(self) -> None:
        self._client = httpx.Client()


def test_wrap_anthropic(temp_cassette_path: Path) -> None:
    client = DummyClient()
    wrapped = wrap_anthropic(client, temp_cassette_path, mode="record")
    assert hasattr(wrapped._client, "_transport")


def test_wrap_openai(temp_cassette_path: Path) -> None:
    client = DummyClient()
    wrapped = wrap_openai(client, temp_cassette_path, mode="record")
    assert hasattr(wrapped._client, "_transport")


def test_wrap_google_genai(temp_cassette_path: Path) -> None:
    from rerunner.integrations.google import wrap_gemini, wrap_google_genai, wrap_vertexai

    # Test with standard _client attribute
    client = DummyClient()
    wrapped = wrap_google_genai(client, temp_cassette_path, mode="record")
    assert hasattr(wrapped._client, "_transport")

    # Test with custom client having http_client attribute
    class CustomGenAIClient:
        def __init__(self) -> None:
            self.http_client = httpx.Client()

    custom_client = CustomGenAIClient()
    wrapped_custom = wrap_vertexai(custom_client, temp_cassette_path, mode="replay")
    assert hasattr(wrapped_custom.http_client, "_transport")

    # Test alias wrap_gemini
    client_gemini = DummyClient()
    wrapped_gemini = wrap_gemini(client_gemini, temp_cassette_path, mode="replay")
    assert hasattr(wrapped_gemini._client, "_transport")


def test_langchain_callback_handler(temp_cassette_path: Path) -> None:
    handler = RerunnerCallbackHandler(str(temp_cassette_path), mode="record")
    handler.on_llm_start({}, ["Write code"])
    handler.on_tool_start({}, "Search web")
    assert handler.step_count == 2
    handler.close()


def test_wrap_google_genai_async(temp_cassette_path: Path) -> None:
    from rerunner.async_transport import AsyncCassetteTransport
    from rerunner.integrations.google import wrap_google_genai
    from rerunner.transport import CassetteTransport

    class AsyncSubClient:
        def __init__(self) -> None:
            self._client = httpx.AsyncClient()

    class DualClient:
        def __init__(self) -> None:
            self._client = httpx.Client()
            self.aio = AsyncSubClient()
            self._async_httpx_client = httpx.AsyncClient()

    client = DualClient()
    wrapped = wrap_google_genai(client, temp_cassette_path, mode="replay")

    assert isinstance(wrapped._client._transport, CassetteTransport)
    assert isinstance(wrapped.aio._client._transport, AsyncCassetteTransport)
    assert isinstance(wrapped._async_httpx_client._transport, AsyncCassetteTransport)

    # Direct AsyncClient
    direct_async = httpx.AsyncClient()
    wrapped_direct = wrap_google_genai(direct_async, temp_cassette_path, mode="replay")
    assert isinstance(wrapped_direct._transport, AsyncCassetteTransport)


def test_callback_handlers_context_manager_and_cleanup(temp_cassette_path: Path) -> None:
    from rerunner.integrations.llamaindex import LlamaIndexRerunnerHandler
    from rerunner.side_effects import get_active_cassette

    assert get_active_cassette() is None

    # LangChain context manager cleanup
    with RerunnerCallbackHandler(str(temp_cassette_path), mode="record") as handler:
        assert get_active_cassette() is not None
        handler.on_llm_start({}, ["prompt"])
        assert handler.step_count == 1

    assert get_active_cassette() is None

    # LlamaIndex context manager cleanup
    with LlamaIndexRerunnerHandler(str(temp_cassette_path), mode="record") as llama_h:
        assert get_active_cassette() is not None
        llama_h.on_event_start("llm")
        assert llama_h.event_count == 1

    assert get_active_cassette() is None


def test_wrap_bedrock_client(temp_cassette_path: Path) -> None:
    from rerunner.integrations.bedrock import mock_bedrock_converse_response, wrap_bedrock_client

    client = DummyClient()
    wrapped = wrap_bedrock_client(client, temp_cassette_path, mode="record")
    assert hasattr(wrapped._client, "_transport")

    mock_resp = mock_bedrock_converse_response(
        text="All tests passed deterministically.", input_tokens=10, output_tokens=20
    )
    assert (
        mock_resp["output"]["message"]["content"][0]["text"]
        == "All tests passed deterministically."
    )
    assert mock_resp["usage"]["totalTokens"] == 30
    assert mock_resp["stopReason"] == "end_turn"
