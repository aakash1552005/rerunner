"""Tolerant request matcher and normalizer for AI agent HTTP interactions."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from rerunner.sanitizer import SENSITIVE_QUERY_PARAMS

if TYPE_CHECKING:
    from rerunner.models import RecordedRequest

MatchingStrategy = Literal["strict", "content", "fuzzy", "semantic"]

# Headers that frequently vary across environments or runs without changing semantic meaning
VOLATILE_HEADER_PREFIXES = (
    "x-stainless-",  # Anthropic & OpenAI SDK metadata
    "x-amzn-",
    "x-goog-",
)

VOLATILE_HEADER_NAMES = {
    "date",
    "x-request-id",
    "request-id",
    "traceparent",
    "tracestate",
    "user-agent",
    "content-length",
    "content-encoding",
    "authorization",
    "api-key",
    "x-api-key",
    "idempotency-key",
    "x-idempotency-key",
    "host",
    "connection",
    "keep-alive",
}


def normalize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Strip non-deterministic and credential headers, normalizing keys to lowercase."""
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        k_lower = key.lower().strip()
        if k_lower in VOLATILE_HEADER_NAMES:
            continue
        if any(k_lower.startswith(prefix) for prefix in VOLATILE_HEADER_PREFIXES):
            continue
        normalized[k_lower] = value.strip()
    return normalized


def normalize_body(body: bytes | str | None) -> str:
    """Normalize body by canonicalizing JSON if applicable, or trimming whitespace."""
    if body is None:
        return ""
    if isinstance(body, bytes):
        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            return body.hex()
    else:
        body_str = body

    body_str = body_str.strip()
    if not body_str:
        return ""

    try:
        parsed = json.loads(body_str)
        # Canonical JSON: sorted keys, compact separators
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except Exception:
        return body_str


def normalize_body_content(body: bytes | str | None) -> str:
    """Normalize body focusing on primary message/prompt content, order-independent for LLM calls."""
    canonical = normalize_body(body)
    if not canonical:
        return ""
    try:
        parsed = json.loads(canonical)
        if isinstance(parsed, dict):
            # Extract content-bearing fields if present
            content_dict: dict[str, object] = {}
            for key in ("messages", "prompt", "input", "contents", "system"):
                if key in parsed:
                    content_dict[key] = parsed[key]
            if content_dict:
                return json.dumps(
                    content_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=True
                )
        return canonical
    except Exception:
        return canonical


def normalize_body_fuzzy(body: bytes | str | None) -> str:
    """Normalize body by stripping minor whitespace and dynamic timestamps."""
    canonical = normalize_body(body)
    if not canonical:
        return ""
    # Strip ISO timestamp patterns
    cleaned = re.sub(
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b",
        "<TIMESTAMP>",
        canonical,
    )
    # Collapse multiple whitespace
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_url(url: str) -> str:
    """Normalize URL by sorting query parameters and redacting sensitive parameters."""
    parsed = urlparse(url)
    if not parsed.query:
        return url
    raw_params = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_params: list[tuple[str, str]] = []
    for k, v in raw_params:
        k_lower = k.lower().strip()
        if k_lower in SENSITIVE_QUERY_PARAMS:
            normalized_params.append((k_lower, "[REDACTED]"))
        else:
            normalized_params.append((k, v))
    normalized_params.sort()
    normalized_query = urlencode(normalized_params)
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            normalized_query,
            parsed.fragment,
        )
    )


