"""Zero-friction wrapper and mock generators for AWS Bedrock agent and model invocations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.transport import CassetteTransport
from rerunner.async_transport import AsyncCassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_bedrock_client(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach a Rerunner CassetteTransport to an HTTP-based AWS Bedrock client or botocore session.

    Example:
        from rerunner.integrations.bedrock import wrap_bedrock_client

        # Direct HTTPX client configured for AWS Bedrock
        client = wrap_bedrock_client(client, "cassettes/bedrock.jsonl", mode="replay")
    """
    is_async = (
        type(client).__name__.startswith("Async")
        or isinstance(getattr(client, "_client", None), httpx.AsyncClient)
        or isinstance(client, httpx.AsyncClient)
    )

    if is_async:
        transport: httpx.BaseTransport | httpx.AsyncBaseTransport = AsyncCassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )
    else:
        transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)

    if isinstance(client, (httpx.Client, httpx.AsyncClient)):
        client._transport = transport
        if hasattr(client, "_mounts"):
            client._mounts.clear()
        return client

    if hasattr(client, "_client"):
        http_client = client._client
        http_client._transport = transport
        if hasattr(http_client, "_mounts"):
            http_client._mounts.clear()
    elif hasattr(client, "http_client"):
        client.http_client._transport = transport
    else:
        if is_async:
            client._client = httpx.AsyncClient(transport=transport)  # type: ignore[arg-type]
        else:
            client._client = httpx.Client(transport=transport)  # type: ignore[arg-type]

    return client


def mock_bedrock_converse_response(
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0",
    text: str = "Deterministic response from AWS Bedrock.",
    input_tokens: int = 15,
    output_tokens: int = 25,
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence"] = "end_turn",
) -> dict[str, Any]:
    """Helper to generate a deterministic AWS Bedrock Converse API dictionary response for testing.

    Enables offline replay of multi-step AWS Bedrock agent workflows in CI without live AWS credentials.
    """
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": stop_reason,
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        },
        "metrics": {"latencyMs": 42},
    }
