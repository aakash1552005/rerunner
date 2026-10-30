"""Unit tests for semantic drift tolerant replay matching via embeddings and cosine similarity (RFC #35)."""

from __future__ import annotations

import json
from pathlib import Path
import httpx

from rerunner.cassette import Cassette
from rerunner.matcher import (
    compute_semantic_similarity,
    compute_text_cosine_similarity,
    extract_prompt_text,
    request_matches,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.transport import CassetteTransport


def test_text_cosine_similarity_accuracy() -> None:
    # Identical
    assert compute_text_cosine_similarity("Hello world", "Hello world") == 1.0
    assert compute_text_cosine_similarity("", "") == 1.0
    assert compute_text_cosine_similarity("Hello", "") == 0.0

    # Minor phrasing update (semantic similarity should be high)
    p1 = "Analyze the quarterly financial earnings report for Q3."
    p2 = "Please analyze the quarterly financial earnings report for the third quarter (Q3)."
    sim_close = compute_text_cosine_similarity(p1, p2)
    assert sim_close > 0.80

    # Completely different task
    p3 = "Generate a Fibonacci sequence in Rust."
    sim_far = compute_text_cosine_similarity(p1, p3)
    assert sim_far < 0.15


def test_extract_prompt_text_multiprovider() -> None:
    # OpenAI messages
    openai_payload = json.dumps(
        {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain quantum computing."},
            ],
        }
    )
    extracted_openai = extract_prompt_text(openai_payload)
    assert "You are a helpful assistant." in extracted_openai
    assert "Explain quantum computing." in extracted_openai

    # Anthropic content blocks
    anthropic_payload = json.dumps(
        {
            "model": "claude-3-7-sonnet",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Draft a follow up email."}],
                }
            ],
        }
    )
    extracted_anthropic = extract_prompt_text(anthropic_payload)
    assert "Draft a follow up email." in extracted_anthropic

    # Google GenAI contents
    gemini_payload = json.dumps(
        {"contents": [{"role": "user", "parts": [{"text": "Summarize this paragraph."}]}]}
    )
    extracted_gemini = extract_prompt_text(gemini_payload)
    assert "Summarize this paragraph." in extracted_gemini

    # Raw string
    assert extract_prompt_text("Direct prompt string") == "Direct prompt string"


def test_request_matches_semantic_drift() -> None:
    recorded_req = RecordedRequest(
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
        body=json.dumps({"messages": [{"role": "user", "content": "Extract customer sentiment"}]}),
        request_key="fake-key-1",
    )

    # Tweaked incoming request with minor phrasing addition
    incoming_tweaked = json.dumps(
        {"messages": [{"role": "user", "content": "Please extract customer sentiment"}]}
    )

    # Under strict matching, keys differ
    assert not request_matches(
        recorded_req,
        "POST",
        "https://api.openai.com/v1/chat/completions",
        incoming_tweaked,
        strategy="strict",
    )

    # Under semantic matching, similarity matches
    assert request_matches(
        recorded_req,
        "POST",
        "https://api.openai.com/v1/chat/completions",
        incoming_tweaked,
        strategy="semantic",
        semantic_threshold=0.80,
    )

    # Completely different task is rejected
    incoming_divergent = json.dumps(
        {"messages": [{"role": "user", "content": "Solve LeetCode two sum"}]}
    )
    assert not request_matches(
        recorded_req,
        "POST",
        "https://api.openai.com/v1/chat/completions",
        incoming_divergent,
        strategy="semantic",
        semantic_threshold=0.80,
    )

    # Different method or URL is rejected
    assert not request_matches(
        recorded_req,
        "GET",
        "https://api.openai.com/v1/chat/completions",
        incoming_tweaked,
        strategy="semantic",
    )
    assert not request_matches(
        recorded_req,
        "POST",
        "https://api.openai.com/v1/embeddings",
        incoming_tweaked,
        strategy="semantic",
    )


def test_custom_embedding_fn() -> None:
    # Custom mock embedding function
    def mock_embed(text: str) -> list[float]:
        return [1.0, 0.0] if "sentiment" in text else [0.0, 1.0]

    b1 = json.dumps({"messages": [{"role": "user", "content": "Analyze sentiment"}]})
    b2 = json.dumps({"messages": [{"role": "user", "content": "Check sentiment score"}]})
    b3 = json.dumps({"messages": [{"role": "user", "content": "Write Python code"}]})

    assert compute_semantic_similarity(b1, b2, embedding_fn=mock_embed) == 1.0
    assert compute_semantic_similarity(b1, b3, embedding_fn=mock_embed) == 0.0


def test_e2e_semantic_replay_transport(temp_cassette_path: Path) -> None:
    # 1. Record original interaction
    cassette = Cassette(temp_cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.anthropic.com/v1/messages",
                body=json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Generate unit tests for auth module"}
                        ]
                    }
                ),
                request_key="anthropic_key_001",
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {"content": [{"type": "text", "text": "def test_login_success(): pass"}]}
                ),
            ),
        )
    )
    cassette.save()

    # 2. Replay with a tweaked prompt under matching_strategy="semantic"
    transport = CassetteTransport(
        cassette_path=temp_cassette_path,
        mode="replay",
        matching_strategy="semantic",
        semantic_threshold=0.80,
    )

    tweaked_body = json.dumps(
        {
            "messages": [
                {"role": "user", "content": "Please generate unit tests for the auth module."}
            ]
        }
    )

    req = httpx.Request(
        "POST",
        "https://api.anthropic.com/v1/messages",
        headers={"content-type": "application/json"},
        content=tweaked_body.encode("utf-8"),
    )

    resp = transport.handle_request(req)
    assert resp.status_code == 200
    data = resp.json()
    assert "def test_login_success(): pass" in data["content"][0]["text"]
