"""Zero-touch interception for ``aiohttp.ClientSession._request`` (Issue #79)."""

from __future__ import annotations

from collections.abc import Callable
import json as json_mod
from typing import Any
from urllib.parse import urlencode

import httpx

_ORIGINAL_AIOHTTP_REQUEST: Any = None
_SESSION_PROVIDER: Callable[[], Any] | None = None


class _ReplayedAiohttpResponse:
    """Minimal async-context-manager response compatible with aiohttp consumers."""

    def __init__(self, httpx_resp: httpx.Response, url: str) -> None:
        self.status = httpx_resp.status_code
        self.reason = httpx_resp.reason_phrase
        self.headers = dict(httpx_resp.headers.items())
        self.url = url
        self._body = httpx_resp.content

    async def read(self) -> bytes:
        return self._body

    async def text(self, encoding: str = "utf-8") -> str:
        return self._body.decode(encoding, errors="replace")

    async def json(self, **kwargs: Any) -> Any:
        return json_mod.loads(self._body.decode("utf-8"), **kwargs)

    async def release(self) -> None:
        return None

    async def __aenter__(self) -> _ReplayedAiohttpResponse:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None


def install_aiohttp_patch(session_provider: Callable[[], Any]) -> None:
    """Patch ``aiohttp.ClientSession._request`` if ``aiohttp`` is installed."""
    global _ORIGINAL_AIOHTTP_REQUEST, _SESSION_PROVIDER
    try:
        import aiohttp
    except ImportError:
        return

    _SESSION_PROVIDER = session_provider
    if _ORIGINAL_AIOHTTP_REQUEST is not None:
        return

    _ORIGINAL_AIOHTTP_REQUEST = aiohttp.ClientSession._request

    async def _patched_aiohttp_request(
        self: Any,
        method: str,
        str_or_url: Any,
        *,
        params: Any = None,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        active_session = _SESSION_PROVIDER() if _SESSION_PROVIDER is not None else None
        if active_session is not None and getattr(active_session, "auto_patch", True):
            target_url = str(str_or_url)
            if params:
                query = urlencode(params, doseq=True) if isinstance(params, dict) else str(params)
                sep = "&" if "?" in target_url else "?"
                target_url = f"{target_url}{sep}{query}"
            req_headers = dict(headers or {})
            content: bytes | None = None
            if json is not None:
                content = json_mod.dumps(json).encode("utf-8")
                req_headers.setdefault("content-type", "application/json")
            elif isinstance(data, bytes):
                content = data
            elif isinstance(data, str):
                content = data.encode("utf-8")

            httpx_req = httpx.Request(
                method=method.upper(),
                url=target_url,
                headers=req_headers,
                content=content,
            )
            httpx_resp = await active_session.async_transport.handle_async_request(httpx_req)
            await httpx_resp.aread()
            return _ReplayedAiohttpResponse(httpx_resp, target_url)

        return await _ORIGINAL_AIOHTTP_REQUEST(
            self,
            method,
            str_or_url,
            params=params,
            data=data,
            json=json,
            headers=headers,
            **kwargs,
        )

    aiohttp.ClientSession._request = _patched_aiohttp_request  # type: ignore[method-assign]


def uninstall_aiohttp_patch() -> None:
    """Restore original ``aiohttp.ClientSession._request`` if patched."""
    global _ORIGINAL_AIOHTTP_REQUEST, _SESSION_PROVIDER
    if _ORIGINAL_AIOHTTP_REQUEST is None:
        return
    try:
        import aiohttp

        aiohttp.ClientSession._request = _ORIGINAL_AIOHTTP_REQUEST
    except ImportError:
        pass
    _ORIGINAL_AIOHTTP_REQUEST = None
    _SESSION_PROVIDER = None
