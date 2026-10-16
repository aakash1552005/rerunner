"""Tests for LlamaIndex callback integration."""

from __future__ import annotations

from pathlib import Path
from rerunner.integrations.llamaindex import LlamaIndexRerunnerHandler


def test_llamaindex_handler_init(tmp_path: Path) -> None:
    cassette = tmp_path / "test_llamaindex.jsonl"
    handler = LlamaIndexRerunnerHandler(str(cassette), mode="record")

    assert handler.cassette_path == str(cassette)
    assert handler.mode == "record"
    assert handler.event_count == 0


def test_llamaindex_events(tmp_path: Path) -> None:
    cassette = tmp_path / "test_llamaindex_events.jsonl"
    handler = LlamaIndexRerunnerHandler(str(cassette), mode="record")

    event_id = handler.on_event_start(
        event_type="llm",
        payload={"messages": ["Hello"]},
        event_id="evt-123",
    )
    assert event_id == "evt-123"
    assert handler.event_count == 1

    handler.on_event_end(
        event_type="llm",
        payload={"response": "World"},
        event_id="evt-123",
    )
    assert handler.event_count == 1
