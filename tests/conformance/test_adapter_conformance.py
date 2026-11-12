"""Automated Integration Conformance Matrix across Rerunner provider adapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import rerunner.integrations as integrations
from rerunner.cassette import Cassette
from rerunner.integrations.base import get_registered_adapters, wrap


class _FakeHttpxClient:
    """Minimal duck-typed client matching httpx.Client-wrapped SDKs."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._client = httpx.Client(transport=transport)


def test_integrations_public_exports_and_registry_populated() -> None:
    adapters = get_registered_adapters()
    assert len(adapters) >= 6
    expected_exports = {
        "wrap",
        "wrap_openai",
        "wrap_anthropic",
        "wrap_google_genai",
        "wrap_gemini",
        "wrap_cohere",
        "wrap_together_client",
        "wrap_bedrock_client",
        "wrap_langchain_model",
        "wrap_langgraph_graph",
        "wrap_autogen_client",
        "wrap_semantic_kernel",
        "LlamaIndexRerunnerHandler",
        "RerunnerCallbackHandler",
        "RerunnerCheckpointer",
        "RerunnerMCPClient",
    }
    assert expected_exports.issubset(set(integrations.__all__))


@pytest.mark.parametrize(
    ("provider_url", "payload", "secret_header"),
    [
        (
            "https://api.openai.com/v1/chat/completions",
            {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            ("authorization", "Bearer sk-proj-conformancetest1234567890"),
        ),
        (
            "https://api.anthropic.com/v1/messages",
            {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "hi"}],
            },
            ("x-api-key", "sk-ant-api03-conformancetest1234567890"),
        ),
        (
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
            {"contents": [{"parts": [{"text": "hi"}]}]},
            ("x-goog-api-key", "AIzaSyConformanceTestKey1234567890123"),
        ),
        (
            "https://api.cohere.com/v2/chat",
            {"model": "command-a-03-2025", "messages": [{"role": "user", "content": "hi"}]},
            ("authorization", "Bearer cohere-secret-key-1234567890"),
        ),
        (
            "https://api.together.xyz/v1/chat/completions",
            {
                "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
                "messages": [{"role": "user", "content": "hi"}],
            },
            ("authorization", "Bearer together-secret-key-1234567890"),
        ),
    ],
)
def test_provider_http_conformance_record_replay_and_redaction(
    tmp_path: Path,
    provider_url: str,
    payload: dict[str, Any],
    secret_header: tuple[str, str],
) -> None:
    call_count = 0

    def _mock_live(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"provider_echo": str(request.url), "usage": {"total_tokens": 25}},
        )

    cassette_path = tmp_path / "conformance.jsonl"
    live_transport = httpx.MockTransport(_mock_live)

    # Record phase via wrap() auto-dispatch on generic httpx-backed client
    rec_client = _FakeHttpxClient(live_transport)
    wrap(rec_client, cassette_path, mode="record")
    r1 = rec_client._client.post(
        provider_url,
        headers={secret_header[0]: secret_header[1]},
        json=payload,
    )
    assert r1.status_code == 200
    assert call_count == 1
    rec_client._client.close()

    # Verify secret never lands on disk (either stripped or [REDACTED]) + SHA-256 chain
    raw_disk = cassette_path.read_text(encoding="utf-8")
    assert secret_header[1] not in raw_disk
    loaded = Cassette.load(cassette_path, verify_integrity=True)
    assert len(loaded.entries) == 1
    recorded_req = loaded.entries[0].request
    assert recorded_req is not None
    assert recorded_req.headers.get(secret_header[0]) in (None, "[REDACTED]")

    # Replay phase: zero live network calls
    replay_client = _FakeHttpxClient(httpx.MockTransport(_mock_live))
    wrap(replay_client, cassette_path, mode="replay")
    r2 = replay_client._client.post(
        provider_url,
        headers={secret_header[0]: "Bearer different-runtime-token"},
        json=payload,
    )
    assert r2.status_code == 200
    assert call_count == 1
    assert json.loads(r2.text)["usage"]["total_tokens"] == 25
