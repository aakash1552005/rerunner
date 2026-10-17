"""Cookbook: Deterministic testing of OpenAI Structured Outputs with Rerunner.

Demonstrates how to record and replay OpenAI `client.beta.chat.completions.parse()`
calls with Pydantic models for zero-cost, hermetic CI test suites.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import httpx
from pydantic import BaseModel

from rerunner import CassetteTransport


class CityInfo(BaseModel):
    """Structured response model for city extraction."""

    name: str
    country: str
    population: int
    famous_landmark: str


def fetch_city_details(transport: httpx.BaseTransport) -> CityInfo:
    """Fetch structured city details using OpenAI SDK with custom HTTP transport."""
    try:
        from openai import OpenAI
    except ImportError as err:
        raise RuntimeError("openai is required. Install via `pip install openai`") from err

    # Attach Rerunner CassetteTransport via httpx.Client to the OpenAI client
    http_client = httpx.Client(transport=transport)
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "sk-mock-key"), http_client=http_client)

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06",
        messages=[
            {"role": "system", "content": "Extract structured details about the requested city."},
            {"role": "user", "content": "Tell me about Tokyo, Japan."},
        ],
        response_format=CityInfo,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError("Failed to parse structured output")
    return message.parsed


if __name__ == "__main__":
    cassette_dir = Path("cassettes")
    cassette_dir.mkdir(parents=True, exist_ok=True)
    cassette_path = cassette_dir / "openai_structured.jsonl"

    class MockOpenAIServer(httpx.BaseTransport):
        """Simulate OpenAI Structured Outputs endpoint for local self-contained runs."""

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            mock_city = CityInfo(
                name="Tokyo",
                country="Japan",
                population=13960000,
                famous_landmark="Tokyo Tower",
            )
            response_json = {
                "id": "chatcmpl-test-structured",
                "object": "chat.completion",
                "created": 1729000000,
                "model": "gpt-4o-2024-08-06",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(mock_city.model_dump()),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 28, "completion_tokens": 32, "total_tokens": 60},
            }
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=json.dumps(response_json).encode("utf-8"),
                request=request,
            )

    print("==================================================================")
    print("PHASE 1: RECORDING OPENAI STRUCTURED OUTPUT CALL")
    print("==================================================================")
    # When an OPENAI_API_KEY is available, uses the real network; otherwise falls back to mock server
    real_transport = httpx.HTTPTransport() if os.getenv("OPENAI_API_KEY") else MockOpenAIServer()
    record_transport = CassetteTransport(cassette_path, mode="record", real_transport=real_transport)

    city_recorded = fetch_city_details(record_transport)
    print(f"Recorded Response: {city_recorded.name}, {city_recorded.country}")
    print(f"Population: {city_recorded.population:,} | Landmark: {city_recorded.famous_landmark}")
    print(f"Cassette saved to: {cassette_path} ({cassette_path.stat().st_size} bytes)")

    print("\n==================================================================")
    print("PHASE 2: DETERMINISTIC $0 REPLAY IN CI (OFFLINE)")
    print("==================================================================")
    # Pure replay: zero external network traffic, zero token consumption, deterministic latency
    replay_transport = CassetteTransport(cassette_path, mode="replay")
    city_replayed = fetch_city_details(replay_transport)

    print(f"Replayed Response: {city_replayed.name}, {city_replayed.country}")
    print(f"Population: {city_replayed.population:,} | Landmark: {city_replayed.famous_landmark}")
    assert city_replayed == city_recorded

    print("\n[SUCCESS] OpenAI Structured Outputs recorded and replayed with 100% fidelity!")
