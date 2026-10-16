"""LlamaIndex callback integration for deterministic cassette recording and offline replay."""

from __future__ import annotations

from typing import Any
from rerunner.side_effects import set_active_cassette

try:
    from llama_index.core.callbacks.base_handler import BaseCallbackHandler
except ImportError:
    # Graceful fallback when llama-index-core is not installed
    class BaseCallbackHandler:  # type: ignore[no-redef]
        def __init__(
            self,
            event_starts_to_ignore: list[Any] | None = None,
            event_ends_to_ignore: list[Any] | None = None,
        ) -> None:
            self.event_starts_to_ignore = event_starts_to_ignore or []
            self.event_ends_to_ignore = event_ends_to_ignore or []


class LlamaIndexRerunnerHandler(BaseCallbackHandler):
    """Callback handler compatible with LlamaIndex query engines, agents, and RAG pipelines."""

    def __init__(
        self,
        cassette_path: str,
        mode: str = "replay",
        fork_step: int | None = None,
        event_starts_to_ignore: list[Any] | None = None,
        event_ends_to_ignore: list[Any] | None = None,
    ) -> None:
        super().__init__(
            event_starts_to_ignore=event_starts_to_ignore or [],
            event_ends_to_ignore=event_ends_to_ignore or [],
        )
        self.cassette_path = cassette_path
        self.mode = mode
        self.fork_step = fork_step
        self.event_count = 0
        set_active_cassette(cassette_path, mode=mode, fork_step=fork_step)

    def on_event_start(
        self,
        event_type: Any,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        parent_id: str = "",
        **kwargs: Any,
    ) -> str:
        """Invoked when a LlamaIndex event (LLM, Embedding, Query, Retrieve) starts."""
        self.event_count += 1
        return event_id

    def on_event_end(
        self,
        event_type: Any,
        payload: dict[str, Any] | None = None,
        event_id: str = "",
        **kwargs: Any,
    ) -> None:
        """Invoked when a LlamaIndex event completes."""
        pass

    def start_trace(self, trace_id: str | None = None) -> None:
        """Invoked when a trace starts."""
        pass

    def end_trace(
        self,
        trace_id: str | None = None,
        trace_map: dict[str, list[str]] | None = None,
    ) -> None:
        """Invoked when a trace ends."""
        pass
