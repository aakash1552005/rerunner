"""Zero-friction wrapper for Google GenAI / Vertex AI SDKs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
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

    Example:
        from google import genai
        from rerunner.integrations import wrap_google_genai

        client = wrap_google_genai(genai.Client(), "gemini_session.jsonl", mode="replay")
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Summarize this telemetry."
        )
    """
    transport = CassetteTransport(cassette_path=cassette_path, mode=mode, fork_step=fork_step)

    # If the client has an inner httpx client (_client or http_client or _http_client)
    if hasattr(client, "_client") and hasattr(client._client, "_transport"):
        client._client._transport = transport
    elif hasattr(client, "http_client") and hasattr(client.http_client, "_transport"):
        client.http_client._transport = transport
    elif hasattr(client, "_http_client") and hasattr(client._http_client, "_transport"):
        client._http_client._transport = transport
    elif hasattr(client, "_api_client") and hasattr(client._api_client, "_transport"):
        client._api_client._transport = transport
    else:
        # Generic fallback: set httpx client with Rerunner transport
        client._client = httpx.Client(transport=transport)

    return client


# Convenient alias for Vertex AI users
wrap_vertexai = wrap_google_genai
wrap_gemini = wrap_google_genai
