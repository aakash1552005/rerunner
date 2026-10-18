"""Tests verifying zero-touch auto-patching of httpx.Client and httpx.AsyncClient."""

from __future__ import annotations

from pathlib import Path
import pytest
import httpx

import rerunner
from rerunner import Session


def _mock_server(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"intercepted": True, "path": str(request.url.path)})


def test_zero_touch_sync_httpx_interception(tmp_path: Path) -> None:
    cassette_file = tmp_path / "auto_patch_sync.zst"
    mock_real = httpx.MockTransport(_mock_server)

    with Session(cassette_file, mode="record", auto_patch=True) as session:
        # Override the session's real transport with our mock server
        session.transport.real_transport = mock_real

        # Zero-touch client instantiation - NO transport passed!
        client = httpx.Client()
        resp = client.get("https://api.openai.com/v1/chat/completions")

        assert resp.status_code == 200
        assert resp.json()["intercepted"] is True
        assert len(session.cassette.entries) == 1

    assert cassette_file.exists()

    # Replay with zero-touch client
    with Session(cassette_file, mode="replay", auto_patch=True) as session:
        client = httpx.Client()
        resp = client.get("https://api.openai.com/v1/chat/completions")
        assert resp.status_code == 200
        assert resp.json()["intercepted"] is True


@pytest.mark.asyncio
async def test_zero_touch_async_httpx_interception(tmp_path: Path) -> None:
    cassette_file = tmp_path / "auto_patch_async.zst"

    async def async_mock_server(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"async_intercepted": True})

    mock_real = httpx.MockTransport(async_mock_server)

    async with Session(cassette_file, mode="record", auto_patch=True) as session:
        session.async_transport.real_transport = mock_real

        # Zero-touch async client
        client = httpx.AsyncClient()
        resp = await client.get("https://api.anthropic.com/v1/messages")

        assert resp.status_code == 200
        assert resp.json()["async_intercepted"] is True
        assert len(session.cassette.entries) == 1

    async with Session(cassette_file, mode="replay", auto_patch=True) as session:
        client = httpx.AsyncClient()
        resp = await client.get("https://api.anthropic.com/v1/messages")
        assert resp.status_code == 200
        assert resp.json()["async_intercepted"] is True


def test_unpatched_client_preserves_live_outbound(tmp_path: Path) -> None:
    cassette_file = tmp_path / "unpatched.zst"

    with Session(cassette_file, mode="record", auto_patch=True) as session:
        # Client marked unpatched
        unpatched = session.unpatched_client()
        # Verify it has standard unpatched transport, not CassetteTransport
        assert not isinstance(unpatched._transport, rerunner.CassetteTransport)


def test_nested_sessions_auto_patch_restores_outer(tmp_path: Path) -> None:
    cass_a = tmp_path / "outer.zst"
    cass_b = tmp_path / "inner.zst"
    mock_real = httpx.MockTransport(_mock_server)

    with Session(cass_a, mode="record", auto_patch=True) as session_a:
        session_a.transport.real_transport = mock_real
        client_a = httpx.Client()
        assert client_a._transport is session_a.transport

        with Session(cass_b, mode="record", auto_patch=True) as session_b:
            session_b.transport.real_transport = mock_real
            client_b = httpx.Client()
            assert client_b._transport is session_b.transport

        # After inner exits, outer auto_patch remains active!
        client_a_after = httpx.Client()
        assert client_a_after._transport is session_a.transport

    # After outer exits, auto_patch is completely restored
    client_outside = httpx.Client()
    assert not isinstance(client_outside._transport, rerunner.CassetteTransport)
