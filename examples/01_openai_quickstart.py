"""01_openai_quickstart.py - OpenAI SDK Recording and Replay with Rerunner.

Demonstrates how to record and deterministically replay OpenAI API calls
using Rerunner's 1-line SDK wrapper (`wrap_openai`) or custom HTTPX transport.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import httpx
from openai import OpenAI
from rich.console import Console

from rerunner.integrations.openai import wrap_openai

console = Console(highlight=False)


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "openai_demo.zst"

        # Mock transport simulating upstream OpenAI backend for self-contained execution
        class MockOpenAIServer(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                return httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={
                        "id": "chatcmpl-demo-123",
                        "model": "gpt-4o",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "Rerunner records and replays agent interactions deterministically.",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 42, "completion_tokens": 15, "total_tokens": 57},
                    },
                )

        console.print("[bold cyan]=== Step 1: Recording Session ===[/bold cyan]")
        console.print(
            "[dim]Wrapping OpenAI client with wrap_openai(client, cassette, mode='record')[/dim]"
        )

        # 1. RECORD MODE:
        raw_client = OpenAI(api_key="sk-test-demo-key")
        recorded_client = wrap_openai(raw_client, cassette_path=cassette_path, mode="record")
        # Route outbound live calls to our simulated upstream server
        recorded_client._client._transport.real_transport = MockOpenAIServer()

        response = recorded_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Explain deterministic replay."}],
        )
        console.print(f"[green][+] Live Output:[/green] {response.choices[0].message.content}")

        assert cassette_path.exists(), "Cassette file was not saved!"
        console.print(f"[cyan][*] Cassette successfully written to {cassette_path.name}[/cyan]\n")

        console.print(
            "[bold cyan]=== Step 2: Deterministic Replay (Zero Network Calls) ===[/bold cyan]"
        )
        console.print("[dim]Replaying with mode='replay' with air-gapped zero network access[/dim]")

        # 2. REPLAY MODE:
        replay_raw = OpenAI(api_key="sk-test-demo-key")
        replay_client = wrap_openai(replay_raw, cassette_path=cassette_path, mode="replay")

        replayed_response = replay_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Explain deterministic replay."}],
        )
        console.print(
            f"[green][+] Replayed Output:[/green] {replayed_response.choices[0].message.content}"
        )
        console.print(f"[yellow][*] Replayed ID:[/yellow] {replayed_response.id}")
        console.print("[bold green][OK] 0ms external latency, $0 token spend.[/bold green]\n")


if __name__ == "__main__":
    run_demo()
