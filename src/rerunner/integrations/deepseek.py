"""Record and replay DeepSeek calls made with the OpenAI-compatible SDK."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from rerunner.integrations.openai import wrap_openai


def wrap_deepseek_client(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach cassette recording or offline replay to a sync or async DeepSeek client.

    Configure the OpenAI client with DeepSeek's base URL before wrapping it.
    The existing OpenAI transport adapter preserves that URL and handles both
    synchronous and asynchronous clients.

    Example:
        from openai import OpenAI
        from rerunner.integrations import wrap_deepseek_client

        client = OpenAI(api_key="...", base_url="https://api.deepseek.com")
        client = wrap_deepseek_client(client, "deepseek.jsonl", mode="record")
    """
    return wrap_openai(client, cassette_path, mode=mode, fork_step=fork_step)


wrap = wrap_deepseek_client
