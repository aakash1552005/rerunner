"""Tamper and accidental corruption detection via SHA-256 hash chaining, with optional cryptographic HMAC signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rerunner.models import CassetteEntry


def canonical_entry_payload(entry: CassetteEntry) -> str:
    """Create a deterministic JSON string representing the entry without its hash."""
    data = entry.model_dump(exclude={"entry_hash"})
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_entry_hash(
    entry: CassetteEntry, prev_hash: str, secret_key: str | bytes | None = None
) -> str:
    """Compute SHA-256 hash (or HMAC-SHA256 if secret_key is provided) chaining prev_hash with canonical entry payload."""
    payload = f"{prev_hash}:{canonical_entry_payload(entry)}"
    key = secret_key or os.getenv("RERUNNER_HMAC_KEY")

    if key:
        key_bytes = key.encode("utf-8") if isinstance(key, str) else key
        return hmac.new(key_bytes, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_cassette_integrity(
    entries: list[CassetteEntry],
    secret_key: str | bytes | None = None,
    expected_count: int | None = None,
) -> tuple[bool, str | None]:
    """Verify that every entry in the cassette adheres to the hash chain and entry count.

    Without an HMAC secret key, this verifies accidental corruption, missing lines, or reordering.
    With an HMAC secret key (or RERUNNER_HMAC_KEY env var), this provides cryptographic tamper resistance.

    Returns:
        (True, None) if the chain is fully verified and untampered.
        (False, error_message) if any link in the chain is broken or modified.
    """
    if expected_count is not None and len(entries) != expected_count:
        return (
            False,
            f"Entry count mismatch: expected {expected_count} entries, but found {len(entries)}",
        )

    if not entries:
        return True, None

    expected_prev = "GENESIS"
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return (
                False,
                f"Broken chain at step {entry.step}: expected prev_hash '{expected_prev}', got '{entry.prev_hash}'",
            )

        recomputed_hash = compute_entry_hash(entry, expected_prev, secret_key=secret_key)
        if recomputed_hash != entry.entry_hash:
            return (
                False,
                f"Tampered entry detected at step {entry.step}: recorded hash '{entry.entry_hash}' does not match recomputed '{recomputed_hash}'",
            )

        expected_prev = entry.entry_hash

    return True, None


def compute_merkle_root(entries: list[CassetteEntry]) -> str:
    """Compute a deterministic SHA-256 Merkle tree root over cassette entry hashes (Issue #82)."""
    if not entries:
        return hashlib.sha256(b"").hexdigest()

    level: list[bytes] = [
        (entry.entry_hash or compute_entry_hash(entry, entry.prev_hash)).encode("utf-8")
        for entry in entries
    ]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level: list[bytes] = []
        for idx in range(0, len(level), 2):
            combined = hashlib.sha256(level[idx] + level[idx + 1]).digest()
            next_level.append(combined)
        level = next_level
    return level[0].hex() if len(level[0]) == 32 else hashlib.sha256(level[0]).hexdigest()


def _load_ed25519_module() -> tuple[object, object]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise ImportError(
            "Ed25519 signing requires 'cryptography'. Install with: pip install 'rerunner[ed25519]'"
        ) from exc
    return ed25519, serialization


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate an asymmetric Ed25519 (private_pem, public_pem) keypair."""
    ed25519_mod, serialization_mod = _load_ed25519_module()
    private_key = ed25519_mod.Ed25519PrivateKey.generate()  # type: ignore[attr-defined]
    public_key = private_key.public_key()
    private_pem: bytes = private_key.private_bytes(
        encoding=serialization_mod.Encoding.PEM,  # type: ignore[attr-defined]
        format=serialization_mod.PrivateFormat.PKCS8,  # type: ignore[attr-defined]
        encryption_algorithm=serialization_mod.NoEncryption(),  # type: ignore[attr-defined]
    )
    public_pem: bytes = public_key.public_bytes(
        encoding=serialization_mod.Encoding.PEM,  # type: ignore[attr-defined]
        format=serialization_mod.PublicFormat.SubjectPublicKeyInfo,  # type: ignore[attr-defined]
    )
    return private_pem, public_pem


def sign_merkle_root_ed25519(merkle_root: str, private_key_pem: bytes) -> str:
    """Sign a Merkle root hex digest with an Ed25519 private key, returning base64."""
    _, serialization_mod = _load_ed25519_module()
    private_key = serialization_mod.load_pem_private_key(  # type: ignore[attr-defined]
        private_key_pem, password=None
    )
    signature: bytes = private_key.sign(merkle_root.encode("utf-8"))
    return base64.b64encode(signature).decode("ascii")


def verify_merkle_root_ed25519(merkle_root: str, signature_b64: str, public_key_pem: bytes) -> bool:
    """Verify a base64 Ed25519 signature over a Merkle root hex digest."""
    from cryptography.exceptions import InvalidSignature

    _, serialization_mod = _load_ed25519_module()
    public_key = serialization_mod.load_pem_public_key(public_key_pem)  # type: ignore[attr-defined]
    try:
        signature = base64.b64decode(signature_b64.encode("ascii"))
        public_key.verify(signature, merkle_root.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False
