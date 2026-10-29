"""Official framework integrations and zero-friction client adapters."""

from __future__ import annotations

from rerunner.integrations.anthropic import mock_anthropic_batch_response, wrap_anthropic
from rerunner.integrations.autogen import wrap_autogen_agent, wrap_autogen_client
from rerunner.integrations.bedrock import mock_bedrock_converse_response, wrap_bedrock_client
from rerunner.integrations.google import wrap_gemini, wrap_google_genai, wrap_vertexai
from rerunner.integrations.langchain import RerunnerCallbackHandler, wrap_langchain_model
from rerunner.integrations.llamaindex import LlamaIndexRerunnerHandler
from rerunner.integrations.mcp import RerunnerMCPClient, record_mcp_tool
from rerunner.integrations.openai import wrap_openai
from rerunner.integrations.semantic_kernel import wrap_semantic_kernel

__all__ = [
    "LlamaIndexRerunnerHandler",
    "RerunnerCallbackHandler",
    "RerunnerMCPClient",
    "mock_anthropic_batch_response",
    "mock_bedrock_converse_response",
    "record_mcp_tool",
    "wrap_anthropic",
    "wrap_autogen_agent",
    "wrap_autogen_client",
    "wrap_bedrock_client",
    "wrap_gemini",
    "wrap_google_genai",
    "wrap_langchain_model",
    "wrap_openai",
    "wrap_semantic_kernel",
    "wrap_vertexai",
]
