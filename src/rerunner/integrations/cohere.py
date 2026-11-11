"""Zero-friction wrapper for the official Cohere SDK (sync and async)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def _cohere_httpx_client(client: Any) -> httpx.Client | httpx.AsyncClient:
    """Return the httpx client a Cohere SDK client sends its requests through.

    The Cohere SDK keeps it at ``client._client_wrapper.httpx_client.httpx_client``
    (``cohere.Client``, ``cohere.ClientV2`` and their async variants). Every
    sub-client (``client.v2``, ``client.datasets``, ...) shares that wrapper, so
    swapping this one transport covers all of them.
    """
    wrapper = getattr(client, "_client_wrapper", None)
    http_client = getattr(getattr(wrapper, "httpx_client", None), "httpx_client", None)
    if not isinstance(http_client, (httpx.Client, httpx.AsyncClient)):
        raise TypeError(
            "wrap_cohere expects a cohere.Client, cohere.ClientV2, cohere.AsyncClient "
            f"or cohere.AsyncClientV2 instance, got {type(client).__name__}"
        )
    return http_client


def wrap_cohere(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach a Rerunner CassetteTransport to an existing Cohere client instance (sync or async).

    Supports ``cohere.Client``, ``cohere.ClientV2``, ``cohere.AsyncClient`` and
    ``cohere.AsyncClientV2`` (chat, chat_stream, embed, rerank, ...). Clears proxy
    mounts so cassettes always intercept traffic regardless of HTTPS_PROXY env vars.

    Example:
        import cohere
        from rerunner.integrations import wrap_cohere

        client = wrap_cohere(cohere.ClientV2(), "my_run.jsonl", mode="replay")
    """
    http_client = _cohere_httpx_client(client)

    if isinstance(http_client, httpx.AsyncClient):
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport = AsyncCassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )
    else:
        transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)

    http_client._transport = transport  # type: ignore[assignment]
    if hasattr(http_client, "_mounts"):
        http_client._mounts.clear()

    return client


# Name used in the integration request (#59).
wrap_cohere_client = wrap_cohere
