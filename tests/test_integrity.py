"""Unit tests for cryptographic SHA-256 integrity checks."""

from __future__ import annotations

from rerunner.integrity import compute_entry_hash, verify_cassette_integrity
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse


def test_hash_chain_verification_passes() -> None:
    req = RecordedRequest(
        method="POST", url="https://api.anthropic.com/v1/messages", request_key="key1"
    )
    resp = RecordedResponse(status_code=200, body='{"output": "ok"}')

    entry1 = CassetteEntry(
        step=1, entry_type="http", request=req, response=resp, prev_hash="GENESIS"
    )
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    entry2 = CassetteEntry(
        step=2, entry_type="http", request=req, response=resp, prev_hash=entry1.entry_hash
    )
    entry2.entry_hash = compute_entry_hash(entry2, entry1.entry_hash)

    is_valid, error = verify_cassette_integrity([entry1, entry2])
    assert is_valid is True
    assert error is None


def test_tamper_detection_flags_modified_body() -> None:
    req = RecordedRequest(
        method="POST", url="https://api.openai.com/v1/chat/completions", request_key="key1"
    )
    resp = RecordedResponse(status_code=200, body='{"content": "Original response"}')

    entry1 = CassetteEntry(
        step=1, entry_type="http", request=req, response=resp, prev_hash="GENESIS"
    )
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS")

    # Attacker tampers with the response body
    entry1.response.body = '{"content": "Hacked response"}'  # type: ignore[union-attr]

    is_valid, error = verify_cassette_integrity([entry1])
    assert is_valid is False
    assert "Tampered entry detected at step 1" in (error or "")
