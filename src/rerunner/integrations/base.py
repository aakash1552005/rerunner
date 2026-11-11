"""Base interfaces and extensible provider adapter registry for Rerunner."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol, TypeVar, runtime_checkable
import httpx

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    from pathlib import Path


@runtime_checkable
class BaseProviderAdapter(Protocol):
    """Protocol that custom provider adapters must implement to support unified `rerunner.wrap`."""

    adapter_name: ClassVar[str]

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        """Return True if this adapter can wrap the given client instance."""
        ...

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        """Wrap the client with Rerunner's cassette transport."""
        ...


_ADAPTER_REGISTRY: list[Any] = []
AdapterT = TypeVar("AdapterT")


def register_adapter(adapter_cls: AdapterT) -> AdapterT:
    """Register a custom model or framework adapter with Rerunner's unified wrap engine.

    Example:
        @register_adapter
        class OllamaAdapter:
            adapter_name = "ollama"

            @classmethod
            def can_wrap(cls, client: Any) -> bool:
                return "ollama" in type(client).__module__

            @classmethod
            def wrap(cls, client: Any, cassette_path: Path | str, mode="replay", **kwargs):
                ...
                return client
    """
    if adapter_cls not in _ADAPTER_REGISTRY:
        _ADAPTER_REGISTRY.append(adapter_cls)
    return adapter_cls


def get_registered_adapters() -> list[Any]:
    """Return all currently registered provider adapters."""
    return list(_ADAPTER_REGISTRY)


# Built-in Default Adapters


@register_adapter
class OpenAIAdapter:
    """Built-in adapter for OpenAI and Azure OpenAI clients."""

    adapter_name = "openai"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "")
        type_name = getattr(type(client), "__name__", "")
        return (
            "openai" in module_name.lower()
            or "OpenAI" in type_name
            or (hasattr(client, "chat") and hasattr(client, "completions"))
        )

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.openai import wrap_openai

        return wrap_openai(client, cassette_path=cassette_path, mode=mode, fork_step=fork_step)


@register_adapter
class AnthropicAdapter:
    """Built-in adapter for Anthropic Claude SDK clients."""

    adapter_name = "anthropic"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "")
        type_name = getattr(type(client), "__name__", "")
        return "anthropic" in module_name.lower() or "Anthropic" in type_name

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.anthropic import wrap_anthropic

        return wrap_anthropic(client, cassette_path=cassette_path, mode=mode, fork_step=fork_step)


@register_adapter
class GoogleGenAIAdapter:
    """Built-in adapter for Google GenAI / Gemini / Vertex AI clients."""

    adapter_name = "google_genai"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        return any(
            x in module_name for x in ("google.genai", "vertexai", "google.cloud.aiplatform")
        )

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.google import wrap_google_genai

        return wrap_google_genai(
            client, cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )


@register_adapter
class CohereAdapter:
    """Built-in adapter for Cohere v1/v2 clients and their async variants."""

    adapter_name = "cohere"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "")
        return module_name == "cohere" or module_name.startswith("cohere.")

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.cohere import wrap_cohere

        return wrap_cohere(client, cassette_path=cassette_path, mode=mode, fork_step=fork_step)


@register_adapter
class BedrockAdapter:
    """Built-in adapter for AWS Bedrock clients."""

    adapter_name = "bedrock"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        return "bedrock" in module_name or hasattr(client, "converse")

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.bedrock import wrap_bedrock_client

        return wrap_bedrock_client(
            client, cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )


@register_adapter
class LangChainAdapter:
    """Built-in adapter for LangChain Chat Models."""

    adapter_name = "langchain"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        return "langchain" in module_name or (
            hasattr(client, "invoke") and hasattr(client, "batch")
        )

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.langchain import wrap_langchain_model

        return wrap_langchain_model(
            client, cassette_path=str(cassette_path), mode=mode, fork_step=fork_step
        )


@register_adapter
class LangGraphAdapter:
    """Built-in adapter for LangGraph StateGraph workflows."""

    adapter_name = "langgraph"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        return "langgraph" in module_name or hasattr(client, "checkpointer")

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.langgraph import wrap_langgraph_graph

        replay_mode: Literal["record", "replay"] = "record" if mode == "record" else "replay"
        return wrap_langgraph_graph(client, cassette_path=cassette_path, mode=replay_mode)


