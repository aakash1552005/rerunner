"""Tamper and accidental corruption detection via SHA-256 hash chaining, with optional cryptographic HMAC signing."""

from __future__ import annotations

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
