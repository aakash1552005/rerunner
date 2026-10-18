"""Comprehensive regression test suite covering all critical audit findings and bug fixes."""

from __future__ import annotations

import json
from pathlib import Path
import httpx
import pytest

from rerunner.cassette import Cassette
from rerunner.integrity import compute_entry_hash, verify_cassette_integrity
from rerunner.sanitizer import sanitize_body, sanitize_string, sanitize_url
from rerunner.side_effects import SideEffectError, set_active_cassette, side_effect
from rerunner.transport import CassetteTransport
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.integrations.openai import wrap_openai
from rerunner.integrations.anthropic import wrap_anthropic


def test_sanitizer_preserves_valid_json_and_numeric_timestamps() -> None:
    """Ensure OpenAI-style Unix timestamp numbers like created: 1730000000 are not corrupted into phone tags."""
    openai_json = json.dumps(
        {
            "id": "chatcmpl-12345",
            "created": 1730000000,
            "model": "gpt-4o",
            "usage": {"total_tokens": 42},
            "system_fingerprint": "fp_44709d6fcb",
            "version": "1.2.3.4",
            "tracking_id": "1234567890123456",
            "user_prompt": "Send key sk-proj-1234567890abcdef1234567890123456 to test@example.com",
        }
    )

    sanitized = sanitize_body(openai_json)

    # Must parse back into valid JSON
    parsed = json.loads(sanitized)
    assert parsed["created"] == 1730000000
    assert isinstance(parsed["created"], int)
    assert parsed["usage"]["total_tokens"] == 42
    assert parsed["version"] == "1.2.3.4"
    assert parsed["tracking_id"] == "1234567890123456"
    assert "[REDACTED_OPENAI_PROJECT_KEY]" in parsed["user_prompt"]
    assert "[REDACTED_EMAIL]" in parsed["user_prompt"]


def test_url_sanitizer_removes_api_keys_from_query_parameters() -> None:
    """Ensure Gemini/Google/API keys in URL query strings are redacted."""
    raw_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?"
        "key=AIzaSyB1234567890abcdefghijklmnopqrstuv&client=test"
    )
    cleaned = sanitize_url(raw_url)
    assert "AIzaSy" not in cleaned
    assert "key=%5BREDACTED_API_KEY%5D" in cleaned or "key=[REDACTED_API_KEY]" in cleaned
    assert "client=test" in cleaned


def test_repeated_identical_requests_replay_in_sequential_order(tmp_path: Path) -> None:
    """Agent loops and retries making identical requests must return 1, 2, 3 in recorded order."""
    cassette_file = tmp_path / "repeated.jsonl"
    url = "https://api.example.com/status"

    # Step 1: Record 3 identical calls returning 1, 2, 3
    responses = [
        httpx.Response(200, json={"attempt": 1}),
        httpx.Response(200, json={"attempt": 2}),
        httpx.Response(200, json={"attempt": 3}),
    ]

    class MockSequenceTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.count = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            resp = responses[self.count]
            self.count += 1
            return resp

    record_transport = CassetteTransport(
        cassette_file, mode="record", real_transport=MockSequenceTransport()
    )
    client_rec = httpx.Client(transport=record_transport)
    assert client_rec.get(url).json()["attempt"] == 1
    assert client_rec.get(url).json()["attempt"] == 2
    assert client_rec.get(url).json()["attempt"] == 3
    client_rec.close()

    # Step 2: Replay the 3 calls - must return 1, 2, 3 and NOT 1, 1, 1
    replay_transport = CassetteTransport(cassette_file, mode="replay")
    client_play = httpx.Client(transport=replay_transport)
    assert client_play.get(url).json()["attempt"] == 1
    assert client_play.get(url).json()["attempt"] == 2
    assert client_play.get(url).json()["attempt"] == 3
    client_play.close()


def test_side_effect_fails_closed_on_unrecorded_action(tmp_path: Path) -> None:
    """In replay mode, an unrecorded side effect must fail closed by raising SideEffectError rather than running live."""
    cassette_file = tmp_path / "side_effect.jsonl"
    executed_live = False

    @side_effect(name="send_payment")
    def send_payment(amount: float) -> str:
        nonlocal executed_live
        executed_live = True
        return f"paid_{amount}"

    # Setup empty cassette in replay mode
    cass = Cassette(cassette_file)
    cass.save()
    set_active_cassette(cass, mode="replay")

    with pytest.raises(SideEffectError, match="Side effects fail closed during replay"):
        send_payment(99.99)

    assert not executed_live, "Side effect must NEVER execute live during replay!"
    set_active_cassette(None)


def test_side_effect_matches_by_arguments_and_sanitizes_data(tmp_path: Path) -> None:
    """Side effects with different arguments match their respective results, and sensitive data is sanitized."""
    cassette_file = tmp_path / "side_effect_args.jsonl"

    @side_effect(name="process_card")
    def process_card(user: str, card: str) -> dict[str, str]:
        return {"status": "ok", "card_used": card}

    # Record two different users
    set_active_cassette(cassette_file, mode="record")
    process_card("alice", "4111 2222 3333 4444")
    process_card("bob", "5555 4444 3333 2222")
    set_active_cassette(None)

    # Inspect cassette to verify sensitive card numbers were redacted in args and results
    loaded = Cassette.load(cassette_file)
    assert len(loaded) == 2
    assert "[REDACTED_CREDIT_CARD]" in str(loaded.entries[0].side_effect_args)
    assert "[REDACTED_CREDIT_CARD]" in str(loaded.entries[0].side_effect_result)

    # Replay both in replay mode
    set_active_cassette(cassette_file, mode="replay")
    res_alice = process_card("alice", "4111 2222 3333 4444")
    res_bob = process_card("bob", "5555 4444 3333 2222")
    assert "[REDACTED_CREDIT_CARD]" in res_alice["card_used"]
    assert "[REDACTED_CREDIT_CARD]" in res_bob["card_used"]
    set_active_cassette(None)


