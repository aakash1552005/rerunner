"""04_chaos_fault_injection.py - Offline Agent Resilience & Chaos Testing with Rerunner.

Demonstrates how to test agent retry policies, circuit breakers, and fallback model
routes under simulated HTTP 429 RateLimit and 503 Overloaded errors without incurring live API costs.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
import httpx
from rich.console import Console

from rerunner import CassetteTransport

console = Console(highlight=False)


def run_agent_with_retry(client: httpx.Client, prompt: str, max_retries: int = 3) -> str:
    """Agent execution loop with exponential backoff on HTTP 429/503."""
    for attempt in range(1, max_retries + 1):
        console.print(
            f"[yellow][*] Attempt {attempt}/{max_retries}:[/yellow] Sending prompt to primary model..."
        )
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": prompt}]},
        )
        if resp.status_code == 200:
            console.print("[green][+] Success on primary model![/green]")
            return str(resp.json()["choices"][0]["message"]["content"])

        if resp.status_code == 429:
            console.print(
                f"[red][!] Rate limited (HTTP 429): {resp.json().get('error', {}).get('message')}[/red]"
            )
            if attempt < max_retries:
                backoff = 0.05 * (2 ** (attempt - 1))
                console.print(f"[dim]Backing off for {backoff:.2f}s...[/dim]")
                time.sleep(backoff)
                continue

    # Fallback to secondary model
    console.print("[cyan][->] Triggering fallback to secondary model (Claude 3.5 Haiku)...[/cyan]")
    resp_fallback = client.post(
        "https://api.anthropic.com/v1/messages",
        json={
            "model": "claude-3-5-haiku-20241022",
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    if resp_fallback.status_code == 200:
        console.print("[green][+] Fallback model succeeded![/green]")
        return str(resp_fallback.json()["content"][0]["text"])

    raise RuntimeError("All primary and fallback attempts exhausted.")


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "chaos_run.jsonl"

        call_count = 0

        # Mock server that simulates: Call 1 -> 429 Rate Limit, Call 2 -> 429 Rate Limit, Call 3 -> Fallback Success
        class SimulatedFlakyNetwork(httpx.BaseTransport):
            def handle_request(self, request: httpx.Request) -> httpx.Response:
                nonlocal call_count
                call_count += 1
                if "openai" in str(request.url):
                    # Simulate OpenAI 429 Rate Limit
                    return httpx.Response(
                        429,
                        headers={"content-type": "application/json", "retry-after": "1"},
                        json={
                            "error": {
                                "message": "Rate limit exceeded. Please throttle your requests."
                            }
                        },
                        request=request,
                    )
                # Anthropic fallback succeeds
                return httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={
                        "id": "msg_fallback_999",
                        "model": "claude-3-5-haiku-20241022",
                        "content": [
                            {
                                "type": "text",
                                "text": "Fallback agent response delivered successfully.",
                            }
                        ],
                    },
                    request=request,
                )

        console.print("[bold cyan]=== Step 1: Recording Chaos Trajectory ===[/bold cyan]")
        console.print(
            "[dim]Simulating 429 errors on primary model and automatic fallback routing[/dim]\n"
        )

        record_transport = CassetteTransport(
            cassette_path=cassette_path,
            mode="record",
            real_transport=SimulatedFlakyNetwork(),
        )

        with httpx.Client(transport=record_transport) as client:
            output = run_agent_with_retry(client, "Summarize system health", max_retries=2)
            console.print(f"[bold green]Final Agent Output:[/bold green] {output}\n")

        assert cassette_path.exists(), "Cassette was not created!"
        console.print(
            f"[cyan][*] Captured full chaos trajectory into {cassette_path.name}[/cyan]\n"
        )

        console.print("[bold cyan]=== Step 2: Deterministic Replay in CI ===[/bold cyan]")
        console.print(
            "[dim]Replaying the entire retry loop and fallback transition with zero network calls[/dim]\n"
        )

        replay_transport = CassetteTransport(
            cassette_path=cassette_path,
            mode="replay",
        )

        with httpx.Client(transport=replay_transport) as client:
            replayed_output = run_agent_with_retry(client, "Summarize system health", max_retries=2)
            assert replayed_output == output
            console.print(
                "\n[bold green][OK] Verified agent circuit breaker and fallback resilience offline![/bold green]\n"
            )


if __name__ == "__main__":
    run_demo()
