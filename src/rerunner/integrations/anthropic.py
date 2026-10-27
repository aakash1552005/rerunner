"""Zero-friction wrapper for the official Anthropic Claude SDK (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.transport import CassetteTransport
from rerunner.async_transport import AsyncCassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_anthropic(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach a Rerunner CassetteTransport to an existing Anthropic client instance (sync or async).

    Supports both sync `anthropic.Anthropic` and async `anthropic.AsyncAnthropic` clients.
    Clears proxy mounts so cassettes always intercept traffic regardless of HTTPS_PROXY env vars.

    Example:
        import anthropic
        from rerunner.integrations import wrap_anthropic

        client = wrap_anthropic(anthropic.Anthropic(), "my_run.jsonl", mode="replay")
    """
    is_async = type(client).__name__.startswith("Async") or isinstance(
        getattr(client, "_client", None), httpx.AsyncClient
    )

    if is_async:
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport = AsyncCassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )
    else:
        transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)

    if hasattr(client, "_client"):
        http_client = client._client
        http_client._transport = transport
        if hasattr(http_client, "_mounts"):
            http_client._mounts.clear()
    else:
        if is_async:
            client._client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]
        else:
            client._client = httpx.Client(transport=transport)  # type: ignore[arg-type]

    return client


def mock_anthropic_batch_response(
    batch_id: str = "msgbatch_test_123",
    status: Literal["in_progress", "canceling", "ended"] = "ended",
    total_requests: int = 1,
    succeeded_requests: int = 1,
) -> dict[str, Any]:
    """Helper to generate a deterministic Anthropic Message Batch API JSON response for testing.

    Resolves Issue #20: Enables immediate offline replay of Claude 3.5 Sonnet / Haiku
    batch workloads in CI without waiting for background batch queue execution.
    """
    return {
        "id": batch_id,
        "type": "message_batch",
        "processing_status": status,
        "request_counts": {
            "processing": 0 if status == "ended" else total_requests,
            "succeeded": succeeded_requests if status == "ended" else 0,
            "errored": 0,
            "canceled": 0,
            "expired": 0,
        },
        "ended_at": "2026-01-01T00:00:00Z" if status == "ended" else None,
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-02T00:00:00Z",
    }
