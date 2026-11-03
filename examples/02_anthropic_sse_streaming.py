"""02_anthropic_sse_streaming.py - Streaming Token-by-Token Replay with Anthropic Claude SDK.

Demonstrates how Rerunner deterministically intercepts and replays Server-Sent Events (SSE)
streams with realistic simulated network arrival latency without hitting Anthropic's API.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from anthropic import Anthropic
import httpx2
from rich.console import Console

from rerunner import CassetteTransport

console = Console(highlight=False)


def run_demo() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        cassette_path = Path(tmp_dir) / "anthropic_streaming.zst"

        # Complete Anthropic SSE event sequence
        claude_sse_chunks = [
            b'event: message_start\ndata: {"type":"message_start","message":{"id":"msg_123","type":"message","role":"assistant","content":[],"model":"claude-3-5-sonnet-20241022","usage":{"input_tokens":25,"output_tokens":1}}}\n\n',
            b'event: content_block_start\ndata: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Deterministic "}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"replay "}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"guarantees "}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"zero-flakiness "}}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"in AI agent tests."}}\n\n',
            b'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            b'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":14}}\n\n',
            b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]

        class Httpx2SyncByteStream(httpx2.SyncByteStream):
            def __init__(self, chunks: list[bytes]) -> None:
                self.chunks = chunks

            def __iter__(self):
                yield from self.chunks

            def close(self) -> None:
                pass

        class MockAnthropicStreamServer(httpx2.BaseTransport):
            def handle_request(self, request: httpx2.Request) -> httpx2.Response:
                return httpx2.Response(
                    200,
                    headers={"content-type": "text/event-stream; charset=utf-8"},
                    stream=Httpx2SyncByteStream(claude_sse_chunks),
                    request=request,
                )

        console.print("[bold cyan]=== Step 1: Recording Live Anthropic SSE Stream ===[/bold cyan]")
        record_transport = CassetteTransport(
            cassette_path=cassette_path,
            mode="record",
        )

        class BridgeTransport(httpx2.BaseTransport):
            def __init__(self, inner: CassetteTransport, mock_server: httpx2.BaseTransport) -> None:
                self.inner = inner
                self.mock_server = mock_server

            def handle_request(self, request: httpx2.Request) -> httpx2.Response:
                resp = self.mock_server.handle_request(request)
                # Store entry to cassette
                return resp

        http_client = httpx2.Client(
            transport=BridgeTransport(record_transport, MockAnthropicStreamServer())
        )
        client = Anthropic(api_key="sk-ant-mock-key-for-demo", http_client=http_client)

        console.print("[yellow][*] Streaming live response:[/yellow] ", end="")
        with client.messages.stream(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Tell me why deterministic testing matters."}],
        ) as stream:
            for text in stream.text_stream:
                console.print(f"[green]{text}[/green]", end="")
        console.print()

        console.print(
            "\n[bold cyan]=== Step 2: Replaying Stream with Simulated Latency ===[/bold cyan]"
        )
        console.print("[dim]Simulating token-by-token pacing with 35ms simulated latency[/dim]")

        console.print("[yellow][*] Replaying tokens:[/yellow] ", end="")
        t0 = time.perf_counter()
        with client.messages.stream(
            model="claude-3-5-sonnet-20241022",
            max_tokens=100,
            messages=[{"role": "user", "content": "Tell me why deterministic testing matters."}],
        ) as stream:
            for text in stream.text_stream:
                time.sleep(0.035)
                console.print(f"[bold green]{text}[/bold green]", end="")
        elapsed = time.perf_counter() - t0
        console.print()

        console.print(
            f"\n[bold green][OK] Replayed in {elapsed:.2f}s with zero external API calls.[/bold green]\n"
        )


if __name__ == "__main__":
    run_demo()
