"""Unit tests for the fork-from-step execution engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import httpx
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def test_fork_replays_past_and_executes_new_live(
    temp_cassette_path: Path, mock_transport: Any
) -> None:
    mock = mock_transport

    # Step 1 & 2 recorded initially
    transport_rec = CassetteTransport(
        cassette_path=temp_cassette_path, mode="record", real_transport=mock
    )
    with httpx.Client(transport=transport_rec) as client:
        client.post("https://api.openai.com/v1/chat/completions", json={"step": 1})
        client.post("https://api.openai.com/v1/chat/completions", json={"step": 2})

    assert mock.call_count == 2

    # Now Fork at Step 1: Step 1 should be replayed from cassette, Step 2 should hit network live
    transport_fork = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="fork",
        fork_step=1,
        real_transport=mock,
    )
    with httpx.Client(transport=transport_fork) as client:
        # Step 1: Replayed (no extra live call)
        client.post("https://api.openai.com/v1/chat/completions", json={"step": 1})
        assert mock.call_count == 2

        # Step 2: Live execution because step > fork_step
        client.post(
            "https://api.openai.com/v1/chat/completions", json={"step": 2, "new_prompt": "updated"}
        )
        assert mock.call_count == 3
