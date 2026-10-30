"""Tests for the optional Sether PII redaction backend. All fixture values are fictional."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path

import httpx
import pytest

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette
from rerunner.sanitizer import (
    SetherRedactor,
    sanitize_body,
    sanitize_chunks,
    sanitize_headers,
    sanitize_string,
    sanitize_url,
)
from rerunner.transport import CassetteTransport

pytest.importorskip("sether")

EMAIL = "ops@acme-corp.technology"
INTL_PHONE = "+44 20 7946 0958"
NATIONAL_PHONE_NG = "0803 123 4567"
NATIONAL_PHONE_GB = "020 7946 0958"
AMEX = "3782 822463 10005"
VISA = "4111 1111 1111 1111"
SSN = "123-45-6789"
ORDER_ID = "ORD-20240601-000123"
DUMMY_KEY = "sk-" + "12345678901234567890123456789012"

NON_PII_VALUES = [
    ORDER_ID,
    "1719878400000",
    "1719878400",
    "1.2.3.4",
    "v0.27.0",
    "2024-06-01T12:00:00Z",
    "123e4567-e89b-12d3-a456-426614174000",
    "1234567890123456",
    "4155550123",
    "987654321",
    "gpt-4-0613",
    "tokens: 1048576",
]

SSE_CHUNKS = [
    f'data: {{"token":"email {EMAIL}"}}\n\n'.encode(),
    f'data: {{"token":"phone {INTL_PHONE}"}}\n\n'.encode(),
    b"data: [DONE]\n\n",
]
REDACTED_SSE_CHUNKS = [
    'data: {"token":"email [REDACTED_EMAIL]"}\n\n',
    'data: {"token":"phone [REDACTED_PHONE]"}\n\n',
    "data: [DONE]\n\n",
]


class _ChunkStream(httpx.SyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks


def _echo(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"echo": json.loads(request.content)})


def test_default_entities_emit_builtin_placeholders() -> None:
    redactor = SetherRedactor()
    assert redactor.entities == ["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "US_SSN"]
    assert redactor.phone_regions == []
    assert redactor.redact(f"email {EMAIL}, phone {INTL_PHONE}, card {AMEX}, ssn {SSN}") == (
        "email [REDACTED_EMAIL], phone [REDACTED_PHONE], "
        "card [REDACTED_CREDIT_CARD], ssn [REDACTED_SSN]"
    )


def test_entity_selection_limits_redaction() -> None:
    redactor = SetherRedactor(entities=["EMAIL_ADDRESS"])
    assert redactor.entities == ["EMAIL_ADDRESS"]
    assert redactor.redact(f"{EMAIL} {INTL_PHONE}") == f"[REDACTED_EMAIL] {INTL_PHONE}"


@pytest.mark.parametrize("entities", [[], ["IP_ADDRESS"], ["EMAIL_ADDRESS", "PERSON"]])
def test_unsupported_entities_are_rejected(entities: list[str]) -> None:
    with pytest.raises(ValueError, match="non-empty subset"):
        SetherRedactor(entities=entities)


def test_repeated_values_are_all_redacted() -> None:
    text = f"{EMAIL}, again {EMAIL}; call {INTL_PHONE} or {INTL_PHONE}"
    cleaned = SetherRedactor().redact(text)
    assert EMAIL not in cleaned
    assert INTL_PHONE not in cleaned
    assert cleaned.count("[REDACTED_EMAIL]") == 2
    assert cleaned.count("[REDACTED_PHONE]") == 2


def test_overlapping_matches_leave_no_fragment() -> None:
    text = "mail +442079460958@example.org end"
    assert SetherRedactor().redact(text) == "mail [REDACTED_PHONE] end"


def test_phone_regions_add_national_formats() -> None:
    text = f"NG {NATIONAL_PHONE_NG}, GB {NATIONAL_PHONE_GB}, intl {INTL_PHONE}"
    assert SetherRedactor().redact(text) == (
        f"NG {NATIONAL_PHONE_NG}, GB {NATIONAL_PHONE_GB}, intl [REDACTED_PHONE]"
    )
    regional = SetherRedactor(phone_regions=["NG", "GB"])
    assert regional.phone_regions == ["NG", "GB"]
    assert regional.redact(text) == (
        "NG [REDACTED_PHONE], GB [REDACTED_PHONE], intl [REDACTED_PHONE]"
    )


def test_unknown_phone_region_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown phone regions"):
        SetherRedactor(phone_regions=["XX"])


@pytest.mark.parametrize("value", NON_PII_VALUES)
def test_backend_adds_no_false_positives(value: str) -> None:
    text = f"id {value} end"
    assert sanitize_string(text, pii_redactor=SetherRedactor()) == sanitize_string(text)


def test_backend_adds_coverage_beyond_builtin_patterns() -> None:
    text = f"{EMAIL}, {INTL_PHONE}, {AMEX}"
    assert sanitize_string(text) == text
    assert sanitize_string(text, pii_redactor=SetherRedactor()) == (
        "[REDACTED_EMAIL], [REDACTED_PHONE], [REDACTED_CREDIT_CARD]"
    )


def test_backend_composes_with_secret_masking() -> None:
    text = f"Bearer {'a' * 24} key {DUMMY_KEY} contact {EMAIL} card {VISA}"
    assert sanitize_string(text, pii_redactor=SetherRedactor()) == (
        "Bearer [REDACTED_TOKEN] key [REDACTED_OPENAI_KEY] "
        "contact [REDACTED_EMAIL] card [REDACTED_CREDIT_CARD]"
    )


def test_sanitize_body_keeps_json_structure() -> None:
    body = json.dumps(
        {
            "customer": {"email": EMAIL, "phone": INTL_PHONE},
            "created": 1730000000,
            "version": "1.2.3.4",
            "ok": True,
        }
    )
    assert json.loads(sanitize_body(body, pii_redactor=SetherRedactor())) == {
        "customer": {"email": "[REDACTED_EMAIL]", "phone": "[REDACTED_PHONE]"},
        "created": 1730000000,
        "version": "1.2.3.4",
        "ok": True,
    }


def test_headers_and_urls_are_redacted() -> None:
    redactor = SetherRedactor()
    headers = sanitize_headers(
        {"X-Customer-Email": EMAIL, "Content-Type": "application/json"}, pii_redactor=redactor
    )
    assert headers == {"x-customer-email": "[REDACTED_EMAIL]", "content-type": "application/json"}

    url = sanitize_url(
        f"https://api.example.test/customers/{EMAIL}?contact={EMAIL}", pii_redactor=redactor
    )
    assert EMAIL not in url
    assert url.count("REDACTED_EMAIL") == 2


def test_buffered_cassette_bytes_are_clean_and_replay_matches(tmp_path: Path) -> None:
    cassette_path = tmp_path / "support.jsonl"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _echo(request)

    network = httpx.MockTransport(handler)
    payload = {"customer": EMAIL, "phone": INTL_PHONE, "card": AMEX, "order": ORDER_ID}

    record_transport = CassetteTransport(
        cassette_path, mode="record", real_transport=network, pii_redactor=SetherRedactor()
    )
    with httpx.Client(transport=record_transport) as client:
        live = client.post("https://api.example.test/v1/tickets", json=payload)
    assert live.json()["echo"] == payload

    raw = cassette_path.read_bytes()
    for value in (EMAIL, INTL_PHONE, AMEX):
        assert value.encode() not in raw
    assert ORDER_ID.encode() in raw

    entry = Cassette.load(cassette_path).entries[0]
    assert entry.request is not None
    assert entry.response is not None
    assert json.loads(entry.request.body) == {
        "customer": "[REDACTED_EMAIL]",
        "phone": "[REDACTED_PHONE]",
        "card": "[REDACTED_CREDIT_CARD]",
        "order": ORDER_ID,
    }
    assert json.loads(entry.response.body)["echo"]["card"] == "[REDACTED_CREDIT_CARD]"

    replay_transport = CassetteTransport(cassette_path, mode="replay", real_transport=network)
    with httpx.Client(transport=replay_transport) as client:
        replayed = client.post("https://api.example.test/v1/tickets", json=payload)
    assert replayed.json()["echo"]["customer"] == "[REDACTED_EMAIL]"
    assert calls == 1


@pytest.mark.asyncio
async def test_async_buffered_cassette_bytes_are_clean(tmp_path: Path) -> None:
    cassette_path = tmp_path / "support-async.jsonl"

    async def handler(request: httpx.Request) -> httpx.Response:
        return _echo(request)

    record_transport = AsyncCassetteTransport(
        cassette_path,
        mode="record",
        real_transport=httpx.MockTransport(handler),
        pii_redactor=SetherRedactor(),
    )
    async with httpx.AsyncClient(transport=record_transport) as client:
        live = await client.post("https://api.example.test/v1/tickets", json={"customer": EMAIL})
    assert live.json()["echo"] == {"customer": EMAIL}

    raw = cassette_path.read_bytes()
    assert EMAIL.encode() not in raw
    assert b"[REDACTED_EMAIL]" in raw


def test_streaming_chunks_are_clean_and_replay_matches(tmp_path: Path) -> None:
    cassette_path = tmp_path / "stream.jsonl"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=_ChunkStream(SSE_CHUNKS),
            request=request,
        )

    network = httpx.MockTransport(handler)
    request_body = {"model": "test", "stream": True}

    record_transport = CassetteTransport(
        cassette_path, mode="record", real_transport=network, pii_redactor=SetherRedactor()
    )
    with (
        httpx.Client(transport=record_transport) as client,
        client.stream("POST", "https://api.example.test/v1/chat", json=request_body) as response,
    ):
        assert list(response.iter_raw()) == SSE_CHUNKS

    raw = cassette_path.read_bytes()
    assert EMAIL.encode() not in raw
    assert INTL_PHONE.encode() not in raw

    recorded = Cassette.load(cassette_path).entries[0].response
    assert recorded is not None
    assert recorded.is_streaming is True
    assert recorded.chunks == REDACTED_SSE_CHUNKS

    replay_transport = CassetteTransport(cassette_path, mode="replay", real_transport=network)
    with (
        httpx.Client(transport=replay_transport) as client,
        client.stream("POST", "https://api.example.test/v1/chat", json=request_body) as response,
    ):
        assert [chunk.decode("utf-8") for chunk in response.iter_raw()] == REDACTED_SSE_CHUNKS
    assert calls == 1


SPLIT_SSE_CHUNKS = [
    b'data: {"token":"mail ops@acme-co',
    b'rp.technology done"}\n\n',
    b"data: [DONE]\n\n",
]
REDACTED_SPLIT_SSE_CHUNKS = [
    'data: {"token":"mail ',
    '[REDACTED_EMAIL] done"}\n\n',
    "data: [DONE]\n\n",
]


def test_sanitize_chunks_applies_backend_across_boundaries() -> None:
    chunks = [chunk.decode("utf-8") for chunk in SPLIT_SSE_CHUNKS]
    assert sanitize_chunks(chunks) == chunks
    assert sanitize_chunks(chunks, pii_redactor=SetherRedactor()) == REDACTED_SPLIT_SSE_CHUNKS


def test_streaming_value_split_across_chunks_is_clean_and_replays(tmp_path: Path) -> None:
    cassette_path = tmp_path / "split-stream.jsonl"
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=_ChunkStream(SPLIT_SSE_CHUNKS),
            request=request,
        )

    network = httpx.MockTransport(handler)
    request_body = {"model": "test", "stream": True}

    record_transport = CassetteTransport(
        cassette_path, mode="record", real_transport=network, pii_redactor=SetherRedactor()
    )
    with (
        httpx.Client(transport=record_transport) as client,
        client.stream("POST", "https://api.example.test/v1/chat", json=request_body) as response,
    ):
        assert list(response.iter_raw()) == SPLIT_SSE_CHUNKS

    raw = cassette_path.read_bytes()
    assert b"ops@acme" not in raw
    assert b"acme-corp" not in raw

    recorded = Cassette.load(cassette_path).entries[0].response
    assert recorded is not None
    assert recorded.chunks == REDACTED_SPLIT_SSE_CHUNKS

    replay_transport = CassetteTransport(cassette_path, mode="replay", real_transport=network)
    with (
        httpx.Client(transport=replay_transport) as client,
        client.stream("POST", "https://api.example.test/v1/chat", json=request_body) as response,
    ):
        assert [chunk.decode("utf-8") for chunk in response.iter_raw()] == REDACTED_SPLIT_SSE_CHUNKS
    assert calls == 1