@register_adapter
class AutoGenAdapter:
    """Built-in adapter for Microsoft AutoGen / AG2 agents and clients."""

    adapter_name = "autogen"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        type_name = getattr(type(client), "__name__", "")
        return (
            "autogen" in module_name
            or "ag2" in module_name
            or "ConversableAgent" in type_name
            or "AssistantAgent" in type_name
        )

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.autogen import wrap_autogen_agent

        return wrap_autogen_agent(
            client, cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )


@register_adapter
class SemanticKernelAdapter:
    """Built-in adapter for Microsoft Semantic Kernel instances."""

    adapter_name = "semantic_kernel"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        module_name = getattr(type(client), "__module__", "").lower()
        return "semantic_kernel" in module_name or hasattr(client, "services")

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        from rerunner.integrations.semantic_kernel import wrap_semantic_kernel

        return wrap_semantic_kernel(
            client, cassette_path=cassette_path, mode=mode, fork_step=fork_step
        )


@register_adapter
class HTTPXAdapter:
    """Universal fallback adapter for raw httpx.Client and httpx.AsyncClient instances."""

    adapter_name = "httpx"

    @classmethod
    def can_wrap(cls, client: Any) -> bool:
        return isinstance(client, (httpx.Client, httpx.AsyncClient)) or (
            hasattr(client, "_transport") and hasattr(client, "send")
        )

    @classmethod
    def wrap(
        cls,
        client: Any,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        **kwargs: Any,
    ) -> Any:
        is_async = isinstance(client, httpx.AsyncClient)
        existing_transport = getattr(client, "_transport", None)
        # Preserve existing custom transport (e.g. MockTransport in tests) as real_transport
        real_transport = kwargs.pop("real_transport", existing_transport)

        if is_async:
            client._transport = AsyncCassetteTransport(
                cassette_path=cassette_path,
                mode=mode,
                fork_step=fork_step,
                real_transport=real_transport,
                **kwargs,
            )
        else:
            client._transport = CassetteTransport(
                cassette_path=cassette_path,
                mode=mode,
                fork_step=fork_step,
                real_transport=real_transport,
                **kwargs,
            )
        if hasattr(client, "_mounts"):
            client._mounts.clear()
        return client


def wrap(
    client: Any,
    cassette_path: Path | str,
    mode: Literal["record", "replay", "fork"] = "replay",
    fork_step: int | None = None,
    **kwargs: Any,
) -> Any:
    """Attach Rerunner cassette transport to any supported client via unified auto-detection.

    Inspects registered adapters (OpenAI, Anthropic, Google, Cohere, Bedrock, LangChain,
    AutoGen, Semantic Kernel, HTTPX, and user-registered providers) and attaches
    deterministic record/replay transport in 1 line.

    Example:
        from rerunner import wrap

        # Works transparently on any SDK client!
        client = wrap(client, "cassette.zst", mode="replay")
    """
    for adapter in _ADAPTER_REGISTRY:
        try:
            can_handle = adapter.can_wrap(client)
        except (AttributeError, TypeError, ValueError):
            can_handle = False

        if can_handle:
            return adapter.wrap(
                client,
                cassette_path=cassette_path,
                mode=mode,
                fork_step=fork_step,
                **kwargs,
            )

    # Secondary check: if client has an inner _client that can be wrapped
    inner_client = getattr(client, "_client", None)
    if inner_client is not None:
        for adapter in _ADAPTER_REGISTRY:
            try:
                can_handle_inner = adapter.can_wrap(inner_client)
            except (AttributeError, TypeError, ValueError):
                can_handle_inner = False

            if can_handle_inner:
                adapter.wrap(
                    inner_client,
                    cassette_path=cassette_path,
                    mode=mode,
                    fork_step=fork_step,
                    **kwargs,
                )
                return client

    raise TypeError(
        f"Unable to auto-detect adapter for client type '{type(client).__name__}'. "
        "Register a custom adapter via `@rerunner.integrations.register_adapter` "
        "or pass an explicit `httpx.Client(transport=CassetteTransport(...))`."
    )
