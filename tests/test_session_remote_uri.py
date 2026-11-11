"""Session keeps remote cassette URIs intact (#74)."""

from __future__ import annotations

import httpx
import pytest

from rerunner import Session
from rerunner.storage import BaseStorageBackend


class _MemoryBackend(BaseStorageBackend):
    """In-memory stand-in for the S3/GCS/Azure backends, keyed by the exact URI."""

    def __init__(self) -> None:
        self.blobs: dict[str, bytes] = {}

    def read_bytes(self, uri: str) -> bytes:
        return self.blobs[uri]

    def write_bytes(self, uri: str, data: bytes) -> None:
        self.blobs[uri] = data

    def exists(self, uri: str) -> bool:
        return uri in self.blobs

    def delete(self, uri: str) -> None:
        self.blobs.pop(uri, None)


@pytest.mark.parametrize(
    "uri",
    ["s3://my-bucket/test.jsonl", "gs://my-bucket/test.jsonl", "az://container/test.jsonl"],
)
def test_session_records_and_replays_remote_uri(
    uri: str, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    backend = _MemoryBackend()
    seen: list[str] = []

    def fake_get_storage_backend(requested: str) -> BaseStorageBackend:
        seen.append(requested)
        return backend

    monkeypatch.setattr("rerunner.session.get_storage_backend", fake_get_storage_backend)
    monkeypatch.setattr("rerunner.cassette.get_storage_backend", fake_get_storage_backend)
    # Nothing may be read from or written to the local disk.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))

    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"n": calls})

    with Session(uri, mode="auto") as session:
        assert session.mode == "record"
        session.transport.real_transport = httpx.MockTransport(handler)
        assert session.get_client().get("https://api.example.com/x").json() == {"n": 1}

    assert list(backend.blobs) == [uri]
    assert set(seen) == {uri}

    with Session(uri, mode="auto") as session:
        assert session.mode == "replay"
        assert session.get_client().get("https://api.example.com/x").json() == {"n": 1}

    assert calls == 1
    assert set(seen) == {uri}