def test_gzip_header_normalization_prevents_decoding_error(tmp_path: Path) -> None:
    """Response recorded with gzip content-encoding must have headers stripped so replay does not fail with DecodingError."""
    cassette_file = tmp_path / "gzip_test.jsonl"
    url = "https://api.example.com/gzip"

    class GzipMockTransport(httpx.BaseTransport):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            import gzip

            uncompressed = b'{"status":"compressed_content"}'
            compressed = gzip.compress(uncompressed)
            return httpx.Response(
                200,
                headers={"content-encoding": "gzip", "content-length": str(len(compressed))},
                content=compressed,
            )

    # Record response
    rec_transport = CassetteTransport(
        cassette_file, mode="record", real_transport=GzipMockTransport()
    )
    client_rec = httpx.Client(transport=rec_transport)
    rec_resp = client_rec.get(url)
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] == "compressed_content"
    client_rec.close()

    # Replay response - should cleanly decode without DecodingError
    play_transport = CassetteTransport(cassette_file, mode="replay")
    client_play = httpx.Client(transport=play_transport)
    play_resp = client_play.get(url)
    assert play_resp.status_code == 200
    assert play_resp.json()["status"] == "compressed_content"
    client_play.close()


def test_fork_mode_prevents_duplicate_step_numbering(tmp_path: Path) -> None:
    """Forking at step 2 from a 4-step cassette must produce sequential steps [1, 2, 3], not [1, 2, 3, 4, 3, 4]."""
    cassette_file = tmp_path / "fork_steps.jsonl"

    class StepMockTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.step = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.step += 1
            return httpx.Response(200, json={"step": self.step})

    # Record 4 initial steps
    rec_transport = CassetteTransport(
        cassette_file, mode="record", real_transport=StepMockTransport()
    )
    client = httpx.Client(transport=rec_transport)
    for i in range(1, 5):
        client.get(f"https://api.example.com/step/{i}")
    client.close()

    loaded = Cassette.load(cassette_file)
    assert [e.step for e in loaded] == [1, 2, 3, 4]

    # Fork at step 2, record a new step 3
    fork_transport = CassetteTransport(
        cassette_file, mode="fork", fork_step=2, real_transport=StepMockTransport()
    )
    client_fork = httpx.Client(transport=fork_transport)
    # Step 1 (replayed)
    client_fork.get("https://api.example.com/step/1")
    # Step 2 (replayed)
    client_fork.get("https://api.example.com/step/2")
    # Step 3 (live fork execution)
    client_fork.get("https://api.example.com/step/forked_step_3")
    client_fork.close()

    # Verify cassette step sequence has no duplicate steps
    reloaded = Cassette.load(cassette_file)
    step_sequence = [e.step for e in reloaded]
    assert step_sequence == [1, 2, 3], f"Expected [1, 2, 3], got {step_sequence}"


def test_hmac_cryptographic_integrity_verification(tmp_path: Path) -> None:
    """HMAC-SHA256 signing detects unauthorized modifications and recomputed hashes."""
    from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

    secret_key = "super-secret-ci-hmac-key"
    entry1 = CassetteEntry(
        step=1,
        entry_type="http",
        request=RecordedRequest(method="GET", url="https://example.com", headers={}, body="", request_key="key1"),
        response=RecordedResponse(status_code=200, headers={}, body="OK"),
    )
    entry1.prev_hash = "GENESIS"
    entry1.entry_hash = compute_entry_hash(entry1, "GENESIS", secret_key=secret_key)

    # Valid HMAC verify passes
    is_valid, err = verify_cassette_integrity([entry1], secret_key=secret_key)
    assert is_valid
    assert err is None

    # Verify fails if wrong secret key is provided
    is_valid_wrong, err_wrong = verify_cassette_integrity([entry1], secret_key="wrong-key")
    assert not is_valid_wrong
    assert "Tampered entry detected" in (err_wrong or "")


def test_async_client_wrappers_attach_async_transports(tmp_path: Path) -> None:
    """wrap_openai and wrap_anthropic attach AsyncCassetteTransport to async client instances."""

    class DummyAsyncClient:
        def __init__(self) -> None:
            self._client = httpx.AsyncClient()
            self._client._mounts = {"https://": httpx.AsyncHTTPTransport()}

    async_client = DummyAsyncClient()
    wrapped_openai = wrap_openai(async_client, tmp_path / "async_openai.jsonl", mode="record")
    assert isinstance(wrapped_openai._client._transport, AsyncCassetteTransport)
    assert len(wrapped_openai._client._mounts) == 0, "Proxy mounts must be cleared to prevent bypass"

    anthropic_async = DummyAsyncClient()
    wrapped_anthropic = wrap_anthropic(anthropic_async, tmp_path / "async_anthropic.jsonl", mode="record")
    assert isinstance(wrapped_anthropic._client._transport, AsyncCassetteTransport)
    assert len(wrapped_anthropic._client._mounts) == 0

    # Test sanitize_string directly
    cleaned_card = sanitize_string("Card 4111 2222 3333 4444")
    assert "[REDACTED_CREDIT_CARD]" in cleaned_card
