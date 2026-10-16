"""Automated secret, API key, and PII redactor for safe cassette persistence.

Includes comprehensive scanning for OpenAI, Anthropic, Google, AWS, GitHub, Slack tokens,
plus standard PII sanitization (Emails, Credit Cards, IPv4 addresses, and US Phone numbers).
"""

from __future__ import annotations

import re
from typing import Any

# Regular expressions detecting common API keys and sensitive tokens
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Model Provider Keys
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{32,}", re.IGNORECASE), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-proj-[a-zA-Z0-9_\-]{32,}", re.IGNORECASE), "[REDACTED_OPENAI_PROJECT_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{32,}", re.IGNORECASE), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}", re.IGNORECASE), "[REDACTED_GOOGLE_API_KEY]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9_\-\.]{16,}", re.IGNORECASE), "Bearer [REDACTED_TOKEN]"),
    # Cloud & Git Tokens
    (re.compile(r"ghp_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{36,}", re.IGNORECASE), "[REDACTED_GITHUB_OAUTH_TOKEN]"),
    (re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE), "[REDACTED_AWS_KEY_ID]"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}", re.IGNORECASE), "[REDACTED_SLACK_TOKEN]"),
    # PII Scrubbers
    (
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"),
        "[REDACTED_EMAIL]",
    ),
    (
        re.compile(r"\b(?:\+?1[-. ]?)?\(?([0-9]{3})\)?[-. ]?([0-9]{3})[-. ]?([0-9]{4})\b"),
        "[REDACTED_PHONE]",
    ),
    (
        re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b"),
        "[REDACTED_CREDIT_CARD]",
    ),
    (
        re.compile(r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"),
        "[REDACTED_IP_ADDRESS]",
    ),
]

# Sensitive header keys that should always have their values scrubbed
SENSITIVE_HEADERS: set[str] = {
    "authorization",
    "x-api-key",
    "api-key",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-auth-token",
}


def sanitize_string(
    text: str,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
) -> str:
    """Scan and scrub sensitive API tokens and PII from arbitrary strings."""
    if not text:
        return text
    sanitized = text

    # Apply default secret & PII patterns
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    # Apply custom user patterns if supplied
    if custom_patterns:
        for pattern, replacement in custom_patterns:
            sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def sanitize_headers(
    headers: dict[str, str],
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
) -> dict[str, str]:
    """Scrub sensitive HTTP headers before writing to cassette."""
    sanitized: dict[str, str] = {}
    for key, value in headers.items():
        k_lower = key.lower().strip()
        if k_lower in SENSITIVE_HEADERS:
            sanitized[k_lower] = "[REDACTED]"
        else:
            sanitized[k_lower] = sanitize_string(value, custom_patterns=custom_patterns)
    return sanitized


def sanitize_payload(
    data: Any,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
) -> Any:
    """Recursively sanitize dicts, lists, and strings for safe storage."""
    if isinstance(data, str):
        return sanitize_string(data, custom_patterns=custom_patterns)
    if isinstance(data, dict):
        return {k: sanitize_payload(v, custom_patterns=custom_patterns) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_payload(item, custom_patterns=custom_patterns) for item in data]
    return data


def find_sensitive_leaks(
    data: Any,
    custom_patterns: list[tuple[re.Pattern[str], str]] | None = None,
) -> list[str]:
    """Scan arbitrary payloads and return descriptions of any unredacted secrets or PII."""
    leaks: list[str] = []
    text_to_scan: list[str] = []

    def _collect_strings(val: Any) -> None:
        if isinstance(val, str):
            text_to_scan.append(val)
        elif isinstance(val, dict):
            for k, v in val.items():
                k_clean = str(k).lower().strip()
                if k_clean in SENSITIVE_HEADERS:
                    val_str = str(v)
                    if val_str and not val_str.startswith("[REDACTED"):
                        leaks.append(f"Unredacted sensitive header '{k}'")
                _collect_strings(v)
        elif isinstance(val, (list, tuple)):
            for item in val:
                _collect_strings(item)

    _collect_strings(data)
    patterns = SECRET_PATTERNS + (custom_patterns or [])

    for text in text_to_scan:
        for pat, replacement in patterns:
            match = pat.search(text)
            if match:
                matched_val = match.group(0)
                # Ensure the matched text isn't already a [REDACTED...] tag
                if not matched_val.startswith("[REDACTED"):
                    leaks.append(f"Found unredacted pattern matching {replacement.strip('[]')}")

    return list(dict.fromkeys(leaks))

