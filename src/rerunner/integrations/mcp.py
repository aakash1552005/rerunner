"""Model Context Protocol (MCP) flight recorder and deterministic replay engine.

Enables offline CI testing of MCP-enabled agents (Claude Code, Cursor, LangChain MCP,
and custom MCP clients) with zero external subprocesses or network servers.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, Literal, TypeVar, cast

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry
from rerunner.side_effects import (
    _ACTIVE_FORK_STEP_VAR,
    _ACTIVE_MODE_VAR,
    get_active_cassette,
    reset_active_cassette,
    set_active_cassette,
)

F = TypeVar("F", bound=Callable[..., Any])
AsyncF = TypeVar("AsyncF", bound=Callable[..., Coroutine[Any, Any, Any]])


def _hash_payload(data: Any) -> str:
    """Deterministic hash for MCP JSON-RPC arguments."""
    try:
        serialized = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:  # nosec B110
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class RerunnerMCPClient:
    """Offline flight recorder and replay proxy for Model Context Protocol (MCP) clients.

    Intercepts JSON-RPC tool calls, resource reads, and prompt queries, serializing
    them to append-only cryptographic cassettes. In replay mode, delivers responses
    without spawning server subprocesses or making network calls.

    Example:
        from rerunner.integrations.mcp import RerunnerMCPClient

        with RerunnerMCPClient("tests/cassettes/mcp_flight.jsonl", mode="replay") as mcp:
            result = mcp.call_tool("read_file", {"path": "/workspace/data.json"})
    """

    def __init__(
        self,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        real_client: Any = None,
    ) -> None:
        self.cassette_path = str(cassette_path)
        self.mode = mode
        self.fork_step = fork_step
        self.real_client = real_client
        self._cassette: Cassette | None = None
        self._token: contextvars.Token[Cassette | None] | None = None

    def __enter__(self) -> RerunnerMCPClient:
        self._token = set_active_cassette(
            self.cassette_path, mode=self.mode, fork_step=self.fork_step
        )
        self._cassette = get_active_cassette()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    async def __aenter__(self) -> RerunnerMCPClient:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close session, flush cassette if recording, and restore context tokens."""
        if self._cassette is not None and self.mode in ("record", "fork"):
            self._cassette.save()
        if self._token is not None:
            reset_active_cassette(self._token)
            self._token = None

    def _ensure_cassette(self) -> Cassette:
        if self._cassette is None:
            active = get_active_cassette()
            if active is not None:
                self._cassette = active
            else:
                self._token = set_active_cassette(
                    self.cassette_path, mode=self.mode, fork_step=self.fork_step
                )
                self._cassette = get_active_cassette()
                if self._cassette is None:
                    self._cassette = Cassette(self.cassette_path)
        return self._cassette

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Call an MCP tool with deterministic record/replay semantics."""
        arguments = arguments or {}
        cassette = self._ensure_cassette()
        arg_hash = _hash_payload(arguments)
        tool_identifier = f"mcp:{name}"

        if self.mode == "replay" or (
            self.mode == "fork"
            and self.fork_step is not None
            and len(cassette.entries) < self.fork_step
        ):
            matched_entry = cassette.find_tool_match(name=tool_identifier, side_effect_key=arg_hash)
            if matched_entry is None:
                raise RuntimeError(
                    f"[Rerunner] Replay failed: Unrecorded MCP tool call '{name}' with arguments {arguments}. "
                    f"Expected recorded step matching '{tool_identifier}'."
                )
            return matched_entry.side_effect_result

        # Live record mode: execute on real_client if provided
        if self.real_client is not None and hasattr(self.real_client, "call_tool"):
            result = self.real_client.call_tool(name, arguments)
        else:
            result = {"status": "success", "content": f"Mock MCP execution for {name}"}

        # Persist to cassette
        step_id = cassette.next_step()
        entry = CassetteEntry(
            step=step_id,
            entry_type="tool",
            side_effect_name=tool_identifier,
            side_effect_kwargs=arguments,
            side_effect_result=result,
        )
        cassette.append(entry)
        return result

    async def a_call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Async variant of call_tool for async MCP clients."""
        arguments = arguments or {}
        cassette = self._ensure_cassette()
        arg_hash = _hash_payload(arguments)
        tool_identifier = f"mcp:{name}"

        if self.mode == "replay" or (
            self.mode == "fork"
            and self.fork_step is not None
            and len(cassette.entries) < self.fork_step
        ):
            matched_entry = cassette.find_tool_match(name=tool_identifier, side_effect_key=arg_hash)
            if matched_entry is None:
                raise RuntimeError(
                    f"[Rerunner] Replay failed: Unrecorded async MCP tool call '{name}' with arguments {arguments}."
                )
            return matched_entry.side_effect_result

        if self.real_client is not None:
            if hasattr(self.real_client, "a_call_tool"):
                result = await self.real_client.a_call_tool(name, arguments)
            elif hasattr(self.real_client, "call_tool"):
                result = self.real_client.call_tool(name, arguments)
            else:
                result = {"status": "success", "content": f"Mock async MCP execution for {name}"}
        else:
            result = {"status": "success", "content": f"Mock async MCP execution for {name}"}

        step_id = cassette.next_step()
        entry = CassetteEntry(
            step=step_id,
            entry_type="tool",
            side_effect_name=tool_identifier,
            side_effect_kwargs=arguments,
            side_effect_result=result,
        )
        cassette.append(entry)
        return result


def record_mcp_tool(
    name: str | None = None,
) -> Callable[[F], F]:
    """Decorator to mark a standalone Python function or tool as a deterministic MCP tool.

    Automatically handles cassette registration, argument hashing, and replay isolation.

    Example:
        @record_mcp_tool(name="fetch_weather")
        def fetch_weather(city: str) -> dict:
            ...
    """

    def decorator(fn: F) -> F:
        tool_name = name or fn.__name__

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cassette = get_active_cassette()
            if cassette is None:
                return fn(*args, **kwargs)

            mode = cast(Literal["record", "replay", "fork"], _ACTIVE_MODE_VAR.get("replay"))
            fork_step = _ACTIVE_FORK_STEP_VAR.get(None)

            try:
                import inspect

                sig = inspect.signature(fn)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                tool_args = dict(bound.arguments)
            except Exception:  # nosec B110
                tool_args = kwargs or {"args": list(args)}

            client = RerunnerMCPClient(
                cassette_path=cassette.path,
                mode=mode,
                fork_step=fork_step,
                real_client=type(
                    "LiveMock", (), {"call_tool": lambda self, n, a: fn(*args, **kwargs)}
                )(),
            )
            client._cassette = cassette
            return client.call_tool(tool_name, tool_args)

        return cast(F, wrapper)

    return decorator
