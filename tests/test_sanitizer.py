"""Unit tests for automated secret, API key, and PII redactor."""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest

from rerunner.sanitizer import (
    SetherRedactor,
    sanitize_body,
    sanitize_chunks,
    sanitize_headers,
    sanitize_payload,
    sanitize_string,
    sanitize_url,
)


def test_sanitize_anthropic_and_openai_keys() -> None:
    ant_key = "sk-ant-" + "api03-abcdef1234567890abcdef1234567890"
    proj_key = "sk-proj-" + "1234567890abcdef1234567890123456"
    text = f"Using key {ant_key} and {proj_key}"
    cleaned = sanitize_string(text)
    assert "sk-ant" not in cleaned
    assert "[REDACTED_ANTHROPIC_KEY]" in cleaned
    assert "sk-proj" not in cleaned
    assert "[REDACTED_OPENAI_PROJECT_KEY]" in cleaned


def test_sanitize_google_slack_and_cloud_tokens() -> None:
    # Use split parts so GitHub secret scanning scanner does not flag test fixture strings
    slack_dummy = "xoxb-" + "000000000000-" + "0000000000000-" + "abcdef123456789012345678"
    google_dummy = "AIzaSy" + "B1234567890abcdefghijklmnopqrstuv"
    text = f"Google {google_dummy} Slack {slack_dummy}"
    cleaned = sanitize_string(text)
    assert "[REDACTED_GOOGLE_API_KEY]" in cleaned
    assert "[REDACTED_SLACK_TOKEN]" in cleaned


def test_sanitize_pii_emails_phones_and_ips() -> None:
    text = "Contact alice.smith@enterprise.org at +1 (555) 234-5678 or 192.168.1.105 with card 4111 2222 3333 4444"
    cleaned = sanitize_string(text)
    assert "[REDACTED_EMAIL]" in cleaned
    assert "alice.smith" not in cleaned
    assert "[REDACTED_PHONE]" in cleaned
    assert "(555) 234-5678" not in cleaned
    assert "[REDACTED_IP_ADDRESS]" in cleaned
    assert "[REDACTED_CREDIT_CARD]" in cleaned


def test_sanitize_headers() -> None:
    headers = {
        "Authorization": "Bearer secret_jwt_token_12345",
        "X-Api-Key": "my-secret-key",
        "Content-Type": "application/json",
        "User-Email": "dev@company.com",
    }
    cleaned = sanitize_headers(headers)
    assert cleaned["authorization"] == "[REDACTED]"
    assert cleaned["x-api-key"] == "[REDACTED]"
    assert cleaned["content-type"] == "application/json"
    assert cleaned["user-email"] == "[REDACTED_EMAIL]"


def test_sanitize_nested_payload() -> None:
    dummy_key = "sk-" + "12345678901234567890123456789012"
    payload = {
        "prompt": f"Here is key {dummy_key}",
        "nested": ["Bearer secret_token_xyz_12345", "contact@test.org"],
    }
    cleaned = sanitize_payload(payload)
    assert "[REDACTED_OPENAI_KEY]" in cleaned["prompt"]
    assert "Bearer [REDACTED_TOKEN]" in cleaned["nested"][0]
    assert "[REDACTED_EMAIL]" in cleaned["nested"][1]


def test_sanitize_with_custom_patterns() -> None:
    custom = [
        (re.compile(r"INTERNAL-[0-9]{4}"), "[REDACTED_INTERNAL_ID]"),
    ]
    text = "Project ticket is INTERNAL-9876"
    cleaned = sanitize_string(text, custom_patterns=custom)
    assert cleaned == "Project ticket is [REDACTED_INTERNAL_ID]"


def test_sanitize_url_sensitive_query_parameters() -> None:
    raw_url = "https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSySecret123&client_secret=super_secret&token=tok_999&search=test_term"
    cleaned = sanitize_url(raw_url)
    assert "AIzaSySecret123" not in cleaned
    assert "super_secret" not in cleaned
    assert "tok_999" not in cleaned
    assert "key=%5BREDACTED%5D" in cleaned or "key=[REDACTED]" in cleaned
    assert "client_secret=%5BREDACTED%5D" in cleaned or "client_secret=[REDACTED]" in cleaned
    assert "search=test_term" in cleaned


