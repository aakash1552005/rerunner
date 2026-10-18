"""Zero-touch SDK auto-patching for httpx.Client and httpx.AsyncClient within Rerunner sessions."""

from __future__ import annotations

import contextvars
import threading
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from rerunner.session import Session

_ACTIVE_SESSION: contextvars.ContextVar[Session | None] = contextvars.ContextVar(
    "_rerunner_active_session", default=None
)

_ORIG_CLIENT_INIT = httpx.Client.__init__
_ORIG_ASYNC_CLIENT_INIT = httpx.AsyncClient.__init__
_IS_PATCHED = False
_PATCH_LOCK = threading.Lock()


def _patched_client_init(self: httpx.Client, *args: Any, **kwargs: Any) -> None:
    is_unpatched = kwargs.pop("_rerunner_unpatched", False)
    session = _ACTIVE_SESSION.get()

    if session is not None and not is_unpatched and kwargs.get("transport") is None:
        kwargs["transport"] = session.transport
        if "mounts" not in kwargs or kwargs["mounts"] is None:
            kwargs["mounts"] = {}

    _ORIG_CLIENT_INIT(self, *args, **kwargs)


def _patched_async_client_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
    is_unpatched = kwargs.pop("_rerunner_unpatched", False)
    session = _ACTIVE_SESSION.get()

    if session is not None and not is_unpatched and kwargs.get("transport") is None:
        kwargs["transport"] = session.async_transport
        if "mounts" not in kwargs or kwargs["mounts"] is None:
            kwargs["mounts"] = {}

    _ORIG_ASYNC_CLIENT_INIT(self, *args, **kwargs)


def install_auto_patch() -> None:
    """Install the global HTTPX interception hooks if not already installed."""
    global _IS_PATCHED
    with _PATCH_LOCK:
        if not _IS_PATCHED:
            httpx.Client.__init__ = _patched_client_init  # type: ignore[method-assign]
            httpx.AsyncClient.__init__ = _patched_async_client_init  # type: ignore[method-assign]
            _IS_PATCHED = True


def uninstall_auto_patch() -> None:
    """Restore original HTTPX Client initializers."""
    global _IS_PATCHED
    with _PATCH_LOCK:
        if _IS_PATCHED:
            httpx.Client.__init__ = _ORIG_CLIENT_INIT  # type: ignore[method-assign]
            httpx.AsyncClient.__init__ = _ORIG_ASYNC_CLIENT_INIT  # type: ignore[method-assign]
            _IS_PATCHED = False


def set_active_session(session: Session | None) -> contextvars.Token[Session | None]:
    """Set the active Session in contextvars and ensure auto-patch hooks are installed."""
    if session is not None:
        install_auto_patch()
    return _ACTIVE_SESSION.set(session)


def reset_active_session(token: contextvars.Token[Session | None]) -> None:
    """Reset the active Session in contextvars."""
    _ACTIVE_SESSION.reset(token)
