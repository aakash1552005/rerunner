"""LangChain and LangGraph callback integration for step recording and observability."""

from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING, Any
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
