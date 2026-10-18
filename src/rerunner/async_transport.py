"""Asynchronous HTTPX transport for buffered and SSE cassette recording and replay."""

from __future__ import annotations

from asyncio import sleep
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

import httpx

from rerunner.cassette import Cassette, CassetteError
from rerunner.matcher import (
    compute_request_key,
    normalize_body,
    normalize_headers,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.sanitizer import sanitize_body, sanitize_headers, sanitize_string, sanitize_url


def _is_event_stream(headers: httpx.Headers) -> bool:
    """Return whether headers describe a server-sent event stream."""
    content_type = str(headers.get("content-type", ""))
    media_type = content_type.partition(";")[0].strip().lower()
    return media_type == "text/event-stream"


class _AsyncReplayByteStream(httpx.AsyncByteStream):
    """Replay recorded response chunks through HTTPX's asynchronous stream API."""

    def __init__(self, chunks: list[bytes], chunk_delay_ms: int = 0) -> None:
        self.chunks = chunks
        self.chunk_delay_seconds = chunk_delay_ms / 1000

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index > 0 and self.chunk_delay_seconds:
                await sleep(self.chunk_delay_seconds)
            yield chunk


class AsyncCassetteTransport(httpx.AsyncBaseTransport):
    """Record or replay asynchronous HTTP traffic, including chunked SSE responses."""

    def __init__(
        self,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        real_transport: httpx.AsyncBaseTransport | None = None,
        chunk_delay_ms: int = 0,
    ) -> None:
        if chunk_delay_ms < 0:
            raise ValueError("chunk_delay_ms must be non-negative")

        self.cassette_path = Path(cassette_path)
        self.mode = mode
        self.fork_step = fork_step
        self.real_transport = real_transport or httpx.AsyncHTTPTransport()
        self.current_step = 0
        self.chunk_delay_ms = chunk_delay_ms

        if self.mode in ("replay", "fork") and self.cassette_path.exists():
            self.cassette = Cassette.load(self.cassette_path)
            if self.mode == "fork" and self.fork_step is not None:
                self.cassette.truncate_after_step(self.fork_step)
        else:
            self.cassette = Cassette(self.cassette_path)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.current_step += 1
        body_bytes = await request.aread()
        request_key = compute_request_key(request.method, str(request.url), body_bytes)

        # Check whether to replay
        should_replay = self.mode == "replay" or (
            self.mode == "fork"
            and self.fork_step is not None
            and self.current_step <= self.fork_step
        )

        if should_replay:
            if not self.cassette_path.exists() and not self.cassette.entries:
                raise FileNotFoundError(
                    f"Cassette file not found in replay mode: {self.cassette_path}"
                )

            match = self.cassette.find_http_match(request_key)
            if match is None or match.response is None:
                raise CassetteError(
                    f"[Async Step {self.current_step}] No cassette match found in replay mode for "
                    f"{request.method} {request.url} (key: {request_key[:12]}...)"
                )

            if match.response.is_streaming:
                return httpx.Response(
                    status_code=match.response.status_code,
                    headers=match.response.headers,
                    stream=_AsyncReplayByteStream(
                        [chunk.encode("utf-8") for chunk in match.response.chunks],
                        chunk_delay_ms=self.chunk_delay_ms,
                    ),
                    request=request,
                )

            return httpx.Response(
                status_code=match.response.status_code,
                headers=match.response.headers,
                content=match.response.body.encode("utf-8"),
                request=request,
            )

        # LIVE EXECUTION
        real_response = await self.real_transport.handle_async_request(request)

        is_streaming = _is_event_stream(real_response.headers)

        if is_streaming:
            response_chunks = [chunk async for chunk in real_response.aiter_raw()]
            response_bytes = b"".join(response_chunks)
        else:
            response_chunks = []
            response_bytes = await real_response.aread()

        # Sanitize headers, url, and body before writing to disk
        cleaned_headers = sanitize_headers(normalize_headers(dict(request.headers)))
        cleaned_url = sanitize_url(str(request.url))
        cleaned_req_body = sanitize_body(normalize_body(body_bytes))
        cleaned_resp_body = sanitize_body(response_bytes.decode("utf-8", errors="replace"))

        cleaned_chunks = [
            sanitize_string(chunk.decode("utf-8", errors="replace")) for chunk in response_chunks
        ]

        # Sanitize response headers and strip content-encoding/length to prevent decompression bugs on replay
        cleaned_resp_headers = sanitize_headers(dict(real_response.headers))
        cleaned_resp_headers.pop("content-encoding", None)
        cleaned_resp_headers.pop("content-length", None)

        # Record to cassette
        recorded_req = RecordedRequest(
            method=request.method,
            url=cleaned_url,
            headers=cleaned_headers,
            body=cleaned_req_body,
            request_key=request_key,
        )

        recorded_resp = RecordedResponse(
            status_code=real_response.status_code,
            headers=cleaned_resp_headers,
            body=cleaned_resp_body,
            chunks=cleaned_chunks,
            is_streaming=is_streaming,
            http_version=real_response.extensions.get("http_version", b"HTTP/1.1").decode(
                "ascii", errors="ignore"
            ),
        )

        entry = CassetteEntry(
            step=self.current_step,
            entry_type="http",
            request=recorded_req,
            response=recorded_resp,
        )
        self.cassette.append(entry)
        self.cassette.save()

        # Clean return headers for caller
        live_return_headers = dict(real_response.headers)
        live_return_headers.pop("content-encoding", None)
        live_return_headers.pop("content-length", None)

        if is_streaming:
            return httpx.Response(
                status_code=real_response.status_code,
                headers=live_return_headers,
                stream=_AsyncReplayByteStream(response_chunks),
                request=request,
            )

        return httpx.Response(
            status_code=real_response.status_code,
            headers=live_return_headers,
            content=response_bytes,
            request=request,
        )

    async def aclose(self) -> None:
        if hasattr(self.real_transport, "aclose"):
            await self.real_transport.aclose()
