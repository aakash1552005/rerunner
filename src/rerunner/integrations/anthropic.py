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
    is_async = (
        type(client).__name__.startswith("Async")
        or isinstance(getattr(client, "_client", None), httpx.AsyncClient)
    )

    if is_async:
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport = AsyncCassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )
    else:
        transport = CassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )

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
