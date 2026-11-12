"""Zero-touch interception for ``requests.Session.request`` (Issue #79)."""

from __future__ import annotations

from collections.abc import Callable
import json as json_mod
from typing import Any
from urllib.parse import urlencode

import httpx

_ORIGINAL_SESSION_REQUEST: Any = None
_SESSION_PROVIDER: Callable[[], Any] | None = None


def _build_httpx_request(
    method: str,
    url: str,
    *,
    params: Any = None,
    data: Any = None,
    headers: dict[str, str] | None = None,
    json: Any = None,
) -> httpx.Request:
    target_url = url
    if params:
        query = urlencode(params, doseq=True) if isinstance(params, dict) else str(params)
        sep = "&" if "?" in target_url else "?"
        target_url = f"{target_url}{sep}{query}"

    req_headers = dict(headers or {})
    content: bytes | str | None = None
    if json is not None:
        content = json_mod.dumps(json).encode("utf-8")
        req_headers.setdefault("content-type", "application/json")
    elif isinstance(data, bytes):
        content = data
    elif isinstance(data, str):
        content = data.encode("utf-8")
    elif isinstance(data, dict):
        content = urlencode(data, doseq=True).encode("utf-8")
        req_headers.setdefault("content-type", "application/x-www-form-urlencoded")

    return httpx.Request(
        method=method.upper(), url=target_url, headers=req_headers, content=content
    )


def _to_requests_response(httpx_resp: httpx.Response, url: str) -> Any:
    import requests
    from requests.structures import CaseInsensitiveDict

    resp = requests.Response()
    resp.status_code = httpx_resp.status_code
    resp.url = url
    resp.headers = CaseInsensitiveDict(httpx_resp.headers.items())
    resp._content = httpx_resp.read()
    resp.encoding = httpx_resp.encoding or "utf-8"
    return resp


def install_requests_patch(session_provider: Callable[[], Any]) -> None:
    """Patch ``requests.Session.request`` if ``requests`` is installed."""
    global _ORIGINAL_SESSION_REQUEST, _SESSION_PROVIDER
    try:
        import requests
    except ImportError:
        return

    _SESSION_PROVIDER = session_provider
    if _ORIGINAL_SESSION_REQUEST is not None:
        return

    _ORIGINAL_SESSION_REQUEST = requests.Session.request

    def _patched_request(
        self: Any,
        method: str,
        url: str,
        params: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        cookies: Any = None,
        files: Any = None,
        auth: Any = None,
        timeout: Any = None,
        allow_redirects: bool = True,
        proxies: Any = None,
        hooks: Any = None,
        stream: Any = None,
        verify: Any = None,
        cert: Any = None,
        json: Any = None,
    ) -> Any:
        active_session = _SESSION_PROVIDER() if _SESSION_PROVIDER is not None else None
        if active_session is not None and getattr(active_session, "auto_patch", True):
            merged_headers = dict(getattr(self, "headers", {}) or {})
            if headers:
                merged_headers.update(headers)
            httpx_req = _build_httpx_request(
                method,
                url,
                params=params,
                data=data,
                headers=merged_headers,
                json=json,
            )
            httpx_resp = active_session.transport.handle_request(httpx_req)
            return _to_requests_response(httpx_resp, str(httpx_req.url))

        return _ORIGINAL_SESSION_REQUEST(
            self,
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
        )

    requests.Session.request = _patched_request  # type: ignore[method-assign, assignment]


def uninstall_requests_patch() -> None:
    """Restore original ``requests.Session.request`` if patched."""
    global _ORIGINAL_SESSION_REQUEST, _SESSION_PROVIDER
    if _ORIGINAL_SESSION_REQUEST is None:
        return
    try:
        import requests

        requests.Session.request = _ORIGINAL_SESSION_REQUEST  # type: ignore[method-assign]
    except ImportError:
        pass
    _ORIGINAL_SESSION_REQUEST = None
    _SESSION_PROVIDER = None
