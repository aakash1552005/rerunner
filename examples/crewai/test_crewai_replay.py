"""Runnable pytest test demonstrating deterministic replay of a CrewAI multi-agent workflow."""

from __future__ import annotations

import os
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

from pathlib import Path
import httpx
import pytest

from rerunner import Session


def test_crewai_multi_agent_deterministic_replay(tmp_path: Path) -> None:
    """Verify that a multi-agent workflow (Researcher + Writer) records and replays offline."""
    cassette_file = tmp_path / "crewai_replay.zst"

    # Simulated backend returns unique responses per agent step
    class MockCrewAIServer(httpx.BaseTransport):
        def __init__(self) -> None:
            self.calls = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            content = f"Agent step {self.calls} complete."
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "id": f"chatcmpl-{self.calls}",
                    "choices": [{"message": {"role": "assistant", "content": content}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                },
            )

    # 1. Record Mode
    with Session(cassette_path=cassette_file, mode="record") as session:
        session.transport.real_transport = MockCrewAIServer()
        client = session.get_client()

        res1 = client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Researcher step"}]},
        )
        out1 = res1.json()["choices"][0]["message"]["content"]

        res2 = client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Writer step"}]},
        )
        out2 = res2.json()["choices"][0]["message"]["content"]

    assert cassette_file.exists()
    assert out1 == "Agent step 1 complete."
    assert out2 == "Agent step 2 complete."

    # 2. Replay Mode (Strictly offline, air-gapped)
    with Session(cassette_path=cassette_file, mode="replay") as replay_session:
        replayer_client = replay_session.get_client()

        replay1 = replayer_client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Researcher step"}]},
        )
        replay2 = replayer_client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Writer step"}]},
        )

        assert replay1.json()["choices"][0]["message"]["content"] == out1
        assert replay2.json()["choices"][0]["message"]["content"] == out2