class _MarkerRedactor:
    """Minimal pii_redactor stub recording the text it receives."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def redact(self, text: str) -> str:
        self.seen.append(text)
        return text.replace("ticket-7781", "[REDACTED_TICKET]")


def test_pii_redactor_runs_after_builtin_patterns() -> None:
    dummy_key = "sk-" + "12345678901234567890123456789012"
    redactor = _MarkerRedactor()
    cleaned = sanitize_string(f"key {dummy_key} ref ticket-7781", pii_redactor=redactor)
    assert cleaned == "key [REDACTED_OPENAI_KEY] ref [REDACTED_TICKET]"
    assert redactor.seen == ["key [REDACTED_OPENAI_KEY] ref ticket-7781"]


def test_pii_redactor_applies_through_json_bodies() -> None:
    body = '{"ref": "ticket-7781", "created": 1730000000, "tags": ["ticket-7781"]}'
    cleaned = sanitize_body(body, pii_redactor=_MarkerRedactor())
    assert json.loads(cleaned) == {
        "ref": "[REDACTED_TICKET]",
        "created": 1730000000,
        "tags": ["[REDACTED_TICKET]"],
    }


def test_sether_redactor_requires_optional_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sether", None)
    with pytest.raises(ImportError, match=r"rerunner\[sether\]"):
        SetherRedactor()


def test_default_sanitizer_never_imports_sether() -> None:
    script = (
        "import sys\n"
        "import rerunner\n"
        "rerunner.sanitize_string('contact alice.smith@example.org')\n"
        "assert 'sether' not in sys.modules\n"
        "assert 'phonenumbers' not in sys.modules\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


SPLIT_SSE_CHUNKS = [
    'data: {"token":"mail alice.smith@exam',
    'ple.org done"}\n\n',
    "data: [DONE]\n\n",
]


def test_sanitize_chunks_redacts_values_split_across_chunks() -> None:
    assert sanitize_chunks(SPLIT_SSE_CHUNKS) == [
        'data: {"token":"mail ',
        '[REDACTED_EMAIL] done"}\n\n',
        "data: [DONE]\n\n",
    ]


def test_sanitize_chunks_keeps_boundaries_when_nothing_straddles() -> None:
    chunks = [
        'data: {"token":"Hello"}\n\n',
        'data: {"token":"mail alice.smith@example.org"}\n\n',
        "data: [DONE]\n\n",
    ]
    assert sanitize_chunks(chunks) == [sanitize_string(chunk) for chunk in chunks]


def test_sanitize_chunks_places_placeholder_where_value_completes() -> None:
    chunks = ["mail ", "alice", ".smith", "@example", ".org", " done"]
    assert sanitize_chunks(chunks) == ["mail ", "", "", "", "[REDACTED_EMAIL]", " done"]


def test_sanitize_chunks_leaves_unrelated_chunks_in_place() -> None:
    chunks = [
        'data: {"token":"alice.smith@exam',
        'ple.org"}\n\n',
        'data: {"token":"unrelated"}\n\n',
        'data: {"token":"bob.jones@exam',
        'ple.org"}\n\n',
        "data: [DONE]\n\n",
    ]
    assert sanitize_chunks(chunks) == [
        'data: {"token":"',
        '[REDACTED_EMAIL]"}\n\n',
        'data: {"token":"unrelated"}\n\n',
        'data: {"token":"',
        '[REDACTED_EMAIL]"}\n\n',
        "data: [DONE]\n\n",
    ]


def test_sanitize_chunks_at_every_split_point() -> None:
    text = (
        'data: {"email":"alice.smith@example.org","card":"4111 1111 1111 1111",'
        '"ip":"192.168.1.105","key":"sk-12345678901234567890123456789012"}\n\n'
    )
    expected = sanitize_string(text)
    assert "alice.smith" not in expected

    for index in range(1, len(text)):
        cleaned = sanitize_chunks([text[:index], text[index:]])
        assert len(cleaned) == 2
        assert "".join(cleaned) == expected

    for first in range(1, len(text) - 1, 5):
        for second in range(first + 1, len(text), 7):
            cleaned = sanitize_chunks([text[:first], text[first:second], text[second:]])
            assert len(cleaned) == 3
            assert "".join(cleaned) == expected


def test_sanitize_chunks_applies_custom_patterns_across_boundaries() -> None:
    custom = [(re.compile(r"INTERNAL-[0-9]{4}"), "[REDACTED_INTERNAL_ID]")]
    cleaned = sanitize_chunks(["ticket INTERNAL-98", "76 open"], custom_patterns=custom)
    assert cleaned == ["ticket ", "[REDACTED_INTERNAL_ID] open"]


def test_sanitize_chunks_keeps_count_when_replacement_grows() -> None:
    custom = [(re.compile(r"abc"), "abcd")]
    assert sanitize_chunks(["ab", "c"], custom_patterns=custom) == ["ab", "cd"]


def test_sanitize_chunks_may_place_placeholder_before_value_completes() -> None:
    # "alice@example.co" is already a valid email, so the placeholder lands one chunk early
    chunks = ["mail alice@example.co", "m", " done"]
    assert sanitize_chunks(chunks) == ["mail [REDACTED_EMAIL]", "", " done"]


def test_sanitize_chunks_keeps_pattern_context_from_earlier_chunks() -> None:
    chunks = ["Bearer", " ", "abcdefghijklmnopqrst", "uvwxyz ok"]
    assert sanitize_chunks(chunks) == ["Bearer", " ", "[REDACTED_TOKEN]", " ok"]


def test_sanitize_chunks_keeps_boundary_context_from_earlier_chunks() -> None:
    # Glued to "ref" the digits are not a card, and the rescan must see that context
    chunks = ["ref", "4111 1111 1111 1111", " ok"]
    assert sanitize_chunks(chunks) == chunks


class _CountingRedactor:
    """pii_redactor stub that records how much text it is asked to scan."""

    def __init__(self) -> None:
        self.scanned = 0

    def redact(self, text: str) -> str:
        self.scanned += len(text)
        return text


def _event_stream(shape: str) -> list[str]:
    """Chunk 800 SSE events holding an email so that no chunk sanitizes correctly on its own."""
    chunks: list[str] = []
    for index in range(800):
        if shape == "value split in two":
            chunks.extend([f'data: {{"email":"user{index}@', 'example.org"}\n\n'])
        elif shape == "boundary at the end of the value":
            chunks.extend([f'data: {{"email":"user{index}@', "example.org", '"}\n\n'])
        elif shape == "every chunk ends inside a value":
            # Each chunk starts with the previous value's end and ends with the next one's start
            chunks.append(f'ple.org"}}\n\ndata: {{"email":"user{index}@exam')
        else:
            # Each chunk ends in text that is already a valid email on its own
            chunks.append(f'm"}}\n\ndata: {{"email":"user{index}@example.co')
    if shape == "every chunk ends inside a value":
        chunks.append('ple.org"}\n\n')
    elif shape == "every chunk ends at a valid prefix of the value":
        chunks.append('m"}\n\n')
    chunks.append("data: [DONE]\n\n")
    return chunks


@pytest.mark.parametrize(
    "shape",
    [
        "value split in two",
        "boundary at the end of the value",
        "every chunk ends inside a value",
        "every chunk ends at a valid prefix of the value",
    ],
)
def test_sanitize_chunks_rescans_a_bounded_amount_of_text(shape: str) -> None:
    chunks = _event_stream(shape)
    joined = "".join(chunks)
    redactor = _CountingRedactor()

    cleaned = sanitize_chunks(chunks, pii_redactor=redactor)

    assert "".join(cleaned) == sanitize_string(joined)
    assert len(cleaned) == len(chunks)
    # Every chunk once, the joined text once, and rescans that only look back to the last
    # boundary confirmed to line up. Rescanning from the start would scan hundreds of times more.
    assert redactor.scanned <= 5 * len(joined)


def test_sanitize_chunks_hands_a_continued_value_to_the_previous_chunk() -> None:
    # The email runs one character into the second chunk, which also holds the next event
    chunks = ["data: a@b.co", 'm"}\n\ndata: x@y.org', '"}\n\n']
    assert sanitize_chunks(chunks) == [
        "data: [REDACTED_EMAIL]",
        '"}\n\ndata: [REDACTED_EMAIL]',
        '"}\n\n',
    ]


def test_sanitize_payload_keeps_records_when_keys_collide() -> None:
    payload = {
        "ops@acme.org": {"id": 1},
        "sales@acme.org": {"id": 2},
        "support@acme.org": 3,
        "status": "open",
    }
    assert sanitize_payload(payload) == {
        "[REDACTED_EMAIL]": {"id": 1},
        "[REDACTED_EMAIL]#2": {"id": 2},
        "[REDACTED_EMAIL]#3": 3,
        "status": "open",
    }


def test_sanitize_payload_suffix_never_takes_an_existing_key_name() -> None:
    literal_first = {"[REDACTED_EMAIL]#2": "literal", "ops@acme.org": 1, "sales@acme.org": 2}
    assert sanitize_payload(literal_first) == {
        "[REDACTED_EMAIL]#2": "literal",
        "[REDACTED_EMAIL]": 1,
        "[REDACTED_EMAIL]#3": 2,
    }

    literal_last = {"ops@acme.org": 1, "sales@acme.org": 2, "[REDACTED_EMAIL]#2": "literal"}
    assert sanitize_payload(literal_last) == {
        "[REDACTED_EMAIL]": 1,
        "[REDACTED_EMAIL]#3": 2,
        "[REDACTED_EMAIL]#2": "literal",
    }


def test_sanitize_body_keeps_nested_records_when_keys_collide() -> None:
    body = json.dumps({"users": {"ops@acme.org": {"id": 1}, "sales@acme.org": {"id": 2}}})
    cleaned = sanitize_body(body)
    assert "acme.org" not in cleaned
    assert json.loads(cleaned) == {
        "users": {"[REDACTED_EMAIL]": {"id": 1}, "[REDACTED_EMAIL]#2": {"id": 2}}
    }
