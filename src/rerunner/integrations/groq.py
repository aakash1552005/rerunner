"""Groq SDK integration for Rerunner."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from rerunner.integrations.openai import wrap_openai

if TYPE_CHECKING:
    from pathlib import Path


def wrap_groq_client(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach Rerunner's cassette transport to a Groq client."""
    return wrap_openai(
        client,
        cassette_path,
        mode=mode,
        fork_step=fork_step,
    )
