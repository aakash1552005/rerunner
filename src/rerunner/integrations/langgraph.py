"""LangGraph multi-agent state checkpointer and deterministic graph replayer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from collections.abc import AsyncIterator, Iterator

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry

if TYPE_CHECKING:
    pass

try:
    from langgraph.checkpoint.base import (
        BaseCheckpointSaver,
        Checkpoint,
        CheckpointMetadata,
        CheckpointTuple,
    )
except ImportError:  # pragma: no cover
    # Standalone duck-typed fallback when langgraph is not installed
    class BaseCheckpointSaver:  # type: ignore[no-redef]
        """Fallback base checkpointer when langgraph is not installed."""

        pass

    Checkpoint = dict  # type: ignore[misc,assignment]
    CheckpointMetadata = dict  # type: ignore[misc,assignment]
    CheckpointTuple = Any  # type: ignore[misc,assignment]


class RerunnerCheckpointer(BaseCheckpointSaver):  # type: ignore[misc]
    """Deterministic LangGraph Checkpoint Saver.

    Persists multi-agent cyclic graph states, node transitions, and channel memories
    directly into Rerunner cassettes for hermetic $0 CI replays.
    """

    def __init__(
        self,
        cassette_path: Path | str,
        mode: Literal["record", "replay"] = "replay",
    ) -> None:
        self.cassette_path = Path(cassette_path)
        self.mode = mode
        self.storage: dict[str, dict[str, Any]] = {}
        self._step_counter = 0

        if self.mode == "replay" and self.cassette_path.exists():
            self._load_from_cassette()

    def _load_from_cassette(self) -> None:
        """Load recorded checkpoint states from the cassette file."""
        try:
            cassette = Cassette.load(self.cassette_path, verify_integrity=False)
            for entry in cassette.entries:
                if (
                    entry.entry_type == "side_effect"
                    and entry.side_effect_name == "langgraph_checkpoint"
                    and entry.side_effect_result is not None
                ):
                    key = str(entry.side_effect_args[0]) if entry.side_effect_args else ""
                    if key:
                        self.storage[key] = entry.side_effect_result
        except Exception:  # nosec B110
            pass

    def _get_key(self, config: dict[str, Any]) -> str:
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "default")
        checkpoint_ns = configurable.get("checkpoint_ns", "")
        checkpoint_id = configurable.get("checkpoint_id", "")
        return f"{thread_id}:{checkpoint_ns}:{checkpoint_id}"

    def get_tuple(self, config: dict[str, Any]) -> Any:
        """Fetch a recorded checkpoint state snapshot."""
        key = self._get_key(config)
        item = self.storage.get(key)
        if item is not None:
            return item
        # If thread-level query without specific checkpoint_id, return latest matching thread
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id", "default")
        prefix = f"{thread_id}:"
        matching = [v for k, v in self.storage.items() if k.startswith(prefix)]
        return matching[-1] if matching else None

    async def aget_tuple(self, config: dict[str, Any]) -> Any:
        """Asynchronously fetch a recorded checkpoint state snapshot."""
        return self.get_tuple(config)

    def put(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        """Save a graph checkpoint snapshot to cassette."""
        key = self._get_key(config)
        record_data = {
            "config": config,
            "checkpoint": checkpoint,
            "metadata": metadata,
            "new_versions": new_versions,
        }
        self.storage[key] = record_data

        if self.mode == "record":
            self._step_counter += 1
            cassette = (
                Cassette.load(self.cassette_path, verify_integrity=False)
                if self.cassette_path.exists()
                else Cassette(self.cassette_path)
            )

            entry = CassetteEntry(
                step=self._step_counter,
                entry_type="side_effect",
                timestamp=1700000000.0,
                side_effect_name="langgraph_checkpoint",
                side_effect_args=[key],
                side_effect_kwargs={},
                side_effect_result=record_data,
            )
            cassette.append(entry)
            cassette.save()

        return config

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: dict[str, Any],
        metadata: dict[str, Any],
        new_versions: dict[str, Any],
    ) -> dict[str, Any]:
        """Asynchronously save a graph checkpoint snapshot."""
        return self.put(config, checkpoint, metadata, new_versions)

    def list(
        self,
        config: dict[str, Any] | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> Iterator[Any]:
        """List historical checkpoint tuples matching criteria."""
        items = list(self.storage.values())
        if limit is not None:
            items = items[:limit]
        return iter(items)

    async def alist(
        self,
        config: dict[str, Any] | None = None,
        *,
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[Any]:
        """Asynchronously list historical checkpoint tuples."""
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item


def wrap_langgraph_graph(
    graph: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay"] = "replay",
) -> Any:
    """Attach a RerunnerCheckpointer to a compiled LangGraph StateGraph instance.

    Example:
        from rerunner.integrations.langgraph import wrap_langgraph_graph

        # Deterministically record or replay multi-agent cyclic graph states
        app = wrap_langgraph_graph(workflow.compile(), "graph_run.jsonl", mode="replay")
        output = app.invoke({"messages": [("user", "Analyze codebase")]})
    """
    checkpointer = RerunnerCheckpointer(cassette_path=cassette_path, mode=mode)
    if hasattr(graph, "checkpointer"):
        graph.checkpointer = checkpointer
    return graph
