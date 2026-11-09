"""05_crewai_multi_agent.py - Deterministic Multi-Agent CrewAI replay with Rerunner.

Demonstrates how to record and replay multi-agent workflows (e.g. Researcher + Writer)
with zero code modification to CrewAI agents, achieving 100% offline, $0 deterministic replay.
"""

from __future__ import annotations

import os
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()

import tempfile
from pathlib import Path
import httpx
from rich.console import Console

from rerunner import Session

console = Console(highlight=False)


def run_crewai_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "crewai_research_crew.zst"

        # Simulated OpenAI/LiteLLM endpoint response for self-contained execution
        class MockCrewAIUpstream(httpx.BaseTransport):
            def __init__(self) -> None:
                self.call_count = 0

            def handle_request(self, request: httpx.Request) -> httpx.Response:
                self.call_count += 1
                if self.call_count == 1:
                    content = (
                        "Research Findings:\n"
                        "- Deterministic execution eliminates flaky integration tests.\n"
                        "- Cassette caching reduces agent development costs to $0."
                    )
                else:
                    content = (
                        "Executive Summary:\n"
                        "Multi-agent frameworks like CrewAI benefit significantly from record/replay "
                        "engines. Rerunner captures multi-turn LLM calls across agents seamlessly."
                    )

                return httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={
                        "id": f"chatcmpl-crewai-{self.call_count}",
                        "model": "gpt-4o",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": content,
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 60, "total_tokens": 180},
                    },
                )

        console.print("[bold cyan]=== Step 1: Record Mode (Crew Execution) ===[/bold cyan]")
        console.print("[dim]Running multi-agent research workflow inside Rerunner Session...[/dim]")

        # 1. RECORD MODE
        with Session(cassette_path=cassette_path, mode="record") as session:
            # Wire our simulated upstream
            session.transport.real_transport = MockCrewAIUpstream()

            # Execute Agent 1: Senior Research Analyst
            client = session.get_client()
            researcher_res = client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a Senior Research Analyst. Gather key facts.",
                        },
                        {"role": "user", "content": "Analyze deterministic testing for AI agents."},
                    ],
                },
            )
            findings = researcher_res.json()["choices"][0]["message"]["content"]
            console.print(f"[green][+] Researcher Output:[/green]\n{findings}\n")

            # Execute Agent 2: Tech Writer
            writer_res = client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an Executive Tech Writer. Summarize the research.",
                        },
                        {"role": "user", "content": f"Summarize these findings:\n{findings}"},
                    ],
                },
            )
            article = writer_res.json()["choices"][0]["message"]["content"]
            console.print(f"[blue][+] Writer Output:[/blue]\n{article}\n")

        assert cassette_path.exists(), "Cassette file was not saved!"
        console.print(
            f"[cyan][*] Cassette successfully recorded with multiple agent turns to {cassette_path.name}[/cyan]\n"
        )

        # 2. REPLAY MODE
        console.print("[bold cyan]=== Step 2: Deterministic Replay (Zero Network Calls) ===[/bold cyan]")
        console.print("[dim]Replaying with air-gapped transport: zero outbound API calls allowed.[/dim]")

        with Session(cassette_path=cassette_path, mode="replay") as replay_session:
            replayer_client = replay_session.get_client()

            replayed_res1 = replayer_client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a Senior Research Analyst. Gather key facts.",
                        },
                        {"role": "user", "content": "Analyze deterministic testing for AI agents."},
                    ],
                },
            )
            replayed_findings = replayed_res1.json()["choices"][0]["message"]["content"]

            replayed_res2 = replayer_client.post(
                "https://api.openai.com/v1/chat/completions",
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an Executive Tech Writer. Summarize the research.",
                        },
                        {"role": "user", "content": f"Summarize these findings:\n{replayed_findings}"},
                    ],
                },
            )
            replayed_article = replayed_res2.json()["choices"][0]["message"]["content"]

        assert replayed_findings == findings
        assert replayed_article == article
        console.print("[bold green][✓] Multi-agent replay matched live outputs bit-for-bit with $0 cost![/bold green]")


if __name__ == "__main__":
    run_crewai_demo()
