"""Unit tests for LangGraph checkpointer and deterministic graph replay."""

from __future__ import annotations

import pytest

from rerunner.integrations.langgraph import RerunnerCheckpointer, wrap_langgraph_graph


def test_langgraph_checkpointer_record_and_replay(tmp_path):
    cassette_file = tmp_path / "langgraph_run.jsonl"

    # Phase 1: Record Mode
    checkpointer = RerunnerCheckpointer(cassette_path=cassette_file, mode="record")

    config = {
        "configurable": {
            "thread_id": "thread_abc_123",
            "checkpoint_ns": "agent_subgraph",
            "checkpoint_id": "chk_step_1",
        }
    }
    checkpoint = {
        "id": "chk_step_1",
        "channel_values": {"messages": ["User query", "Agent plan"], "step": 1},
    }
    metadata = {"source": "loop", "step": 1}
    new_versions = {"messages": 1}

    # Put checkpoint
    res = checkpointer.put(config, checkpoint, metadata, new_versions)
    assert res == config
    assert cassette_file.exists()

    # Get tuple
    retrieved = checkpointer.get_tuple(config)
    assert retrieved is not None
    assert retrieved["checkpoint"]["id"] == "chk_step_1"
    assert retrieved["checkpoint"]["channel_values"]["step"] == 1

    # Phase 2: Replay Mode (from tape)
    replayer = RerunnerCheckpointer(cassette_path=cassette_file, mode="replay")
    replayed = replayer.get_tuple(config)

    assert replayed is not None
    assert replayed["checkpoint"]["id"] == "chk_step_1"
    assert replayed["checkpoint"]["channel_values"]["messages"] == ["User query", "Agent plan"]


@pytest.mark.asyncio
async def test_langgraph_checkpointer_async_methods(tmp_path):
    cassette_file = tmp_path / "async_langgraph.jsonl"
    checkpointer = RerunnerCheckpointer(cassette_path=cassette_file, mode="record")

    config = {"configurable": {"thread_id": "thread_async", "checkpoint_id": "chk_async_1"}}
    checkpoint = {"id": "chk_async_1", "state": "done"}

    await checkpointer.aput(config, checkpoint, {}, {})
    retrieved = await checkpointer.aget_tuple(config)

    assert retrieved is not None
    assert retrieved["checkpoint"]["state"] == "done"

    items = [item async for item in checkpointer.alist()]
    assert len(items) == 1


def test_wrap_langgraph_graph_attaches_checkpointer(tmp_path):
    class MockGraph:
        def __init__(self):
            self.checkpointer = None

    graph = MockGraph()
    wrapped = wrap_langgraph_graph(graph, tmp_path / "test.jsonl", mode="replay")

    assert wrapped is graph
    assert isinstance(graph.checkpointer, RerunnerCheckpointer)
    assert graph.checkpointer.mode == "replay"
