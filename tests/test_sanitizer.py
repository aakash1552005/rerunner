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
