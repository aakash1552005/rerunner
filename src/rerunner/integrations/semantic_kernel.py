"""Zero-friction wrapper for Microsoft Semantic Kernel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_semantic_kernel(
    kernel: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach Rerunner cassette transports to all AI services registered with a Semantic Kernel instance.

    Intercepts ChatCompletion, TextCompletion, and Embedding services configured
    on the kernel (both sync and async transports).

    Example:
        import semantic_kernel as sk
        from rerunner.integrations.semantic_kernel import wrap_semantic_kernel

        kernel = sk.Kernel()
        # ... add services ...
        wrap_semantic_kernel(kernel, "cassettes/sk_flight.jsonl", mode="replay")
    """
    async_transport = AsyncCassetteTransport(
        cassette_path=cassette_path, mode=mode, fork_step=fork_step
    )
    sync_transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)

    # Patch services registered in kernel.services (dict or registry)
    services = getattr(kernel, "services", {})
    service_iterable: Any = []
    if isinstance(services, dict):
        service_iterable = list(services.values())
    elif hasattr(services, "__iter__"):
        service_iterable = services

    for service in service_iterable:
        _patch_service_client(service, sync_transport, async_transport)

    # Also check if kernel has direct client or http_client
    if hasattr(kernel, "http_client"):
        _patch_http_client(kernel.http_client, sync_transport, async_transport)

    return kernel


def _patch_service_client(
    service: Any,
    sync_transport: CassetteTransport,
    async_transport: AsyncCassetteTransport,
) -> None:
    """Patch client attributes on a Semantic Kernel AI service."""
    # OpenAI/AzureOpenAI client attribute inside service
    for attr in ("client", "_client", "async_client", "_async_client", "http_client"):
        target = getattr(service, attr, None)
        if target is not None:
            _patch_http_client(target, sync_transport, async_transport)


def _patch_http_client(
    client: Any,
    sync_transport: CassetteTransport,
    async_transport: AsyncCassetteTransport,
) -> None:
    """Patch httpx transport on a client object."""
    if isinstance(client, httpx.AsyncClient):
        client._transport = async_transport
        if hasattr(client, "_mounts"):
            client._mounts.clear()
    elif isinstance(client, httpx.Client):
        client._transport = sync_transport
        if hasattr(client, "_mounts"):
            client._mounts.clear()
    elif hasattr(client, "_client"):
        # Nested client (e.g., openai.OpenAI / openai.AsyncOpenAI)
        _patch_http_client(client._client, sync_transport, async_transport)
