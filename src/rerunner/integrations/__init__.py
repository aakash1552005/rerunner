"""Official framework integrations and zero-friction client adapters."""

from __future__ import annotations

from rerunner.integrations.anthropic import wrap_anthropic
from rerunner.integrations.google import wrap_gemini, wrap_google_genai, wrap_vertexai
from rerunner.integrations.langchain import RerunnerCallbackHandler
from rerunner.integrations.llamaindex import LlamaIndexRerunnerHandler
from rerunner.integrations.openai import wrap_openai

__all__ = [
    "LlamaIndexRerunnerHandler",
    "RerunnerCallbackHandler",
    "wrap_anthropic",
    "wrap_gemini",
    "wrap_google_genai",
    "wrap_openai",
    "wrap_vertexai",
]
