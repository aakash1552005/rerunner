"""Zero-touch SDK auto-patching for httpx.Client and httpx.AsyncClient within Rerunner sessions."""

from __future__ import annotations

import contextvars
import threading
from typing import Any, Protocol

import httpx


class ActiveSessionProtocol(Protocol):
    """Minimal protocol implemented by Session for zero-touch HTTPX patching."""

    @property
    def auto_patch(self) -> bool: ...

    @property
    def transport(self) -> httpx.BaseTransport: ...

    @property
    def async_transport(self) -> httpx.AsyncBaseTransport: ...


_ACTIVE_SESSION: contextvars.ContextVar[ActiveSessionProtocol | None] = contextvars.ContextVar(
    "_rerunner_active_session", default=None
)

_ORIGINAL_SYNC_INIT = httpx.Client.__init__
_ORIGINAL_ASYNC_INIT = httpx.AsyncClient.__init__
_PATCH_REF_COUNT = 0
_PATCH_LOCK = threading.Lock()


def _patched_client_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
    is_unpatched = kwargs.pop("_rerunner_unpatched", False)
    session = _ACTIVE_SESSION.get()

    if (
        session is not None
        and getattr(session, "auto_patch", True)
        and not is_unpatched
        and kwargs.get("transport") is None
    ):
        kwargs["transport"] = session.transport
        kwargs["mounts"] = {}

    _ORIGINAL_SYNC_INIT(self, *args, **kwargs)


def _patched_async_client_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
    is_unpatched = kwargs.pop("_rerunner_unpatched", False)
    session = _ACTIVE_SESSION.get()

    if (
        session is not None
        and getattr(session, "auto_patch", True)
        and not is_unpatched
        and kwargs.get("transport") is None
    ):
        kwargs["transport"] = session.async_transport
        kwargs["mounts"] = {}

    _ORIGINAL_ASYNC_INIT(self, *args, **kwargs)


def install_auto_patch() -> None:
    """Install the global HTTPX interception hooks with reference counting."""
    global _PATCH_REF_COUNT
    with _PATCH_LOCK:
        if _PATCH_REF_COUNT == 0:
            httpx.Client.__init__ = _patched_client_init  # type: ignore[method-assign]
            httpx.AsyncClient.__init__ = _patched_async_client_init  # type: ignore[method-assign]
        _PATCH_REF_COUNT += 1


def uninstall_auto_patch() -> None:
    """Restore original HTTPX Client initializers when reference count drops to 0."""
    global _PATCH_REF_COUNT
    with _PATCH_LOCK:
        if _PATCH_REF_COUNT > 0:
            _PATCH_REF_COUNT -= 1
            if _PATCH_REF_COUNT == 0:
                httpx.Client.__init__ = _ORIGINAL_SYNC_INIT  # type: ignore[method-assign]
                httpx.AsyncClient.__init__ = _ORIGINAL_ASYNC_INIT  # type: ignore[method-assign]


def set_active_session(
    session: ActiveSessionProtocol | None,
) -> contextvars.Token[ActiveSessionProtocol | None]:
    """Set the active Session in contextvars and manage auto-patch hook reference count."""
    if session is not None and getattr(session, "auto_patch", True):
        install_auto_patch()
    return _ACTIVE_SESSION.set(session)


def reset_active_session(token: contextvars.Token[ActiveSessionProtocol | None]) -> None:
    """Reset the active Session in contextvars and decrement auto-patch hook reference count."""
    current = _ACTIVE_SESSION.get()
    if current is not None and getattr(current, "auto_patch", True):
        uninstall_auto_patch()
    _ACTIVE_SESSION.reset(token)


def get_active_session() -> ActiveSessionProtocol | None:
    """Return the active Session in the current context."""
    return _ACTIVE_SESSION.get()