def extract_prompt_text(body: bytes | str | None) -> str:
    """Extract primary text content from an LLM request payload across OpenAI, Anthropic, and Gemini."""
    if not body:
        return ""
    if isinstance(body, bytes):
        try:
            body_str = body.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    else:
        body_str = body

    trimmed = body_str.strip()
    if not trimmed:
        return ""

    try:
        data = json.loads(trimmed)
    except (json.JSONDecodeError, TypeError, ValueError):
        return trimmed

    if not isinstance(data, dict):
        return trimmed

    texts: list[str] = []

    # OpenAI / Anthropic messages list
    messages = data.get("messages")
    if isinstance(messages, list):
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and isinstance(part.get("text"), str):
                            texts.append(part["text"])

    # Google GenAI contents list
    contents = data.get("contents")
    if isinstance(contents, list):
        for c in contents:
            if isinstance(c, dict) and isinstance(c.get("parts"), list):
                for part in c["parts"]:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        texts.append(part["text"])

    # Generic prompt/input/system fields
    for key in ("prompt", "input", "system"):
        val = data.get(key)
        if isinstance(val, str):
            texts.append(val)

    return " ".join(texts) if texts else trimmed


def compute_text_cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute token and character trigram cosine similarity between two text strings."""
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    if text_a == text_b:
        return 1.0

    def get_features(text: str) -> Counter[str]:
        words = re.findall(r"\b\w+\b", text.lower())
        char_trigrams = [text[i : i + 3].lower() for i in range(len(text) - 2)]
        return Counter(words + char_trigrams)

    vec_a = get_features(text_a)
    vec_b = get_features(text_b)

    intersection = set(vec_a.keys()) & set(vec_b.keys())
    dot_product = sum(vec_a[x] * vec_b[x] for x in intersection)

    norm_a = math.sqrt(sum(v**2 for v in vec_a.values()))
    norm_b = math.sqrt(sum(v**2 for v in vec_b.values()))

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


def compute_semantic_similarity(
    body_a: bytes | str | None,
    body_b: bytes | str | None,
    embedding_fn: Callable[[str], list[float]] | None = None,
) -> float:
    """Compute semantic similarity between two request payloads, optionally using an embedding function."""
    prompt_a = extract_prompt_text(body_a)
    prompt_b = extract_prompt_text(body_b)

    if embedding_fn is not None:
        vec_a = embedding_fn(prompt_a)
        vec_b = embedding_fn(prompt_b)
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=False))
        norm_a = math.sqrt(sum(a**2 for a in vec_a))
        norm_b = math.sqrt(sum(b**2 for b in vec_b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return float(dot_product / (norm_a * norm_b))

    return compute_text_cosine_similarity(prompt_a, prompt_b)


def compute_request_key(
    method: str,
    url: str,
    body: bytes | str | None = None,
    strategy: MatchingStrategy = "strict",
) -> str:
    """Compute deterministic SHA-256 hash identifying an HTTP request under a given matching strategy."""
    norm_url = normalize_url(url)
    if strategy == "content":
        norm_body = normalize_body_content(body)
    elif strategy == "fuzzy":
        norm_body = normalize_body_fuzzy(body)
    else:
        norm_body = normalize_body(body)

    payload = f"{method.upper()}|{norm_url}|{norm_body}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def request_matches(
    recorded: RecordedRequest,
    incoming_method: str,
    incoming_url: str,
    incoming_body: bytes | str | None = None,
    strategy: MatchingStrategy = "strict",
    semantic_threshold: float = 0.80,
    embedding_fn: Callable[[str], list[float]] | None = None,
) -> bool:
    """Determine whether an incoming request matches a recorded request under the given strategy."""
    incoming_key = compute_request_key(
        incoming_method, incoming_url, incoming_body, strategy=strategy
    )
    if recorded.request_key == incoming_key:
        return True
    if strategy in ("content", "fuzzy"):
        recorded_key = compute_request_key(
            recorded.method, recorded.url, recorded.body, strategy=strategy
        )
        return recorded_key == incoming_key
    if strategy == "semantic":
        # Semantic matching: same method and normalized URL, plus prompt similarity >= threshold
        if recorded.method.upper() != incoming_method.upper():
            return False
        if normalize_url(recorded.url) != normalize_url(incoming_url):
            return False
        sim = compute_semantic_similarity(recorded.body, incoming_body, embedding_fn=embedding_fn)
        return sim >= semantic_threshold
    return False
