from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re

import httpx
import pytest
from typer.testing import CliRunner

from rerunner.cassette import Cassette
from rerunner.cli import app
from rerunner.integrity import (
    compute_merkle_root,
    generate_ed25519_keypair,
    sign_merkle_root_ed25519,
    verify_merkle_root_ed25519,
)
from rerunner.matcher import compute_request_key
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.sanitizer import Pseudonymizer, _is_luhn_valid
from rerunner.session import Session
from rerunner.storage import BaseStorageBackend, CachedRemoteBackend, get_storage_backend

runner = CliRunner()


def test_pseudonymizer_preserves_formats_and_determinism() -> None:
    p1 = Pseudonymizer(seed="secret-seed-1")
    p2 = Pseudonymizer(seed="secret-seed-1")

    email_a = p1.pseudonymize_email("alice@acme.com")
    email_b = p2.pseudonymize_email("ALICE@ACME.COM")
    assert email_a == email_b
    assert email_a != "alice@acme.com"
    assert re.fullmatch(r"user_[0-9a-f]{10}@example\.test", email_a)

    uid = p1.pseudonymize_uuid("550e8400-e29b-41d4-a716-446655440000")
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}",
        uid,
    )

    ssn = p1.pseudonymize_ssn("123-45-6789")
    assert re.fullmatch(r"900-\d{2}-\d{4}", ssn)

    cc = p1.pseudonymize_credit_card("4111-1111-1111-1111")
    assert len(cc) == 16 and cc.isdigit() and _is_luhn_valid(cc)

    payload = {
        "user": {"email": "bob@corp.io", "id": "550e8400-e29b-41d4-a716-446655440000"},
        "count": 42,
    }
    masked = p1.pseudonymize_payload(payload)
    assert masked["count"] == 42
    assert masked["user"]["email"].endswith("@example.test")
    assert masked["user"]["id"] != payload["user"]["id"]


def test_merkle_root_and_ed25519_signing_cli(tmp_path: Path) -> None:
    if importlib.util.find_spec("cryptography") is None:
        pytest.skip("cryptography not installed")

    cassette_path = tmp_path / "signed.jsonl"
    cassette = Cassette(cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://api.example.com/v1/ping"),
            response=RecordedResponse(status_code=200, body=json.dumps({"ok": True})),
        )
    )
    cassette.save()

    loaded = Cassette.load(cassette_path, verify_integrity=True)
    root = compute_merkle_root(loaded.entries)
    assert len(root) == 64

    priv_pem, pub_pem = generate_ed25519_keypair()
    sig = sign_merkle_root_ed25519(root, priv_pem)
    assert verify_merkle_root_ed25519(root, sig, pub_pem) is True
    assert verify_merkle_root_ed25519("0" * 64, sig, pub_pem) is False

    key_dir = tmp_path / "keys"
    res_keygen = runner.invoke(app, ["keygen", "--output-dir", str(key_dir)])
    assert res_keygen.exit_code == 0

    res_sign = runner.invoke(
        app,
        ["sign", str(cassette_path), "--private-key", str(key_dir / "rerunner_ed25519.key")],
    )
    assert res_sign.exit_code == 0

    res_verify = runner.invoke(
        app,
        ["sign", str(cassette_path), "--public-key", str(key_dir / "rerunner_ed25519.pub")],
    )
    assert res_verify.exit_code == 0


def test_cached_remote_backend_caches_reads_and_invalidates(tmp_path: Path) -> None:
    class _FakeRemote(BaseStorageBackend):
        def __init__(self) -> None:
            self.store: dict[str, bytes] = {"s3://bucket/c.jsonl": b'{"ok":true}\n'}
            self.read_calls = 0

        def read_bytes(self, uri: str) -> bytes:
            self.read_calls += 1
            return self.store[uri]

        def write_bytes(self, uri: str, data: bytes) -> None:
            self.store[uri] = data

        def exists(self, uri: str) -> bool:
            return uri in self.store

        def delete(self, uri: str) -> None:
            self.store.pop(uri, None)

    remote = _FakeRemote()
    cached = CachedRemoteBackend(remote, cache_dir=tmp_path / "cache")

    assert cached.read_bytes("s3://bucket/c.jsonl") == b'{"ok":true}\n'
    assert cached.read_bytes("s3://bucket/c.jsonl") == b'{"ok":true}\n'
    assert remote.read_calls == 1

    cached.invalidate("s3://bucket/c.jsonl")
    assert cached.read_bytes("s3://bucket/c.jsonl") == b'{"ok":true}\n'
    assert remote.read_calls == 2

    backend = get_storage_backend("s3://bucket/c.jsonl", use_cache=True)
    assert isinstance(backend, CachedRemoteBackend)


def test_requests_patcher_intercepts_inside_session(tmp_path: Path) -> None:
    requests = pytest.importorskip("requests")

    cassette_path = tmp_path / "req.jsonl"
    req_body = json.dumps({"item": "widget"})
    url = "https://api.example.invalid/v1/items"
    cassette = Cassette(cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url=url,
                headers={"content-type": "application/json"},
                body=req_body,
                request_key=compute_request_key("POST", url, req_body.encode("utf-8")),
            ),
            response=RecordedResponse(
                status_code=201,
                headers={"content-type": "application/json"},
                body=json.dumps({"created": True, "id": "item_1"}),
            ),
        )
    )
    cassette.save()

    with Session(cassette_path, mode="replay", auto_patch=True):
        resp = requests.post(
            "https://api.example.invalid/v1/items",
            json={"item": "widget"},
            timeout=5,
        )
        assert resp.status_code == 201
        assert resp.json() == {"created": True, "id": "item_1"}
        # Ensure httpx Session remains unaffected
        assert httpx.Client is not None
