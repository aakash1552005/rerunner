"""Contributor Integration Test Template.

Copy and adapt this file when contributing a new model or framework adapter
(e.g., Ollama, Groq, Mistral, DeepSeek, LiteLLM) to Rerunner.

Steps to add a new provider:
1. Create `src/rerunner/integrations/<provider_name>.py`.
2. Define your adapter implementing `BaseProviderAdapter` or register via `@register_adapter`.
3. Copy this test file to `tests/integrations/test_<provider_name>.py` and fill in client calls.
"""

from __future__ import annotations

from typing import Any, Literal
import httpx

from rerunner import wrap
from rerunner.integrations.base import register_adapter


# 1. Example Provider Client (Replace with real SDK client or mock in your integration test)
class ExampleProviderClient:
    """Mock client simulating third-party SDK behavior (e.g. Ollama, Groq, Mistral)."""

    def __init__(self, http_client: httpx.Client | None = None) -> None:
        self.http_client = http_client or httpx.Client()

    def generate(self, prompt: str) -> dict[str, Any]:
        resp = self.http_client.post(
            "https://api.example-provider.ai/v1/generate", json={"prompt": prompt}
        )
        data: dict[str, Any] = resp.json()
        return data


# 2. Example Provider Adapter
@register_adapter
class ExampleProviderAdapter:
    adapter_name = "example_provider"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        return isinstance(client, ExampleProviderClient)

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Any,
        mode: Literal["record", "replay", "fork"] = "replay",
        **kwargs: Any,
    ) -> Any:
        wrap(client.http_client, cassette_path=cassette_path, mode=mode, **kwargs)
        return client


# 3. Test Scaffolding
def test_example_provider_record_and_replay(tmp_path):
    """Verify that the provider client records live requests and replays identically offline."""
    cassette_file = tmp_path / "example_provider.jsonl"

    # Step A: Record Mode
    mock_transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={
                "id": "gen-12345",
                "output": "Deterministic response from example provider.",
                "usage": {"total_tokens": 42},
            },
        )
    )

    client = ExampleProviderClient(http_client=httpx.Client(transport=mock_transport))
    wrapped_client = wrap(client, cassette_file, mode="record")

    live_res = wrapped_client.generate("Hello model!")
    assert live_res["output"] == "Deterministic response from example provider."
    assert cassette_file.exists()

    # Step B: Replay Mode (Zero Network Calls)
    # The client replayer uses air-gapped transport: if it makes a live call, it raises an error.
    replayer_client = ExampleProviderClient()
    wrapped_replayer = wrap(replayer_client, cassette_file, mode="replay")

    replayed_res = wrapped_replayer.generate("Hello model!")
    assert replayed_res == live_res
    assert replayed_res["id"] == "gen-12345"
