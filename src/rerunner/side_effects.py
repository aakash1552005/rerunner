"""Safe execution stubbing for external agent side-effects (DB writes, Slack, payments) and deterministic tool decorators.

Enforces fail-closed safety during replay, argument-hash based matching,
sanitization of sensitive arguments/results, and thread/async context safety via contextvars.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, overload

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry
from rerunner.sanitizer import sanitize_payload

if TYPE_CHECKING:
    pass

F = TypeVar("F", bound=Callable[..., Any])


class SideEffectError(Exception):
    """Raised when an unrecorded side-effect is encountered in replay mode or replay is unconfigured."""


_ACTIVE_CASSETTE: contextvars.ContextVar[Cassette | None] = contextvars.ContextVar(
    "active_cassette", default=None
)
_ACTIVE_MODE_VAR: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_rerunner_mode", default="replay"
)
_ACTIVE_FORK_STEP_VAR: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "_rerunner_fork_step", default=None
)
_CURRENT_SIDE_EFFECT_STEP_VAR: contextvars.ContextVar[int] = contextvars.ContextVar(
    "_rerunner_se_step", default=0
)
_SIDE_EFFECT_CURSORS_VAR: contextvars.ContextVar[dict[str, int] | None] = contextvars.ContextVar(
    "_rerunner_se_cursors", default=None
)


def compute_side_effect_key(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 key identifying a side-effect call by name and arguments."""
    try:
        payload = json.dumps(
            {"name": name, "args": args, "kwargs": kwargs},
            sort_keys=True,
            default=str,
            ensure_ascii=True,
        )
    except Exception:
        payload = f"{name}:{args!r}:{kwargs!r}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def set_active_cassette(
    cassette: Cassette | Path | str | None,
    mode: str = "replay",
    fork_step: int | None = None,
) -> contextvars.Token[Cassette | None]:
    """Set the active cassette context for side-effect recording and stubbing.

    Returns the ContextVar token so nested contexts can be restored cleanly.
    """
    _ACTIVE_MODE_VAR.set(mode)
    _ACTIVE_FORK_STEP_VAR.set(fork_step)
    _CURRENT_SIDE_EFFECT_STEP_VAR.set(0)
    _SIDE_EFFECT_CURSORS_VAR.set({})

    if cassette is None:
        return _ACTIVE_CASSETTE.set(None)
    if isinstance(cassette, Cassette):
        return _ACTIVE_CASSETTE.set(cassette)

    cass_obj = Cassette.load(cassette) if mode == "replay" else Cassette(cassette)
    return _ACTIVE_CASSETTE.set(cass_obj)


def reset_active_cassette(token: contextvars.Token[Cassette | None]) -> None:
    """Reset the active cassette ContextVar to the token's previous value."""
    _ACTIVE_CASSETTE.reset(token)


def get_active_cassette() -> Cassette | None:
    """Return the active Cassette in the current context."""
    return _ACTIVE_CASSETTE.get()


