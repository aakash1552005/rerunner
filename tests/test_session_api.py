"""Tests for rerunner.Session API, modes, and environment variable overrides."""

from __future__ import annotations

from pathlib import Path
import pytest
import httpx

from rerunner import CassetteMissingError, Session, SessionContext, fork, record, replay


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/test":
        return httpx.Response(200, json={"message": "hello", "path": request.url.path})
    return httpx.Response(404, json={"error": "not found"})


def test_session_auto_mode_new_and_existing(tmp_path: Path) -> None:
    cassette_file = tmp_path / "test_auto.zst"
    mock_transport = httpx.MockTransport(_mock_handler)

    # 1. Non-existent file -> 'record' mode
    with Session(cassette_file, mode="auto") as session:
        assert session.mode == "record"
        session.transport.real_transport = mock_transport
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200
        assert resp.json()["message"] == "hello"

    assert cassette_file.exists()
    assert cassette_file.stat().st_size > 0

    # 2. Existing file -> 'replay' mode
    with Session(cassette_file, mode="auto") as session:
        assert session.mode == "replay"
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200
        assert resp.json()["message"] == "hello"


def test_session_replay_mode_missing_raises_error(tmp_path: Path) -> None:
    missing_file = tmp_path / "missing.jsonl"
    with (
        pytest.raises(CassetteMissingError, match="does not exist or is empty"),
        Session(missing_file, mode="replay"),
    ):
        pass


def test_session_env_mode_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    missing_file = tmp_path / "env_override.jsonl"

    # Set RERUNNER_MODE=replay
    monkeypatch.setenv("RERUNNER_MODE", "replay")
    with pytest.raises(CassetteMissingError), Session(missing_file, mode="auto"):
        pass

    # Record first with RERUNNER_MODE=record
    monkeypatch.setenv("RERUNNER_MODE", "record")
    mock_transport = httpx.MockTransport(_mock_handler)
    with Session(missing_file, mode="auto") as session:
        assert session.mode == "record"
        session.transport.real_transport = mock_transport
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200

    # Now verify with RERUNNER_MODE=replay
    monkeypatch.setenv("RERUNNER_MODE", "replay")
    with Session(missing_file, mode="auto") as session:
        assert session.mode == "replay"
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200


def test_convenience_functions(tmp_path: Path) -> None:
    cassette_file = tmp_path / "convenience.cassette.zst"
    mock_transport = httpx.MockTransport(_mock_handler)

    with record(cassette_file) as session:
        assert session.mode == "record"
        session.transport.real_transport = mock_transport
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200

    with replay(cassette_file) as session:
        assert session.mode == "replay"
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200

    with fork(cassette_file, step=1) as session:
        assert session.mode == "fork"
        client = session.get_client()
        resp = client.get("https://api.example.com/test")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_async_session_context_manager(tmp_path: Path) -> None:
    cassette_file = tmp_path / "async_session.jsonl"

    async def async_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"async": True})

    async_mock = httpx.MockTransport(async_handler)

    async with Session(cassette_file, mode="record") as session:
        session.async_transport.real_transport = async_mock
        client = session.get_async_client()
        resp = await client.get("https://api.example.com/async")
        assert resp.status_code == 200
        assert resp.json()["async"] is True

    assert cassette_file.exists()

    async with Session(cassette_file, mode="replay") as session:
        client = session.get_async_client()
        resp = await client.get("https://api.example.com/async")
        assert resp.status_code == 200
        assert resp.json()["async"] is True


def test_session_forwards_pii_redactor_to_transports(tmp_path: Path) -> None:
    class _MarkerRedactor:
        def redact(self, text: str) -> str:
            return text.replace("ticket-7781", "[REDACTED_TICKET]")

    cassette_file = tmp_path / "redacted.jsonl"
    redactor = _MarkerRedactor()

    with record(cassette_file, pii_redactor=redactor) as session:
        assert session.transport.pii_redactor is redactor
        assert session.async_transport.pii_redactor is redactor
        assert SessionContext(session.transport).async_transport.pii_redactor is redactor
        session.transport.real_transport = httpx.MockTransport(_mock_handler)
        client = session.get_client()
        resp = client.post("https://api.example.com/test", json={"ref": "ticket-7781"})
        assert resp.status_code == 200

    raw = cassette_file.read_bytes()
    assert b"ticket-7781" not in raw
    assert b"[REDACTED_TICKET]" in raw

    with fork(cassette_file, step=1, pii_redactor=redactor) as session:
        assert session.transport.pii_redactor is redactor
