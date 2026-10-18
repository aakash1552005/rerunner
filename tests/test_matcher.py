"""Unit tests for tolerant request matching and normalizers."""

from __future__ import annotations

from rerunner.matcher import (
    compute_request_key,
    normalize_body,
    normalize_headers,
)


def test_volatile_headers_stripped() -> None:
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-secret-12345",
        "X-Request-ID": "volatile-req-uuid-999",
        "Date": "Mon, 12 Oct 2026 12:00:00 GMT",
        "User-Agent": "anthropic-python/0.28.0",
        "X-Stainless-Arch": "x64",
    }
    normalized = normalize_headers(headers)
    assert "content-type" in normalized
    assert "authorization" not in normalized
    assert "x-request-id" not in normalized
    assert "date" not in normalized
    assert "user-agent" not in normalized
    assert "x-stainless-arch" not in normalized


def test_json_body_canonicalization() -> None:
    body1 = (
        '{"model": "claude-3-5-sonnet-20241022", "messages": [{"role": "user", "content": "hi"}]}'
    )
    body2 = '{\n  "messages": [\n    {"role": "user", "content": "hi"}\n  ],\n  "model": "claude-3-5-sonnet-20241022"\n}'

    assert normalize_body(body1) == normalize_body(body2)
    key1 = compute_request_key("POST", "https://api.anthropic.com/v1/messages", body1)
    key2 = compute_request_key("POST", "https://api.anthropic.com/v1/messages", body2)
    assert key1 == key2
