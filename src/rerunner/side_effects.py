"""Safe execution stubbing for external agent side-effects (DB writes, Slack, payments).

Enforces fail-closed safety during replay, argument-hash based matching,
sanitization of sensitive arguments/results, and thread/async context safety.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry
from rerunner.sanitizer import sanitize_payload

if TYPE_CHECKING:
    pass

F = TypeVar("F", bound=Callable[..., Any])


class SideEffectError(Exception):
    """Raised when an unrecorded side-effect is encountered in replay mode or replay is unconfigured."""


_ACTIVE_SESSION_CASSETTE_VAR: contextvars.ContextVar[Cassette | None] = contextvars.ContextVar(
    "_rerunner_cassette", default=None
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
) -> None:
    """Set the active cassette context for side-effect recording and stubbing."""
    _ACTIVE_MODE_VAR.set(mode)
    _ACTIVE_FORK_STEP_VAR.set(fork_step)
    _CURRENT_SIDE_EFFECT_STEP_VAR.set(0)
    _SIDE_EFFECT_CURSORS_VAR.set({})

    if cassette is None:
        _ACTIVE_SESSION_CASSETTE_VAR.set(None)
    elif isinstance(cassette, Cassette):
        _ACTIVE_SESSION_CASSETTE_VAR.set(cassette)
    else:
        cass_obj = Cassette.load(cassette) if mode == "replay" else Cassette(cassette)
        _ACTIVE_SESSION_CASSETTE_VAR.set(cass_obj)


def side_effect(name: str | None = None) -> Callable[[F], F]:
    """Decorator preventing destructive actions (DB writes, webhooks, payments) during replay.

    FAILS CLOSED: If no matching side-effect is recorded in the cassette, raises
    SideEffectError rather than executing live during replay.

    Example:
        @side_effect(name="charge_customer")
        def charge_credit_card(user_id: str, amount: float) -> str:
            # Only runs on live recording. During replay, returns recorded tx_id safely.
            return stripe.charge(user_id, amount)
    """

    def decorator(func: F) -> F:
        fn_name = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cassette = _ACTIVE_SESSION_CASSETTE_VAR.get()
            mode = _ACTIVE_MODE_VAR.get()
            fork_step = _ACTIVE_FORK_STEP_VAR.get()
            step = _CURRENT_SIDE_EFFECT_STEP_VAR.get() + 1
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

                # Look up matching recorded side-effect entries
                matching_entries = [
                    entry
                    for entry in cassette.entries
                    if entry.entry_type == "side_effect" and entry.side_effect_name == fn_name
                ]

                # If argument-level matches exist, prioritize exact argument match
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

                # FAIL CLOSED: Never run live during replay when no match exists
                raise SideEffectError(
                    f"[Replay Step {step}] Unrecorded side effect '{fn_name}' (call_key: {call_key[:8]}). "
                    f"Side effects fail closed during replay to prevent unauthorized live execution."
                )

            # Live execution
            result = func(*args, **kwargs)

            if cassette is not None and mode in ("record", "fork"):
                # Sanitize arguments and result to prevent storing credit cards, passwords, etc.
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
            cassette = _ACTIVE_SESSION_CASSETTE_VAR.get()
            mode = _ACTIVE_MODE_VAR.get()
            fork_step = _ACTIVE_FORK_STEP_VAR.get()
            step = _CURRENT_SIDE_EFFECT_STEP_VAR.get() + 1
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
                    if entry.entry_type == "side_effect" and entry.side_effect_name == fn_name
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

                # FAIL CLOSED
                raise SideEffectError(
                    f"[Replay Step {step}] Unrecorded side effect '{fn_name}' (call_key: {call_key[:8]}). "
                    f"Side effects fail closed during replay to prevent unauthorized live execution."
                )

            result = await func(*args, **kwargs)

            if cassette is not None and mode in ("record", "fork"):
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
