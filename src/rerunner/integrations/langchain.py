"""LangChain and LangGraph callback integration for step recording and observability."""

from __future__ import annotations

from typing import Any
from rerunner.side_effects import set_active_cassette

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
        self.ignore_llm = False
        self.ignore_chain = False
        self.ignore_agent = False
        self.ignore_chat_model = False
        self.ignore_retriever = False
        self.ignore_custom_event = False
        self.raise_error = False
        set_active_cassette(cassette_path, mode=mode, fork_step=fork_step)

    def on_llm_start(self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any) -> None:
        """Invoked when an LLM call begins in a LangChain chain."""
        self.step_count += 1

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Invoked when a tool executes in an agent workflow."""
        self.step_count += 1

    def on_chain_end(self, outputs: dict[str, Any], **kwargs: Any) -> None:
        """Invoked when a chain completes execution."""
        pass
