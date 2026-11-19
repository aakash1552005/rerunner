"""Unit tests for automated secret, API key, and PII redactor."""

from __future__ import annotations

import json
import re
import subprocess
import sys

import pytest
from dataclasses import dataclass
from pydantic import BaseModel

from rerunner.sanitizer import (
    SECRET_PATTERNS,
    SENSITIVE_HEADERS,
    SENSITIVE_QUERY_PARAMS,
    Pseudonymizer,
    SetherRedactor,
    _absorbed_head,
    _common_prefix_length,
    _common_suffix_length,
    _is_luhn_valid,
    _is_probable_ip,
    find_sensitive_leaks,
    get_env_redact_patterns,
    sanitize_body,
    sanitize_chunks,
    sanitize_data,
    sanitize_headers,
    sanitize_payload,
    sanitize_pii,
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


def test_sanitize_with_env_redact_patterns_json_list(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns = json.dumps(["corp_secret_[a-zA-Z0-9]+", "acme_key_[0-9]+"])
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", patterns)

    text = "Payload with corp_secret_Abc123Xyz and acme_key_987654 inside."
    cleaned = sanitize_string(text)
    assert "corp_secret_Abc123Xyz" not in cleaned
    assert "acme_key_987654" not in cleaned
    assert cleaned == "Payload with [REDACTED] and [REDACTED] inside."


def test_sanitize_data_alias_with_env_redact_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns = json.dumps(["corp_token_[a-zA-Z0-9]+"])
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", patterns)

    raw_payload = {
        "token": "corp_token_xyz999",
        "nested": {"key": "corp_token_abc111"},
        "count": 42,
    }
    cleaned = sanitize_data(raw_payload)
    assert cleaned["token"] == "[REDACTED]"
    assert cleaned["nested"]["key"] == "[REDACTED]"
    assert cleaned["count"] == 42


def test_env_redact_patterns_custom_replacements(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns = json.dumps(
        [
            ["internal_key_[0-9]+", "[REDACTED_INTERNAL]"],
            {"pattern": "tenant_[0-9]{4}", "replacement": "[REDACTED_TENANT]"},
        ]
    )
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", patterns)

    text = "Access internal_key_456 for tenant_7890"
    cleaned = sanitize_string(text)
    assert cleaned == "Access [REDACTED_INTERNAL] for [REDACTED_TENANT]"


def test_find_sensitive_leaks_with_env_redact_patterns(monkeypatch: pytest.MonkeyPatch) -> None:
    patterns = json.dumps(["secret_vault_[a-z0-9]+"])
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", patterns)

    leaks = find_sensitive_leaks({"auth": "secret_vault_topsecret123"})
    assert len(leaks) >= 1


def test_env_redact_patterns_resilient_to_invalid_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", "invalid json string")
    assert get_env_redact_patterns() == []
    assert sanitize_string("Hello world") == "Hello world"

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", '["valid_[0-9]+", "[invalid_regex("]')
    patterns = get_env_redact_patterns()
    assert len(patterns) == 1
    assert sanitize_string("valid_123") == "[REDACTED]"

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", '{"not_a": "list"}')
    assert get_env_redact_patterns() == []


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


def test_is_luhn_valid_cases() -> None:
    assert _is_luhn_valid("4000001234567891") is False
    assert _is_luhn_valid("4111111111111111") is True
    assert _is_luhn_valid("12345") is False
    assert _is_luhn_valid("4111-1111-1111-1111") is True
    assert _is_luhn_valid("4111-1111-1111-1112") is False


def test_is_probable_ip_cases() -> None:
    assert _is_probable_ip("1.2.3") is False
    assert _is_probable_ip("1.2.3.4.5") is False
    assert _is_probable_ip("a.b.c.d") is False
    assert _is_probable_ip("1.2.c.4") is False
    assert _is_probable_ip("256.0.0.1") is False
    assert _is_probable_ip("-1.0.0.1") is False
    assert _is_probable_ip("10.0.0.1") is True
    assert _is_probable_ip("127.0.0.1") is True
    assert _is_probable_ip("192.168.1.1") is True
    assert _is_probable_ip("172.16.0.1") is True
    assert _is_probable_ip("172.31.255.255") is True
    assert _is_probable_ip("8.8.8.10") is True
    assert _is_probable_ip("1.1.1.1") is False


def test_sanitize_payload_pydantic_and_dataclass() -> None:
    @dataclass
    class SampleDC:
        user_email: str
        count: int

    class SampleModel(BaseModel):
        token: str
        active: bool

    dc = SampleDC(user_email="alice@example.com", count=42)
    cleaned_dc = sanitize_payload(dc)
    assert cleaned_dc == {"user_email": "[REDACTED_EMAIL]", "count": 42}

    model = SampleModel(token="sk-ant-api03-abcdef1234567890abcdef1234567890", active=True)
    cleaned_model = sanitize_payload(model)
    assert cleaned_model == {"token": "[REDACTED_ANTHROPIC_KEY]", "active": True}


def test_sanitize_payload_version_keys_bypass_ip_redaction() -> None:
    data = {
        "version": "10.0.1.2",
        "semver": "127.0.0.1",
        "pyversion": "192.168.1.1",
        "sdk_version": "172.16.0.1",
        "server_ip": "10.0.1.2",
    }
    cleaned = sanitize_payload(data)
    assert cleaned["version"] == "10.0.1.2"
    assert cleaned["semver"] == "127.0.0.1"
    assert cleaned["pyversion"] == "192.168.1.1"
    assert cleaned["sdk_version"] == "172.16.0.1"
    assert cleaned["server_ip"] == "[REDACTED_IP_ADDRESS]"


def test_sanitize_body_fallback_on_invalid_json() -> None:
    invalid_json = "{bad-json: alice@example.com"
    cleaned = sanitize_body(invalid_json)
    assert "[REDACTED_EMAIL]" in cleaned
    assert "alice@example.com" not in cleaned
    assert sanitize_body(12345) == 12345


def test_sanitize_pii_fallback_and_empty() -> None:
    assert sanitize_pii("") == ""
    text = "Call me at 555-123-4567 or email bob@example.com"
    cleaned = sanitize_pii(text)
    assert "[REDACTED_EMAIL]" in cleaned
    assert "[REDACTED_PHONE]" in cleaned


def test_sanitize_pii_with_mocked_presidio(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    presidio_analyzer = types.ModuleType("presidio_analyzer")
    presidio_anonymizer = types.ModuleType("presidio_anonymizer")
    entities_mod = types.ModuleType("presidio_anonymizer.entities")

    class MockOperatorConfig:
        def __init__(self, mode: str, params: dict[str, str]) -> None:
            self.mode = mode
            self.params = params

    class MockAnonymized:
        def __init__(self, text: str) -> None:
            self.text = text

    class MockAnalyzerEngine:
        def analyze(self, text: str, entities: list[str], language: str) -> list[str]:
            return ["mock_match"]

    class MockAnonymizerEngine:
        def anonymize(
            self, text: str, analyzer_results: list[str], operators: dict[str, object]
        ) -> MockAnonymized:
            return MockAnonymized("anonymized " + text)

    presidio_analyzer.AnalyzerEngine = MockAnalyzerEngine
    presidio_anonymizer.AnonymizerEngine = MockAnonymizerEngine
    entities_mod.OperatorConfig = MockOperatorConfig

    monkeypatch.setitem(sys.modules, "presidio_analyzer", presidio_analyzer)
    monkeypatch.setitem(sys.modules, "presidio_anonymizer", presidio_anonymizer)
    monkeypatch.setitem(sys.modules, "presidio_anonymizer.entities", entities_mod)

    res = sanitize_pii("test input", entities=["EMAIL_ADDRESS"])
    assert "anonymized test input" in res


def test_sether_redactor_validation_and_redact(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    phonenumbers = types.ModuleType("phonenumbers")
    phonenumbers.SUPPORTED_REGIONS = ["US", "GB"]

    sether = types.ModuleType("sether")

    class MockMatch:
        def __init__(self, start: int, end: int) -> None:
            self.start = start
            self.end = end

    class MockDetector:
        def __init__(self, matches: list[tuple[int, int]]) -> None:
            self.matches = matches

        def detect(self, text: str) -> list[MockMatch]:
            return [MockMatch(s, e) for s, e in self.matches]

    sether.email_detector = MockDetector([(0, 17)])  # "alice@example.com"
    sether.phone_detector = MockDetector([(21, 33)])
    sether.credit_card_detector = MockDetector([])
    sether.ssn_detector = MockDetector([])
    sether.create_multi_region_phone_detector = lambda regions: sether.phone_detector

    monkeypatch.setitem(sys.modules, "phonenumbers", phonenumbers)
    monkeypatch.setitem(sys.modules, "sether", sether)

    with pytest.raises(ValueError, match="SetherRedactor entities must be a non-empty subset"):
        SetherRedactor(entities=["INVALID_ENTITY"])

    with pytest.raises(ValueError, match="Unknown phone regions"):
        SetherRedactor(phone_regions=["XX"])

    redactor = SetherRedactor(entities=["EMAIL_ADDRESS", "PHONE_NUMBER"], phone_regions=["US"])
    assert redactor.redact("") == ""

    text = "alice@example.com and +15551234567"
    redacted = redactor.redact(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted


def test_pseudonymizer_comprehensive(monkeypatch: pytest.MonkeyPatch) -> None:
    p_default = Pseudonymizer()
    p_bytes = Pseudonymizer(seed=b"custom-bytes-seed")
    monkeypatch.setenv("RERUNNER_PSEUDONYM_SEED", "env-seed")
    p_env = Pseudonymizer()
    assert p_default._key == b"rerunner-default-seed"
    assert p_bytes._key == b"custom-bytes-seed"
    assert p_env._key == b"env-seed"

    p = Pseudonymizer(seed="test-seed")

    email1 = p.pseudonymize_email("Alice@Domain.COM")
    email2 = p.pseudonymize_email("alice@domain.com")
    assert email1 == email2
    assert email1.startswith("user_")
    assert email1.endswith("@example.test")

    uuid_str = "550e8400-e29b-41d4-a716-446655440000"
    pseudo_uuid = p.pseudonymize_uuid(uuid_str)
    assert len(pseudo_uuid) == 36
    parts = pseudo_uuid.split("-")
    assert len(parts) == 5
    assert parts[2].startswith("4")
    assert parts[3].startswith("8")

    ssn = p.pseudonymize_ssn("123-45-6789")
    assert ssn.startswith("900-")
    assert len(ssn) == 11

    valid_cc = "4111-1111-1111-1111"
    pseudo_cc = p.pseudonymize_credit_card(valid_cc)
    assert pseudo_cc.startswith("400000")
    assert len(pseudo_cc) == 16
    assert _is_luhn_valid(pseudo_cc)

    assert p.pseudonymize_credit_card("1234") == "1234"
    assert p.pseudonymize_credit_card("4111111111111112") == "4111111111111112"

    text = f"Contact alice@acme.com with {uuid_str} and ssn 123-45-6789 and card {valid_cc}"
    pseudo_text = p.pseudonymize_string(text)
    assert "alice@acme.com" not in pseudo_text
    assert "user_" in pseudo_text
    assert uuid_str not in pseudo_text
    assert "900-" in pseudo_text
    assert "400000" in pseudo_text
    assert p.pseudonymize_string("") == ""

    payload = {
        "user": "bob@acme.com",
        "meta": [uuid_str, 123, True, None],
        "nested": {"ssn": "123-45-6789"},
    }
    masked = p.pseudonymize_payload(payload)
    assert masked["user"].startswith("user_")
    assert masked["meta"][0] != uuid_str
    assert masked["meta"][1] == 123
    assert masked["meta"][2] is True
    assert masked["meta"][3] is None
    assert masked["nested"]["ssn"].startswith("900-")
    assert p.pseudonymize_payload("direct_string").startswith("direct_string")


def test_common_prefix_suffix_and_absorbed_head() -> None:
    assert _common_prefix_length("abcde", "abcfg") == 3
    assert _common_prefix_length("abc", "xyz") == 0
    assert _common_prefix_length("", "abc") == 0
    assert _common_prefix_length("abc", "abc") == 3

    assert _common_suffix_length("xyzabc", "123abc") == 3
    assert _common_suffix_length("xyz", "abc") == 0
    assert _common_suffix_length("", "abc") == 0
    assert _common_suffix_length("abc", "abc") == 3

    assert _absorbed_head("hello", "hello", "hello world", 0, 10) == 0
    assert _absorbed_head("token_123", "token_123", "sub_token_123", 4, 10) == 0


def test_sanitize_data_alias_identity() -> None:
    data = {"secret": "sk-ant-api03-abcdef1234567890abcdef1234567890"}
    assert sanitize_data(data) == sanitize_payload(data)


def test_every_builtin_secret_pattern_matches_and_redacts() -> None:
    assert len(SECRET_PATTERNS) >= 9
    test_cases = [
        ("sk-ant-api03-" + "a" * 32, "[REDACTED_ANTHROPIC_KEY]"),
        ("sk-proj-" + "b" * 32, "[REDACTED_OPENAI_PROJECT_KEY]"),
        ("sk-" + "c" * 32, "[REDACTED_OPENAI_KEY]"),
        ("AIzaSy" + "d" * 33, "[REDACTED_GOOGLE_API_KEY]"),
        ("Bearer " + "e" * 20, "Bearer [REDACTED_TOKEN]"),
        ("ghp_" + "f" * 36, "[REDACTED_GITHUB_TOKEN]"),
        ("gho_" + "g" * 36, "[REDACTED_GITHUB_OAUTH_TOKEN]"),
        ("AKIA" + "1234567890ABCDEF", "[REDACTED_AWS_KEY_ID]"),
        ("xoxb-" + "1234567890123", "[REDACTED_SLACK_TOKEN]"),
        ("xoxp-" + "1234567890123", "[REDACTED_SLACK_TOKEN]"),
        ("test.user+tag@sub.domain.org", "[REDACTED_EMAIL]"),
        ("+1-800-555-0199", "[REDACTED_PHONE]"),
        ("(800) 555-0199", "[REDACTED_PHONE]"),
        ("800-555-0199", "[REDACTED_PHONE]"),
        ("123-45-6789", "[REDACTED_SSN]"),
    ]
    for sample, expected_replacement in test_cases:
        res = sanitize_string(f"prefix {sample} suffix")
        assert expected_replacement in res, f"Failed for sample: {sample}"


def test_every_sensitive_header_redacted() -> None:
    raw_headers = {h: f"secret-val-for-{h}" for h in SENSITIVE_HEADERS}
    raw_headers["content-type"] = "application/json"
    raw_headers["USER-AGENT"] = "rerunner-test/1.0"

    cleaned = sanitize_headers(raw_headers)
    for h in SENSITIVE_HEADERS:
        assert cleaned[h] == "[REDACTED]"
    assert cleaned["content-type"] == "application/json"
    assert cleaned["user-agent"] == "rerunner-test/1.0"


def test_every_sensitive_query_param_redacted() -> None:
    for param in SENSITIVE_QUERY_PARAMS:
        url = f"https://api.example.com/v1/search?safe=1&{param}=supersecret&other=val"
        cleaned = sanitize_url(url)
        assert f"{param}=%5BREDACTED%5D" in cleaned or f"{param}=[REDACTED]" in cleaned
        assert "supersecret" not in cleaned
        assert "safe=1" in cleaned


def test_sanitize_url_without_query_and_empty_and_path() -> None:
    assert sanitize_url("") == ""
    clean_no_query = sanitize_url("https://example.com/api/v1/users/4111-1111-1111-1111")
    assert "[REDACTED_CREDIT_CARD]" in clean_no_query
    assert "4111-1111-1111-1111" not in clean_no_query

    # Query with path and fragment
    full_url = "https://example.com/api/test.user@domain.com?token=tok123#myfragment"
    cleaned = sanitize_url(full_url)
    assert "[REDACTED_EMAIL]" in cleaned
    assert "token=%5BREDACTED%5D" in cleaned or "token=[REDACTED]" in cleaned
    assert "myfragment" in cleaned


def test_find_sensitive_leaks_comprehensive() -> None:
    # Clean data returns empty list
    clean_payload = {
        "user": "[REDACTED_EMAIL]",
        "headers": {"authorization": "[REDACTED]"},
    }
    assert find_sensitive_leaks(clean_payload) == []

    # Leaking sensitive header
    leaky_headers = {"authorization": "Bearer unredacted_secret"}
    leaks = find_sensitive_leaks(leaky_headers)
    assert any("Unredacted sensitive header 'authorization'" in leak for leak in leaks)

    # Leaking card in string
    leaks_card = find_sensitive_leaks("Found card 4111 1111 1111 1111 here")
    assert any("REDACTED_CREDIT_CARD" in leak for leak in leaks_card)

    # Leaking IP in nested list
    leaks_ip = find_sensitive_leaks([["host", "192.168.1.50"]])
    assert any("REDACTED_IP_ADDRESS" in leak for leak in leaks_ip)

    # Leaking AWS key in dict
    leaks_aws = find_sensitive_leaks({"aws": "AKIA1234567890ABCDEF"})
    assert any("REDACTED_AWS_KEY_ID" in leak for leak in leaks_aws)


def test_get_env_redact_patterns_formats(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Invalid JSON or empty
    monkeypatch.delenv("RERUNNER_REDACT_PATTERNS", raising=False)
    assert get_env_redact_patterns() == []

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", "not-a-json")
    assert get_env_redact_patterns() == []

    # 2. String items with invalid regex
    json_rules = json.dumps(
        [
            "simple_string",
            ["tuple_pat", "[TUPLE_REPL]"],
            {"pattern": "dict_pat", "replacement": "[DICT_REPL]"},
            "[invalid(regex",  # Should be skipped via re.error
            ["[another(invalid", "[REPL]"],
            {"pattern": "[third(invalid", "replacement": "[REPL]"},
        ]
    )
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", json_rules)
    patterns = get_env_redact_patterns()
    assert len(patterns) == 3
    assert patterns[0][0].pattern == "simple_string"
    assert patterns[0][1] == "[REDACTED]"
    assert patterns[1][0].pattern == "tuple_pat"
    assert patterns[1][1] == "[TUPLE_REPL]"
    assert patterns[2][0].pattern == "dict_pat"
    assert patterns[2][1] == "[DICT_REPL]"


def test_sanitize_string_card_and_ip_raw_and_semver() -> None:
    # Raw 16-digit valid card without delimiters
    raw_card = "4111111111111111"
    assert sanitize_string(f"my {raw_card} number") == "my [REDACTED_CREDIT_CARD] number"

    # Raw 16-digit invalid card
    invalid_raw = "4111111111111112"
    assert sanitize_string(f"ref {invalid_raw} code") == f"ref {invalid_raw} code"

    # Semver string that matches _IP_REGEX pattern but fails _is_probable_ip
    semver = "1.2.3.4"
    assert sanitize_string(f"version {semver}") == f"version {semver}"

    # Probable IP that matches and gets redacted
    ip_addr = "10.0.0.1"
    assert sanitize_string(f"host {ip_addr}") == "host [REDACTED_IP_ADDRESS]"


def test_sanitize_payload_exceptions_and_primitives() -> None:
    class FailingModel:
        def model_dump(self, mode: str = "python") -> dict[str, str]:
            raise RuntimeError("Dump failed")

    # Broken model_dump falls through without crashing
    broken = FailingModel()
    assert sanitize_payload(broken) is broken

    # Tuples, booleans, numbers, None
    assert sanitize_payload(("alice@domain.com", 123, True, None)) == (
        "[REDACTED_EMAIL]",
        123,
        True,
        None,
    )
    assert sanitize_payload([("bob@domain.com", 456)]) == [("[REDACTED_EMAIL]", 456)]


def test_sanitize_body_json_decode_error_fallback() -> None:
    # Starts with { and ends with }, but has invalid JSON content
    bad_json_wrapped = "{invalid json content: user@test.org}"
    cleaned = sanitize_body(bad_json_wrapped)
    assert "[REDACTED_EMAIL]" in cleaned
    assert "user@test.org" not in cleaned


def test_absorbed_head_detailed_branches() -> None:
    # Not matching within limit -> -1
    assert _absorbed_head("abc", "abc", "xyz", 0, 10) == -1

    # Absorbing leading chars
    # chunk="abc_val", clean="abc_val", target="val", start=0, limit=10 -> head=4
    assert _absorbed_head("abc_val", "abc_val", "val", 0, 10) == 4

    # Limit smaller than required head -> -1
    assert _absorbed_head("abc_val", "abc_val", "val", 0, 2) == -1


def test_sether_redactor_overlapping_and_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    phonenumbers = types.ModuleType("phonenumbers")
    phonenumbers.SUPPORTED_REGIONS = ["US"]

    sether = types.ModuleType("sether")

    class MockMatch:
        def __init__(self, start: int, end: int) -> None:
            self.start = start
            self.end = end

    class MockDetector:
        def __init__(self, matches: list[tuple[int, int]]) -> None:
            self.matches = matches

        def detect(self, text: str) -> list[MockMatch]:
            return [MockMatch(s, e) for s, e in self.matches]

    # Detector 1 detects 0..10, Detector 2 detects 5..15 (overlapping), Detector 3 detects 20..25
    sether.email_detector = MockDetector([(0, 10)])
    sether.phone_detector = MockDetector([(5, 15)])
    sether.credit_card_detector = MockDetector([(20, 25)])
    sether.ssn_detector = MockDetector([])
    sether.create_multi_region_phone_detector = lambda regions: sether.phone_detector

    monkeypatch.setitem(sys.modules, "phonenumbers", phonenumbers)
    monkeypatch.setitem(sys.modules, "sether", sether)

    redactor = SetherRedactor(
        entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"],
        phone_regions=["US"],
    )

    text = "0123456789abcdefghij0123456789"
    redacted = redactor.redact(text)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_CREDIT_CARD]" in redacted

    # When no detector matches anything
    empty_redactor = SetherRedactor(entities=["US_SSN"])
    assert empty_redactor.redact("plain text no ssn") == "plain text no ssn"


def test_pseudonymizer_additional_card_variations() -> None:
    p = Pseudonymizer(seed="variation-seed")
    # Various valid cards to ensure doubled digits > 9 branch (d -= 9) is exercised
    cards = [
        "4999-9999-9999-9999",
        "4888-8888-8888-8888",
        "4567-8901-2345-6789",
    ]
    for c in cards:
        if _is_luhn_valid(re.sub(r"\D", "", c)):
            res = p.pseudonymize_credit_card(c)
            assert res.startswith("400000")
            assert len(res) == 16
            assert _is_luhn_valid(res)


def test_pseudonymizer_different_seeds_produce_different_digests() -> None:
    p1 = Pseudonymizer(seed="seed-alpha")
    p2 = Pseudonymizer(seed="seed-beta")

    assert p1.pseudonymize_email("common@acme.org") != p2.pseudonymize_email("common@acme.org")
    assert p1.pseudonymize_uuid("550e8400-e29b-41d4-a716-446655440000") != p2.pseudonymize_uuid(
        "550e8400-e29b-41d4-a716-446655440000"
    )
    assert p1.pseudonymize_ssn("987-65-4321") != p2.pseudonymize_ssn("987-65-4321")
    assert p1.pseudonymize_credit_card("4111-1111-1111-1111") != p2.pseudonymize_credit_card(
        "4111-1111-1111-1111"
    )


def test_sanitize_headers_keys_always_lowercase_and_custom_patterns() -> None:
    headers = {
        "AUTHORIZATION": "Bearer secret123",
        "X-API-KEY": "key123",
        "CUSTOM-HEADER": "contains custom_secret_token",
    }
    custom = [(re.compile(r"custom_secret_token"), "[REDACTED_CUSTOM]")]
    cleaned = sanitize_headers(headers, custom_patterns=custom)

    assert set(cleaned.keys()) == {"authorization", "x-api-key", "custom-header"}
    assert cleaned["authorization"] == "[REDACTED]"
    assert cleaned["x-api-key"] == "[REDACTED]"
    assert cleaned["custom-header"] == "contains [REDACTED_CUSTOM]"


def test_sanitize_chunks_empty_single_and_multi_split() -> None:
    assert sanitize_chunks([]) == []
    assert sanitize_chunks(["plain text chunk"]) == ["plain text chunk"]

    # Split across 4 chunks
    quad_chunks = ["sk-ant-", "api03-", "1234567890abcdef", "1234567890abcdef"]
    cleaned = sanitize_chunks(quad_chunks)
    assert len(cleaned) == 4
    assert "".join(cleaned) == "[REDACTED_ANTHROPIC_KEY]"


def test_is_probable_ip_full_matrix() -> None:
    assert _is_probable_ip("0.0.0.0") is False
    assert _is_probable_ip("1.2.3.9") is False
    assert _is_probable_ip("1.2.3.10") is True
    assert _is_probable_ip("255.255.255.255") is True
    assert _is_probable_ip("192.169.1.1") is True
    assert _is_probable_ip("172.15.1.1") is True
    assert _is_probable_ip("172.16.1.1") is True
    assert _is_probable_ip("172.31.1.1") is True
    assert _is_probable_ip("172.32.1.1") is True


def test_regex_exact_boundary_lengths() -> None:
    # Anthropic {32,}
    assert sanitize_string("sk-ant-" + "a" * 31) == "sk-ant-" + "a" * 31
    assert sanitize_string("sk-ant-" + "a" * 32) == "[REDACTED_ANTHROPIC_KEY]"

    # OpenAI Project {32,}
    assert sanitize_string("sk-proj-" + "b" * 31) == "sk-proj-" + "b" * 31
    assert sanitize_string("sk-proj-" + "b" * 32) == "[REDACTED_OPENAI_PROJECT_KEY]"

    # OpenAI Standard {32,}
    assert sanitize_string("sk-" + "c" * 31) == "sk-" + "c" * 31
    assert sanitize_string("sk-" + "c" * 32) == "[REDACTED_OPENAI_KEY]"

    # Google {35}
    assert sanitize_string("AIza" + "d" * 34) == "AIza" + "d" * 34
    assert sanitize_string("AIza" + "d" * 35) == "[REDACTED_GOOGLE_API_KEY]"

    # Bearer {16,}
    assert sanitize_string("Bearer " + "e" * 15) == "Bearer " + "e" * 15
    assert sanitize_string("Bearer " + "e" * 16) == "Bearer [REDACTED_TOKEN]"

    # GitHub Token {36,}
    assert sanitize_string("ghp_" + "f" * 35) == "ghp_" + "f" * 35
    assert sanitize_string("ghp_" + "f" * 36) == "[REDACTED_GITHUB_TOKEN]"

    # GitHub OAuth {36,}
    assert sanitize_string("gho_" + "g" * 35) == "gho_" + "g" * 35
    assert sanitize_string("gho_" + "g" * 36) == "[REDACTED_GITHUB_OAUTH_TOKEN]"

    # AWS Key {16}
    assert sanitize_string("AKIA" + "A" * 15) == "AKIA" + "A" * 15
    assert sanitize_string("AKIA" + "A" * 16) == "[REDACTED_AWS_KEY_ID]"

    # Slack Token {10,48}
    assert sanitize_string("xoxb-" + "a" * 9) == "xoxb-" + "a" * 9
    assert sanitize_string("xoxb-" + "a" * 10) == "[REDACTED_SLACK_TOKEN]"
    assert sanitize_string("xoxb-" + "a" * 48) == "[REDACTED_SLACK_TOKEN]"


def test_pseudonymizer_exact_values() -> None:
    p = Pseudonymizer(seed="test-seed")
    assert p.pseudonymize_email("alice@example.com") == "user_09ee5b696e@example.test"
    assert p.pseudonymize_email("ALICE@EXAMPLE.COM") == "user_09ee5b696e@example.test"
    assert (
        p.pseudonymize_uuid("550e8400-e29b-41d4-a716-446655440000")
        == "47e87e1b-a9c5-4f51-81fc-470d8b3010af"
    )
    assert (
        p.pseudonymize_uuid("550E8400-E29B-41D4-A716-446655440000")
        == "47e87e1b-a9c5-4f51-81fc-470d8b3010af"
    )
    assert p.pseudonymize_ssn("123-45-6789") == "900-19-1020"
    assert p.pseudonymize_credit_card("4111-1111-1111-1111") == "4000003543043000"


def test_common_prefix_and_suffix_exact() -> None:
    assert _common_prefix_length("", "abc") == 0
    assert _common_prefix_length("abc", "") == 0
    assert _common_prefix_length("abc", "abc") == 3
    assert _common_prefix_length("abcdef", "abcxyz") == 3
    assert _common_prefix_length("xbc", "abc") == 0

    assert _common_suffix_length("", "abc") == 0
    assert _common_suffix_length("abc", "") == 0
    assert _common_suffix_length("abc", "abc") == 3
    assert _common_suffix_length("defabc", "xyzabc") == 3
    assert _common_suffix_length("abx", "abc") == 0


def test_absorbed_head_exact() -> None:
    assert _absorbed_head("hello", "hello", "hello world", 0, 10) == 0
    assert _absorbed_head("ab_suffix", "ab_suffix", "suffix and more", 0, 10) == 3
    assert _absorbed_head("abcdef", "uvwxyz", "no match", 0, 5) == -1
    assert _absorbed_head("abc", "abc", "xyz", 0, 0) == -1


def test_sanitize_chunks_comprehensive() -> None:
    # Identical chunks when joined equals cleaned
    assert sanitize_chunks(["hello ", "world"]) == ["hello ", "world"]

    # Split OpenAI project key across two chunks
    res1 = sanitize_chunks(["sk-proj-", "12345678901234567890123456789012"])
    assert res1 == ["", "[REDACTED_OPENAI_PROJECT_KEY]"]

    # Split OpenAI standard key across 3 chunks
    res2 = sanitize_chunks(["prefix ", "sk-", "12345678901234567890123456789012", " suffix"])
    assert res2 == ["prefix ", "", "[REDACTED_OPENAI_KEY]", " suffix"]

    # Split Bearer token across chunks
    res3 = sanitize_chunks(["Bearer ", "x" * 16, " tail"])
    assert res3 == ["Bearer ", "[REDACTED_TOKEN]", " tail"]

    # Split Anthropic key
    res4 = sanitize_chunks(["start: ", "sk-ant-", "a" * 32, " end"])
    assert res4 == ["start: ", "", "[REDACTED_ANTHROPIC_KEY]", " end"]


def test_pseudonymizer_string_and_payload_exact() -> None:
    p = Pseudonymizer(seed="test-seed")
    assert p.pseudonymize_string("") == ""
    assert p.pseudonymize_payload(123) == 123
    assert p.pseudonymize_payload(None) is None

    assert p.pseudonymize_credit_card("1234") == "1234"
    assert p.pseudonymize_credit_card("4111111111111112") == "4111111111111112"

    text = "Call 123-45-6789 or email test@example.com with id 550e8400-e29b-41d4-a716-446655440000"
    pseudo_text = p.pseudonymize_string(text)
    assert "123-45-6789" not in pseudo_text
    assert "test@example.com" not in pseudo_text
    assert "550e8400-e29b-41d4-a716-446655440000" not in pseudo_text
    assert "900-" in pseudo_text
    assert "@example.test" in pseudo_text

    payload = {
        "user": "test@example.com",
        "nested": [1, "123-45-6789"],
        "count": 42,
    }
    cleaned = p.pseudonymize_payload(payload)
    assert cleaned["count"] == 42
    assert "@example.test" in cleaned["user"]
    assert cleaned["nested"][0] == 1
    assert "900-" in cleaned["nested"][1]


def test_find_sensitive_leaks_direct_assertions() -> None:
    assert find_sensitive_leaks({"status": "ok", "count": 1}) == []

    leaks1 = find_sensitive_leaks({"headers": {"Authorization": "Bearer secret123456789012"}})
    assert any("Authorization" in leak for leak in leaks1)

    assert find_sensitive_leaks({"headers": {"Authorization": "[REDACTED]"}}) == []

    leaks2 = find_sensitive_leaks({"data": "Card 4111-1111-1111-1111 at 192.168.1.1"})
    assert any("REDACTED_CREDIT_CARD" in leak for leak in leaks2)
    assert any("REDACTED_IP_ADDRESS" in leak for leak in leaks2)

    assert find_sensitive_leaks({"data": "[REDACTED_CREDIT_CARD] at [REDACTED_IP_ADDRESS]"}) == []


def test_sanitize_url_exact() -> None:
    assert sanitize_url("") == ""
    assert sanitize_url("https://example.com/api/v1/users") == "https://example.com/api/v1/users"
    url = "https://example.com/search?q=test&token=secret123456789012&api_key=AIzaSyA_abcdef1234567890abcdef1234567"
    sanitized = sanitize_url(url)
    assert "token=%5BREDACTED%5D" in sanitized or "token=[REDACTED]" in sanitized
    assert "api_key=%5BREDACTED%5D" in sanitized or "api_key=[REDACTED]" in sanitized
    assert "q=test" in sanitized


def test_all_sensitive_headers_individual_exact() -> None:
    assert sanitize_headers({"authorization": "s"}) == {"authorization": "[REDACTED]"}
    assert sanitize_headers({"x-api-key": "s"}) == {"x-api-key": "[REDACTED]"}
    assert sanitize_headers({"api-key": "s"}) == {"api-key": "[REDACTED]"}
    assert sanitize_headers({"proxy-authorization": "s"}) == {"proxy-authorization": "[REDACTED]"}
    assert sanitize_headers({"cookie": "s"}) == {"cookie": "[REDACTED]"}
    assert sanitize_headers({"set-cookie": "s"}) == {"set-cookie": "[REDACTED]"}
    assert sanitize_headers({"x-auth-token": "s"}) == {"x-auth-token": "[REDACTED]"}

    assert sanitize_headers({"AUTHORIZATION": "s"}) == {"authorization": "[REDACTED]"}
    assert sanitize_headers({"X-API-KEY": "s"}) == {"x-api-key": "[REDACTED]"}
    assert sanitize_headers({"API-KEY": "s"}) == {"api-key": "[REDACTED]"}
    assert sanitize_headers({"PROXY-AUTHORIZATION": "s"}) == {"proxy-authorization": "[REDACTED]"}
    assert sanitize_headers({"COOKIE": "s"}) == {"cookie": "[REDACTED]"}
    assert sanitize_headers({"SET-COOKIE": "s"}) == {"set-cookie": "[REDACTED]"}
    assert sanitize_headers({"X-AUTH-TOKEN": "s"}) == {"x-auth-token": "[REDACTED]"}


def test_all_sensitive_query_params_individual_exact() -> None:
    assert sanitize_url("https://example.com/?key=val") == "https://example.com/?key=%5BREDACTED%5D"
    assert (
        sanitize_url("https://example.com/?api_key=val")
        == "https://example.com/?api_key=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?apikey=val")
        == "https://example.com/?apikey=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?token=val")
        == "https://example.com/?token=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?access_token=val")
        == "https://example.com/?access_token=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?client_secret=val")
        == "https://example.com/?client_secret=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?auth=val") == "https://example.com/?auth=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?secret=val")
        == "https://example.com/?secret=%5BREDACTED%5D"
    )
    assert (
        sanitize_url("https://example.com/?password=val")
        == "https://example.com/?password=%5BREDACTED%5D"
    )
    assert sanitize_url("https://example.com/?sig=val") == "https://example.com/?sig=%5BREDACTED%5D"
    assert (
        sanitize_url("https://example.com/?signature=val")
        == "https://example.com/?signature=%5BREDACTED%5D"
    )


def test_all_phone_number_formats_exact() -> None:
    assert sanitize_string("+1-555-123-4567") == "+[REDACTED_PHONE]"
    assert sanitize_string("1-555-123-4567") == "[REDACTED_PHONE]"
    assert sanitize_string("1.555.123.4567") == "[REDACTED_PHONE]"
    assert sanitize_string("(555) 123-4567") == "([REDACTED_PHONE]"
    assert sanitize_string("555-123-4567") == "[REDACTED_PHONE]"
    assert sanitize_string("555.123.4567") == "[REDACTED_PHONE]"
    assert sanitize_string("555 123 4567") == "[REDACTED_PHONE]"


def test_key_collision_and_reserved_exact() -> None:
    data = {
        "alice@example.com": 1,
        "bob@example.com": 2,
        "[REDACTED_EMAIL]#2": 3,
        "charlie@example.com": 4,
    }
    res = sanitize_payload(data)
    assert res == {
        "[REDACTED_EMAIL]": 1,
        "[REDACTED_EMAIL]#3": 2,
        "[REDACTED_EMAIL]#2": 3,
        "[REDACTED_EMAIL]#4": 4,
    }


def test_version_key_bypass_exact() -> None:
    assert sanitize_payload({"version": "10.0.0.1"}) == {"version": "10.0.0.1"}
    assert sanitize_payload({"semver": "10.0.0.1"}) == {"semver": "10.0.0.1"}
    assert sanitize_payload({"pyversion": "10.0.0.1"}) == {"pyversion": "10.0.0.1"}
    assert sanitize_payload({"sdk_version": "10.0.0.1"}) == {"sdk_version": "10.0.0.1"}
    assert sanitize_payload({"other": "10.0.0.1"}) == {"other": "[REDACTED_IP_ADDRESS]"}


def test_get_env_redact_patterns_exact_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RERUNNER_REDACT_PATTERNS", raising=False)
    assert get_env_redact_patterns() == []

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", "   ")
    assert get_env_redact_patterns() == []

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", "not-json")
    assert get_env_redact_patterns() == []

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", '{"not": "a list"}')
    assert get_env_redact_patterns() == []

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", '["valid_pat", "invalid[re"]')
    pats1 = get_env_redact_patterns()
    assert len(pats1) == 1
    assert pats1[0][0].pattern == "valid_pat"
    assert pats1[0][1] == "[REDACTED]"

    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", '[["tuple_pat", "custom_repl"], ["bad_len"]]')
    pats2 = get_env_redact_patterns()
    assert len(pats2) == 1
    assert pats2[0][0].pattern == "tuple_pat"
    assert pats2[0][1] == "custom_repl"

    monkeypatch.setenv(
        "RERUNNER_REDACT_PATTERNS",
        '[{"pattern": "dict_pat", "replacement": "custom_repl2"}, {"pattern": "default_repl"}]',
    )
    pats3 = get_env_redact_patterns()
    assert len(pats3) == 2
    assert pats3[0][1] == "custom_repl2"
    assert pats3[1][1] == "[REDACTED]"
