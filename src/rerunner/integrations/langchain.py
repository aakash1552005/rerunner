"""LangChain and LangGraph callback integration for step recording and observability."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any, Literal
from rerunner.side_effects import reset_active_cassette, set_active_cassette

if TYPE_CHECKING:
    from rerunner.cassette import Cassette

try:
    from langchain_core.callbacks.base import BaseCallbackHandler
except ImportError:  # pragma: no cover

    class BaseCallbackHandler:  # type: ignore[no-redef]
        """Fallback callback handler base when langchain-core is not installed."""

        raise_error: bool = False
        ignore_llm: bool = False
        ignore_chain: bool = False
        ignore_agent: bool = False
        ignore_retriever: bool = False
        ignore_chat_model: bool = False
        ignore_custom_event: bool = False


class RerunnerCallbackHandler(BaseCallbackHandler):  # type: ignore[misc]
    """Callback handler compatible with LangChain, LangGraph, and CrewAI pipelines."""

    def __init__(
        self, cassette_path: str, mode: str = "replay", fork_step: int | None = None
    ) -> None:
        super().__init__()
        self.cassette_path = cassette_path
        self.mode = mode
        self.fork_step = fork_step
        self.step_count = 0
        self._token: contextvars.Token[Cassette | None] | None = set_active_cassette(
            cassette_path, mode=mode, fork_step=fork_step
        )

    def __enter__(self) -> RerunnerCallbackHandler:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Reset the active cassette ContextVar token to avoid leaking state across tests."""
        if hasattr(self, "_token") and self._token is not None:
            reset_active_cassette(self._token)
            self._token = None

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Invoked when an LLM call begins in a LangChain chain."""
        self.step_count += 1

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Invoked when a tool executes in an agent workflow."""
        self.step_count += 1

    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Invoked when a chain completes execution."""
        pass


def wrap_langchain_model(
    model: Any,
    cassette_path: str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach Rerunner cassette transports directly to a LangChain ChatModel or LLM instance.

    Works across `ChatOpenAI`, `ChatAnthropic`, `ChatGoogleGenerativeAI`, and custom models
    with `http_client` or `http_async_client` attributes.

    Example:
        from langchain_openai import ChatOpenAI
        from rerunner.integrations.langchain import wrap_langchain_model

        llm = wrap_langchain_model(ChatOpenAI(model="gpt-4o"), "cassettes/langchain.jsonl", mode="replay")
        result = llm.invoke("Hello agent")
    """
    from rerunner.async_transport import AsyncCassetteTransport
    from rerunner.transport import CassetteTransport
    import httpx

    sync_transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)
    async_transport = AsyncCassetteTransport(
        cassette_path=cassette_path, mode=mode, fork_step=fork_step
    )

    # Patch sync client if present
    if hasattr(model, "http_client"):
        if model.http_client is None:
            model.http_client = httpx.Client(transport=sync_transport)
        elif isinstance(model.http_client, httpx.Client):
            model.http_client._transport = sync_transport
            if hasattr(model.http_client, "_mounts"):
                model.http_client._mounts.clear()

    # Patch async client if present
    if hasattr(model, "http_async_client"):
        if model.http_async_client is None:
            model.http_async_client = httpx.AsyncClient(transport=async_transport)
        elif isinstance(model.http_async_client, httpx.AsyncClient):
            model.http_async_client._transport = async_transport
            if hasattr(model.http_async_client, "_mounts"):
                model.http_async_client._mounts.clear()

    # Check root client
    if hasattr(model, "client") and hasattr(model.client, "_client"):
        if isinstance(model.client._client, httpx.Client):
            model.client._client._transport = sync_transport
        elif isinstance(model.client._client, httpx.AsyncClient):
            model.client._client._transport = async_transport

    return model