def side_effect(name: str | None = None) -> Callable[[F], F]:
    """Decorator preventing destructive actions (DB writes, webhooks, payments) during replay.

    FAILS CLOSED: If no matching side-effect is recorded in the cassette, raises
    SideEffectError rather than executing live during replay.
    """

    def decorator(func: F) -> F:
        fn_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cassette = _ACTIVE_CASSETTE.get()
            mode = _ACTIVE_MODE_VAR.get()
            fork_step = _ACTIVE_FORK_STEP_VAR.get()
            step = cassette.next_step() if cassette else _CURRENT_SIDE_EFFECT_STEP_VAR.get() + 1
            _CURRENT_SIDE_EFFECT_STEP_VAR.set(step)

            should_replay = mode == "replay" or (
                mode == "fork" and fork_step is not None and step <= fork_step
            )

            call_key = compute_side_effect_key(fn_name, args, kwargs)

            if should_replay:
                if cassette is None:
                    raise SideEffectError(
                        f"Cannot replay side-effect '{fn_name}': no active cassette is configured."
                    )

                cursors = _SIDE_EFFECT_CURSORS_VAR.get()
                if cursors is None:
                    cursors = {}
                    _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                cursor = cursors.get(call_key, 0)

                matching_entries = [
                    entry
                    for entry in cassette.entries
                    if entry.entry_type in ("side_effect", "tool")
                    and entry.side_effect_name == fn_name
                ]

                exact_arg_matches = [
                    e
                    for e in matching_entries
                    if compute_side_effect_key(
                        e.side_effect_name or "",
                        tuple(e.side_effect_args or []),
                        e.side_effect_kwargs or {},
                    )
                    == call_key
                ]

                target_matches = exact_arg_matches if exact_arg_matches else matching_entries

                if cursor < len(target_matches):
                    matched_entry = target_matches[cursor]
                    cursors[call_key] = cursor + 1
                    _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                    return matched_entry.side_effect_result

                raise SideEffectError(
                    f"[Replay Step {step}] Unrecorded side effect '{fn_name}' (call_key: {call_key[:8]}). "
                    f"Side effects fail closed during replay to prevent unauthorized live execution."
                )

            result = func(*args, **kwargs)

            if cassette is not None and mode in ("record", "fork", "auto"):
                cleaned_args = sanitize_payload(list(args))
                cleaned_kwargs = sanitize_payload(kwargs)
                cleaned_result = sanitize_payload(result)

                entry = CassetteEntry(
                    step=step,
                    entry_type="side_effect",
                    side_effect_name=fn_name,
                    side_effect_args=cleaned_args,
                    side_effect_kwargs=cleaned_kwargs,
                    side_effect_result=cleaned_result,
                )
                cassette.append(entry)
                cassette.save()

            return result

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            cassette = _ACTIVE_CASSETTE.get()
            mode = _ACTIVE_MODE_VAR.get()
            fork_step = _ACTIVE_FORK_STEP_VAR.get()
            step = cassette.next_step() if cassette else _CURRENT_SIDE_EFFECT_STEP_VAR.get() + 1
            _CURRENT_SIDE_EFFECT_STEP_VAR.set(step)

            should_replay = mode == "replay" or (
                mode == "fork" and fork_step is not None and step <= fork_step
            )

            call_key = compute_side_effect_key(fn_name, args, kwargs)

            if should_replay:
                if cassette is None:
                    raise SideEffectError(
                        f"Cannot replay side-effect '{fn_name}': no active cassette is configured."
                    )

                cursors = _SIDE_EFFECT_CURSORS_VAR.get()
                if cursors is None:
                    cursors = {}
                    _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                cursor = cursors.get(call_key, 0)

                matching_entries = [
                    entry
                    for entry in cassette.entries
                    if entry.entry_type in ("side_effect", "tool")
                    and entry.side_effect_name == fn_name
                ]

                exact_arg_matches = [
                    e
                    for e in matching_entries
                    if compute_side_effect_key(
                        e.side_effect_name or "",
                        tuple(e.side_effect_args or []),
                        e.side_effect_kwargs or {},
                    )
                    == call_key
                ]

                target_matches = exact_arg_matches if exact_arg_matches else matching_entries

                if cursor < len(target_matches):
                    matched_entry = target_matches[cursor]
                    cursors[call_key] = cursor + 1
                    _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                    return matched_entry.side_effect_result

                raise SideEffectError(
                    f"[Replay Step {step}] Unrecorded side effect '{fn_name}' (call_key: {call_key[:8]}). "
                    f"Side effects fail closed during replay to prevent unauthorized live execution."
                )

            result = await func(*args, **kwargs)

            if cassette is not None and mode in ("record", "fork", "auto"):
                cleaned_args = sanitize_payload(list(args))
                cleaned_kwargs = sanitize_payload(kwargs)
                cleaned_result = sanitize_payload(result)

                entry = CassetteEntry(
                    step=step,
                    entry_type="side_effect",
                    side_effect_name=fn_name,
                    side_effect_args=cleaned_args,
                    side_effect_kwargs=cleaned_kwargs,
                    side_effect_result=cleaned_result,
                )
                cassette.append(entry)
                cassette.save()

            return result

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return wrapper  # type: ignore[return-value]

    return decorator


@overload
def record_tool(func: F, /) -> F: ...


@overload
def record_tool(name: str, /) -> Callable[[F], F]: ...


@overload
def record_tool(*, name: str | None = None) -> Callable[[F], F]: ...


