"""Unit tests for synchronous and asynchronous CassetteTransport."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import httpx
import pytest
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def test_sync_record_and_replay(temp_cassette_path: Path, mock_transport: Any) -> None:
    # 1. Record Mode
    record_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=mock_transport,
    )
    with httpx.Client(transport=record_transport) as client:
        resp = client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "test"})
        assert resp.status_code == 200
        assert "Hello AI World" in resp.text
        assert mock_transport.call_count == 1

    assert temp_cassette_path.exists()

    # 2. Replay Mode (Zero network calls, mock_transport is NOT called again)
    replay_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="replay",
        real_transport=mock_transport,
    )
    with httpx.Client(transport=replay_transport) as client:
        replayed_resp = client.post(
            "https://api.openai.com/v1/chat/completions", json={"prompt": "test"}
        )
        assert replayed_resp.status_code == 200
        assert "Hello AI World" in replayed_resp.text
        # Call count remains 1, proving network was NOT hit
        assert mock_transport.call_count == 1


@pytest.mark.asyncio
async def test_async_record_and_replay(temp_cassette_path: Path, mock_async_transport: Any) -> None:
    # 1. Async Record Mode
    async_record_transport = AsyncCassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=mock_async_transport,
    )
    async with httpx.AsyncClient(transport=async_record_transport) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", json={"prompt": "async test"}
        )
        assert resp.status_code == 200
        assert "Async Hello" in resp.text
        assert mock_async_transport.call_count == 1

    # 2. Async Replay Mode
    async_replay_transport = AsyncCassetteTransport(
        cassette_path=temp_cassette_path,
        mode="replay",
        real_transport=mock_async_transport,
    )
    async with httpx.AsyncClient(transport=async_replay_transport) as client:
        replayed_resp = await client.post(
            "https://api.anthropic.com/v1/messages", json={"prompt": "async test"}
        )
        assert replayed_resp.status_code == 200
        assert "Async Hello" in replayed_resp.text
        assert mock_async_transport.call_count == 1


class _MarkerRedactor:
    """Minimal pii_redactor stub so transport wiring is testable without optional packages."""

    def redact(self, text: str) -> str:
        return text.replace("ticket-7781", "[REDACTED_TICKET]")


def test_sync_pii_redactor_applies_before_persisting(
    temp_cassette_path: Path, mock_transport: Any
) -> None:
    record_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=mock_transport,
        pii_redactor=_MarkerRedactor(),
    )
    with httpx.Client(transport=record_transport) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions", json={"prompt": "ticket-7781"}
        )
        assert resp.status_code == 200

    raw = temp_cassette_path.read_bytes()
    assert b"ticket-7781" not in raw
    assert b"[REDACTED_TICKET]" in raw

    # Replay matches on the raw request, so redaction never affects cassette lookup
    replay_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="replay",
        real_transport=mock_transport,
    )
    with httpx.Client(transport=replay_transport) as client:
        replayed_resp = client.post(
            "https://api.openai.com/v1/chat/completions", json={"prompt": "ticket-7781"}
        )
        assert replayed_resp.status_code == 200
        assert mock_transport.call_count == 1


def test_sync_recording_is_unchanged_without_pii_redactor(
    temp_cassette_path: Path, mock_transport: Any
) -> None:
    record_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=mock_transport,
    )
    with httpx.Client(transport=record_transport) as client:
        client.post("https://api.openai.com/v1/chat/completions", json={"prompt": "ticket-7781"})

    assert b"ticket-7781" in temp_cassette_path.read_bytes()


@pytest.mark.asyncio
async def test_async_pii_redactor_applies_before_persisting(
    temp_cassette_path: Path, mock_async_transport: Any
) -> None:
    record_transport = AsyncCassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=mock_async_transport,
        pii_redactor=_MarkerRedactor(),
    )
    async with httpx.AsyncClient(transport=record_transport) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages", json={"prompt": "ticket-7781"}
        )
        assert resp.status_code == 200

    raw = temp_cassette_path.read_bytes()
    assert b"ticket-7781" not in raw
    assert b"[REDACTED_TICKET]" in raw


def test_sync_record_keeps_records_whose_keys_sanitize_alike(temp_cassette_path: Path) -> None:
    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"users": {"ops@acme.org": {"id": 1}, "sales@acme.org": {"id": 2}}}
        )

    record_transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="record",
        real_transport=httpx.MockTransport(handle_request),
    )
    with httpx.Client(transport=record_transport) as client:
        resp = client.get("https://api.example.test/users")
        assert len(resp.json()["users"]) == 2

    raw = temp_cassette_path.read_bytes()
    assert b"acme.org" not in raw
    assert b"[REDACTED_EMAIL]#2" in raw

    replay_transport = CassetteTransport(cassette_path=temp_cassette_path, mode="replay")
    with httpx.Client(transport=replay_transport) as client:
        users = client.get("https://api.example.test/users").json()["users"]
    assert users == {"[REDACTED_EMAIL]": {"id": 1}, "[REDACTED_EMAIL]#2": {"id": 2}}
