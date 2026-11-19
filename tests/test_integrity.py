"""Unit tests for cryptographic SHA-256 integrity checks, Merkle trees, and Ed25519 signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import pytest

from rerunner.integrity import (
    _load_ed25519_module,
    canonical_entry_payload,
    compute_entry_hash,
    compute_merkle_root,
    generate_ed25519_keypair,
    sign_merkle_root_ed25519,
    verify_cassette_integrity,
    verify_merkle_root_ed25519,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

HAS_CRYPTOGRAPHY = importlib.util.find_spec("cryptography") is not None


def _make_sample_entry(step: int = 1, prev_hash: str = "GENESIS", body: str = '{"output": "ok"}') -> CassetteEntry:
    req = RecordedRequest(
        method="POST", url="https://api.anthropic.com/v1/messages", request_key=f"key{step}"
    )
    resp = RecordedResponse(status_code=200, body=body)
    return CassetteEntry(
        step=step, entry_type="http", request=req, response=resp, prev_hash=prev_hash
    )


def test_hash_chain_verification_passes() -> None:
    entry1 = _make_sample_entry(step=1, prev_hash="GENESIS")
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    entry2 = _make_sample_entry(step=2, prev_hash=entry1.entry_hash)
    entry2.entry_hash = compute_entry_hash(entry2, entry1.entry_hash)

    is_valid, error = verify_cassette_integrity([entry1, entry2])
    assert is_valid is True
    assert error is None


def test_tamper_detection_flags_modified_body() -> None:
    entry1 = _make_sample_entry(step=1, prev_hash="GENESIS", body='{"content": "Original response"}')
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    # Attacker tampers with the response body
    entry1.response.body = '{"content": "Hacked response"}'  # type: ignore[union-attr]

    is_valid, error = verify_cassette_integrity([entry1])
    assert is_valid is False
    assert error is not None
    assert "Tampered entry detected at step 1" in error
    assert "recorded hash" in error
    assert "does not match recomputed" in error


def test_canonical_entry_payload_formatting() -> None:
    entry = _make_sample_entry(step=1)
    entry.entry_hash = "some_hash"
    payload = canonical_entry_payload(entry)
    data = json.loads(payload)
    assert "entry_hash" not in data
    assert data["step"] == 1
    assert payload == json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def test_compute_entry_hash_plain_sha256() -> None:
    entry = _make_sample_entry(step=1)
    canonical = canonical_entry_payload(entry)
    expected_payload = f"GENESIS:{canonical}"
    expected_hash = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
    assert compute_entry_hash(entry, "GENESIS") == expected_hash


def test_compute_entry_hash_hmac_secret_key() -> None:
    entry = _make_sample_entry(step=1)
    canonical = canonical_entry_payload(entry)
    expected_payload = f"GENESIS:{canonical}"
    key = "super-secret-key"
    expected_hmac = hmac.new(key.encode("utf-8"), expected_payload.encode("utf-8"), hashlib.sha256).hexdigest()

    # Pass as str
    assert compute_entry_hash(entry, "GENESIS", secret_key=key) == expected_hmac
    # Pass as bytes
    assert compute_entry_hash(entry, "GENESIS", secret_key=key.encode("utf-8")) == expected_hmac


def test_compute_entry_hash_env_hmac_key(monkeypatch: pytest.MonkeyPatch) -> None:
    entry = _make_sample_entry(step=1)
    canonical = canonical_entry_payload(entry)
    expected_payload = f"GENESIS:{canonical}"
    monkeypatch.setenv("RERUNNER_HMAC_KEY", "env-secret-key")
    expected_hmac = hmac.new(b"env-secret-key", expected_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    assert compute_entry_hash(entry, "GENESIS") == expected_hmac


def test_verify_cassette_integrity_empty() -> None:
    is_valid, error = verify_cassette_integrity([])
    assert is_valid is True
    assert error is None


def test_verify_cassette_integrity_expected_count() -> None:
    entry1 = _make_sample_entry(step=1)
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    # Match count
    is_valid, error = verify_cassette_integrity([entry1], expected_count=1)
    assert is_valid is True
    assert error is None

    # Mismatch count
    is_valid, error = verify_cassette_integrity([entry1], expected_count=2)
    assert is_valid is False
    assert error == "Entry count mismatch: expected 2 entries, but found 1"


def test_verify_cassette_integrity_broken_prev_hash() -> None:
    entry1 = _make_sample_entry(step=1, prev_hash="WRONG_GENESIS")
    entry1.entry_hash = compute_entry_hash(entry1, "WRONG_GENESIS")

    is_valid, error = verify_cassette_integrity([entry1])
    assert is_valid is False
    assert error == "Broken chain at step 1: expected prev_hash 'GENESIS', got 'WRONG_GENESIS'"


def test_verify_cassette_integrity_with_hmac_secret() -> None:
    key = "test-hmac-key"
    entry1 = _make_sample_entry(step=1)
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS", secret_key=key)

    # Valid with matching key
    is_valid, error = verify_cassette_integrity([entry1], secret_key=key)
    assert is_valid is True
    assert error is None

    # Invalid with different key
    is_valid, error = verify_cassette_integrity([entry1], secret_key="different-key")
    assert is_valid is False
    assert error is not None
    assert "Tampered entry detected at step 1" in error


def test_verify_cassette_integrity_broken_chain_at_later_step() -> None:
    entry1 = _make_sample_entry(step=1, prev_hash="GENESIS")
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    entry2 = _make_sample_entry(step=2, prev_hash=entry1.entry_hash)
    entry2.entry_hash = compute_entry_hash(entry2, entry1.entry_hash)

    # Step 3 has broken prev_hash
    entry3 = _make_sample_entry(step=3, prev_hash="CORRUPTED_HASH")
    entry3.entry_hash = compute_entry_hash(entry3, "CORRUPTED_HASH")

    is_valid, error = verify_cassette_integrity([entry1, entry2, entry3])
    assert is_valid is False
    assert error == f"Broken chain at step 3: expected prev_hash '{entry2.entry_hash}', got 'CORRUPTED_HASH'"


def test_verify_cassette_integrity_tampered_at_later_step() -> None:
    entry1 = _make_sample_entry(step=1, prev_hash="GENESIS")
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    entry2 = _make_sample_entry(step=2, prev_hash=entry1.entry_hash)
    entry2.entry_hash = compute_entry_hash(entry2, entry1.entry_hash)

    # Tamper with entry2
    entry2.response.body = '{"output": "tampered"}'  # type: ignore[union-attr]

    is_valid, error = verify_cassette_integrity([entry1, entry2])
    assert is_valid is False
    assert error is not None
    assert "Tampered entry detected at step 2" in error


def test_compute_merkle_root_even_and_large_trees() -> None:
    # 2 entries (exact pair)
    e1 = _make_sample_entry(step=1, prev_hash="GENESIS")
    e1.entry_hash = compute_entry_hash(e1, "GENESIS")
    e2 = _make_sample_entry(step=2, prev_hash=e1.entry_hash)
    e2.entry_hash = compute_entry_hash(e2, e1.entry_hash)

    expected_combined = hashlib.sha256(
        e1.entry_hash.encode("utf-8") + e2.entry_hash.encode("utf-8")
    ).digest()
    root_2 = compute_merkle_root([e1, e2])
    assert root_2 == expected_combined.hex()

    # 4 entries
    e3 = _make_sample_entry(step=3, prev_hash=e2.entry_hash)
    e3.entry_hash = compute_entry_hash(e3, e2.entry_hash)
    e4 = _make_sample_entry(step=4, prev_hash=e3.entry_hash)
    e4.entry_hash = compute_entry_hash(e4, e3.entry_hash)

    h12 = hashlib.sha256(e1.entry_hash.encode("utf-8") + e2.entry_hash.encode("utf-8")).digest()
    h34 = hashlib.sha256(e3.entry_hash.encode("utf-8") + e4.entry_hash.encode("utf-8")).digest()
    expected_root_4 = hashlib.sha256(h12 + h34).digest().hex()

    assert compute_merkle_root([e1, e2, e3, e4]) == expected_root_4


def test_compute_merkle_root_empty_entries() -> None:
    assert compute_merkle_root([]) == hashlib.sha256(b"").hexdigest()


def test_compute_merkle_root_single_entry() -> None:
    entry = _make_sample_entry(step=1)
    entry.entry_hash = compute_entry_hash(entry, "GENESIS")
    root = compute_merkle_root([entry])
    assert len(root) == 64
    assert root == hashlib.sha256(entry.entry_hash.encode("utf-8")).hexdigest()


def test_compute_merkle_root_odd_entries_and_fallback_hash() -> None:
    # 3 entries tests the odd-count duplicate branch
    entries = []
    prev = "GENESIS"
    for i in range(1, 4):
        e = _make_sample_entry(step=i, prev_hash=prev)
        # Leave entry_hash None on purpose to test the fallback branch:
        # compute_entry_hash(entry, entry.prev_hash)
        e.entry_hash = None
        prev = compute_entry_hash(e, prev)
        entries.append(e)

    root = compute_merkle_root(entries)
    assert isinstance(root, str)
    assert len(root) == 64

    # Determinism
    root2 = compute_merkle_root(entries)
    assert root == root2


@pytest.mark.skipif(not HAS_CRYPTOGRAPHY, reason="cryptography not installed")
def test_ed25519_keypair_and_signatures() -> None:
    priv_pem, pub_pem = generate_ed25519_keypair()
    assert b"BEGIN PRIVATE KEY" in priv_pem
    assert b"BEGIN PUBLIC KEY" in pub_pem

    merkle_root = hashlib.sha256(b"merkle-tree-root").hexdigest()
    sig_b64 = sign_merkle_root_ed25519(merkle_root, priv_pem)
    assert isinstance(sig_b64, str)

    # Verification passes
    assert verify_merkle_root_ed25519(merkle_root, sig_b64, pub_pem) is True

    # Tampered root fails
    tampered_root = hashlib.sha256(b"tampered-root").hexdigest()
    assert verify_merkle_root_ed25519(tampered_root, sig_b64, pub_pem) is False

    # Corrupted signature fails
    corrupt_sig = base64.b64encode(b"invalid_signature_bytes_not_matching_key").decode("ascii")
    assert verify_merkle_root_ed25519(merkle_root, corrupt_sig, pub_pem) is False

    # Invalid base64 signature fails gracefully
    assert verify_merkle_root_ed25519(merkle_root, "not-valid-base64!@#$", pub_pem) is False


def test_load_ed25519_module_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    orig_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if "cryptography" in name:
            raise ImportError("Mocked missing cryptography")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="Ed25519 signing requires 'cryptography'"):
        _load_ed25519_module()
