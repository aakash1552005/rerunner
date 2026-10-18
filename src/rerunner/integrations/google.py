"""Zero-friction wrapper for Google GenAI / Vertex AI SDKs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_google_genai(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach a Rerunner CassetteTransport to an existing Google GenAI or Vertex AI client instance.

    Works with both the modern `google-genai` SDK and custom HTTP-based Gemini clients.
    Supports both synchronous and asynchronous client interfaces (e.g. client.aio).
    """
    sync_transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)
    async_transport = AsyncCassetteTransport(
        cassette_path=cassette_path, mode=mode, fork_step=fork_step
    )

    # 1. Direct AsyncClient instance
    if isinstance(client, httpx.AsyncClient):
        client._transport = async_transport
        return client

    # 2. Sync client wrapping
    if hasattr(client, "_client") and hasattr(client._client, "_transport"):
        if isinstance(client._client, httpx.AsyncClient):
            client._client._transport = async_transport
        else:
            client._client._transport = sync_transport
    elif hasattr(client, "http_client") and hasattr(client.http_client, "_transport"):
        if isinstance(client.http_client, httpx.AsyncClient):
            client.http_client._transport = async_transport
        else:
            client.http_client._transport = sync_transport
    elif hasattr(client, "_http_client") and hasattr(client._http_client, "_transport"):
        if isinstance(client._http_client, httpx.AsyncClient):
            client._http_client._transport = async_transport
        else:
            client._http_client._transport = sync_transport
    elif hasattr(client, "_api_client") and hasattr(client._api_client, "_transport"):
        client._api_client._transport = sync_transport
    else:
        # Generic fallback
        client._client = httpx.Client(transport=sync_transport)

    # 3. Asynchronous client wrapping (client.aio, _async_httpx_client, _async_client, async_client)
    for async_attr in ("aio", "_async_httpx_client", "_async_client", "async_client"):
        if hasattr(client, async_attr):
            async_obj = getattr(client, async_attr)
            if async_obj is not None:
                if isinstance(async_obj, httpx.AsyncClient):
                    async_obj._transport = async_transport
                elif hasattr(async_obj, "_client") and hasattr(async_obj._client, "_transport"):
                    async_obj._client._transport = async_transport
                elif hasattr(async_obj, "http_client") and hasattr(
                    async_obj.http_client, "_transport"
                ):
                    async_obj.http_client._transport = async_transport
                elif hasattr(async_obj, "_http_client") and hasattr(
                    async_obj._http_client, "_transport"
                ):
                    async_obj._http_client._transport = async_transport
                elif hasattr(async_obj, "_api_client") and hasattr(
                    async_obj._api_client, "_transport"
                ):
                    async_obj._api_client._transport = async_transport

    return client


# Convenient alias for Vertex AI users
wrap_vertexai = wrap_google_genai
wrap_gemini = wrap_google_genai
