"""Zero-friction wrapper for Microsoft AutoGen (AG2) agents and clients."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal
import httpx
from rerunner.async_transport import AsyncCassetteTransport
from rerunner.integrations.openai import wrap_openai
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


def wrap_autogen_client(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Attach Rerunner cassette transport to an AutoGen OpenAIWrapper or client instance.

    Works with AutoGen's `OpenAIWrapper` which manages one or more underlying
    `openai.OpenAI` or `openai.AsyncOpenAI` client instances.
    """
    # If it's an AutoGen OpenAIWrapper, patch each client in _clients
    if hasattr(client, "_clients"):
        for sub_client in client._clients:
            wrap_openai(sub_client, cassette_path, mode=mode, fork_step=fork_step)
        return client

    # If it has a standard http client
    if hasattr(client, "_client"):
        return wrap_openai(client, cassette_path, mode=mode, fork_step=fork_step)

    # Fallback to direct client wrapping
    if isinstance(client, httpx.AsyncClient):
        client._transport = AsyncCassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )
    elif isinstance(client, httpx.Client):
        client._transport = CassetteTransport(
            cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )

    return client


def wrap_autogen_agent(
    agent: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
) -> Any:
    """Wrap an AutoGen ConversableAgent, AssistantAgent, or UserProxyAgent for offline replay.

    Intercepts outbound LLM calls executed during multi-agent conversations.

    Example:
        from autogen import AssistantAgent
        from rerunner.integrations.autogen import wrap_autogen_agent

        assistant = AssistantAgent("assistant", llm_config=llm_config)
        wrap_autogen_agent(assistant, "cassettes/autogen_debate.jsonl", mode="replay")
    """
    if hasattr(agent, "client") and agent.client is not None:
        wrap_autogen_client(agent.client, cassette_path, mode=mode, fork_step=fork_step)

    # Check for direct llm_config or client references
    if hasattr(agent, "_client"):
        wrap_autogen_client(agent._client, cassette_path, mode=mode, fork_step=fork_step)

    return agent
