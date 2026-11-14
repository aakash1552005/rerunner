"""Zero-friction wrapper for the official Together AI SDK (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.transport import CassetteTransport
from rerunner.async_transport import AsyncCassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_together_client(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach a Rerunner CassetteTransport to an existing Together AI client instance (sync or async).

    Supports both sync `together.Together` and async `together.AsyncTogether` clients.
    Clears proxy mounts so cassettes always intercept traffic regardless of HTTPS_PROXY env vars.

    Example:
        import together
        from rerunner.integrations import wrap_together_client

        client = wrap_together_client(together.Together(), "my_run.jsonl", mode="replay")
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

    # Convert settings to string/standard primitives to guarantee compatibility across httpx versions
    old_client = getattr(client, "_client", None)
    client_kwargs: dict[str, Any] = {"transport": transport}

    if old_client is not None:
        raw_base_url = getattr(old_client, "base_url", None)
        if raw_base_url:
            client_kwargs["base_url"] = str(raw_base_url)

        raw_timeout = getattr(old_client, "timeout", None)
        if raw_timeout is not None:
            client_kwargs["timeout"] = float(getattr(raw_timeout, "read", 60.0))

        raw_headers = getattr(old_client, "headers", None)
        if raw_headers is not None:
            client_kwargs["headers"] = dict(raw_headers)

    if is_async:
        client._client = httpx.AsyncClient(**client_kwargs)
    else:
        client._client = httpx.Client(**client_kwargs)

    return client