def record_tool(
    func_or_name: F | str | None = None,
    /,
    *,
    name: str | None = None,
) -> Any:
    """Record and replay external tools, functions, and DB queries deterministically.

    During 'record' mode, executes the wrapped function, serializes return value
    (or raised exception) to the active cassette, and returns the result.
    During 'replay' mode, bypasses live execution and returns the recorded result deterministically.
    """

    def create_decorator(tool_name: str | None) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            fn_name = tool_name or func.__name__

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                cassette = _ACTIVE_CASSETTE.get()
                mode = _ACTIVE_MODE_VAR.get()
                fork_step = _ACTIVE_FORK_STEP_VAR.get()

                if cassette is None:
                    return func(*args, **kwargs)

                step = cassette.next_step()
                should_replay = mode == "replay" or (
                    mode == "fork" and fork_step is not None and step <= fork_step
                )

                call_key = compute_side_effect_key(fn_name, args, kwargs)

                if should_replay:
                    matching = [
                        e
                        for e in cassette.entries
                        if e.entry_type in ("tool", "side_effect") and e.side_effect_name == fn_name
                    ]
                    exact = [
                        e
                        for e in matching
                        if compute_side_effect_key(
                            e.side_effect_name or "",
                            tuple(e.side_effect_args or []),
                            e.side_effect_kwargs or {},
                        )
                        == call_key
                    ]
                    candidates = exact if exact else matching

                    cursors = _SIDE_EFFECT_CURSORS_VAR.get() or {}
                    cursor = cursors.get(call_key, 0)

                    if cursor < len(candidates):
                        match = candidates[cursor]
                        cursors[call_key] = cursor + 1
                        _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                        if match.side_effect_exception is not None:
                            raise RuntimeError(match.side_effect_exception)
                        return match.side_effect_result

                    raise SideEffectError(
                        f"[Replay Step {step}] No recorded tool execution found for '{fn_name}' "
                        f"(key: {call_key[:8]}). Cannot execute live during replay."
                    )

                # Record mode execution
                exc: Exception | None = None
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    exc = e
                    result = None

                cleaned_args = sanitize_payload(list(args))
                cleaned_kwargs = sanitize_payload(kwargs)
                cleaned_result = sanitize_payload(result) if exc is None else None
                exc_str = str(exc) if exc is not None else None

                entry = CassetteEntry(
                    step=step,
                    entry_type="tool",
                    side_effect_name=fn_name,
                    side_effect_args=cleaned_args,
                    side_effect_kwargs=cleaned_kwargs,
                    side_effect_result=cleaned_result,
                    side_effect_exception=exc_str,
                )
                cassette.append(entry)
                cassette.save()

                if exc is not None:
                    raise exc
                return result

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                cassette = _ACTIVE_CASSETTE.get()
                mode = _ACTIVE_MODE_VAR.get()
                fork_step = _ACTIVE_FORK_STEP_VAR.get()

                if cassette is None:
                    return await func(*args, **kwargs)

                step = cassette.next_step()
                should_replay = mode == "replay" or (
                    mode == "fork" and fork_step is not None and step <= fork_step
                )

                call_key = compute_side_effect_key(fn_name, args, kwargs)

                if should_replay:
                    matching = [
                        e
                        for e in cassette.entries
                        if e.entry_type in ("tool", "side_effect") and e.side_effect_name == fn_name
                    ]
                    exact = [
                        e
                        for e in matching
                        if compute_side_effect_key(
                            e.side_effect_name or "",
                            tuple(e.side_effect_args or []),
                            e.side_effect_kwargs or {},
                        )
                        == call_key
                    ]
                    candidates = exact if exact else matching

                    cursors = _SIDE_EFFECT_CURSORS_VAR.get() or {}
                    cursor = cursors.get(call_key, 0)

                    if cursor < len(candidates):
                        match = candidates[cursor]
                        cursors[call_key] = cursor + 1
                        _SIDE_EFFECT_CURSORS_VAR.set(cursors)
                        if match.side_effect_exception is not None:
                            raise RuntimeError(match.side_effect_exception)
                        return match.side_effect_result

                    raise SideEffectError(
                        f"[Replay Step {step}] No recorded tool execution found for '{fn_name}' "
                        f"(key: {call_key[:8]}). Cannot execute live during replay."
                    )

                exc: Exception | None = None
                try:
                    result = await func(*args, **kwargs)
                except Exception as e:
                    exc = e
                    result = None

                cleaned_args = sanitize_payload(list(args))
                cleaned_kwargs = sanitize_payload(kwargs)
                cleaned_result = sanitize_payload(result) if exc is None else None
                exc_str = str(exc) if exc is not None else None

                entry = CassetteEntry(
                    step=step,
                    entry_type="tool",
                    side_effect_name=fn_name,
                    side_effect_args=cleaned_args,
                    side_effect_kwargs=cleaned_kwargs,
                    side_effect_result=cleaned_result,
                    side_effect_exception=exc_str,
                )
                cassette.append(entry)
                cassette.save()

                if exc is not None:
                    raise exc
                return result

            if inspect.iscoroutinefunction(func):
                return async_wrapper  # type: ignore[return-value]
            return sync_wrapper  # type: ignore[return-value]

        return decorator

    if callable(func_or_name):
        return create_decorator(name)(func_or_name)
    if isinstance(func_or_name, str):
        return create_decorator(func_or_name)
    return create_decorator(name)
