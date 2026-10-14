"""Synchronous HTTPX transport for buffered and SSE cassette recording and replay."""

from __future__ import annotations

import httpx
from typing import Literal
from collections.abc import Iterator
from pathlib import Path
from rerunner.cassette import Cassette, CassetteError
from rerunner.matcher import (
    compute_request_key,
    normalize_body,
    normalize_headers,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.sanitizer import sanitize_headers, sanitize_string
from time import sleep


def _is_event_stream(headers: httpx.Headers) -> bool:
    """Return whether headers describe a server-sent event stream."""
    content_type = str(headers.get("content-type", ""))
    media_type = content_type.partition(";")[0].strip().lower()
    return media_type == "text/event-stream"


class _ReplayByteStream(httpx.SyncByteStream):
    """Replay recorded response chunks through HTTPX's synchronous stream API."""

    def __init__(self, chunks: list[bytes], chunk_delay_ms: int = 0) -> None:
        self.chunks = chunks
        self.chunk_delay_seconds = chunk_delay_ms / 1000

    def __iter__(self) -> Iterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index > 0 and self.chunk_delay_seconds:
                sleep(self.chunk_delay_seconds)
            yield chunk


class CassetteTransport(httpx.BaseTransport):
    """Record or replay synchronous HTTP traffic, including chunked SSE responses."""

    def __init__(
        self,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        real_transport: httpx.BaseTransport | None = None,
        chunk_delay_ms: int = 0,
    ) -> None:
        self.cassette_path = Path(cassette_path)
        self.mode = mode
        self.fork_step = fork_step
        self.real_transport = real_transport or httpx.HTTPTransport()
        self.current_step = 0

        if self.mode in ("replay", "fork") and self.cassette_path.exists():
            self.cassette = Cassette.load(self.cassette_path)
        else:
            self.cassette = Cassette(self.cassette_path)

        if chunk_delay_ms < 0:
            raise ValueError("chunk_delay_ms must be non-negative")

        self.chunk_delay_ms = chunk_delay_ms

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.current_step += 1
        body_bytes = request.read()
        request_key = compute_request_key(request.method, str(request.url), body_bytes)

        # Decide whether to replay from cassette or hit live network
        should_replay = self.mode == "replay" or (
            self.mode == "fork"
            and self.fork_step is not None
            and self.current_step <= self.fork_step
        )

        if should_replay:
            match = self.cassette.find_http_match(request_key)
            if match is None or match.response is None:
                raise CassetteError(
                    f"[Step {self.current_step}] No cassette match found in replay mode for "
                    f"{request.method} {request.url} (key: {request_key[:12]}...)"
                )

            # Replay streaming chunks if response was recorded as stream
            if match.response.is_streaming:
                return httpx.Response(
                    status_code=match.response.status_code,
                    headers=match.response.headers,
                    stream=_ReplayByteStream(
                        [chunk.encode("utf-8") for chunk in match.response.chunks],
                        chunk_delay_ms=self.chunk_delay_ms,
                    ),
                    request=request,
                )

            # Standard buffered response replay
            return httpx.Response(
                status_code=match.response.status_code,
                headers=match.response.headers,
                content=match.response.body.encode("utf-8"),
                request=request,
            )

        # LIVE EXECUTION (Record or Fork after fork_step)
        real_response = self.real_transport.handle_request(request)

        is_streaming = _is_event_stream(real_response.headers)

        if is_streaming:
            response_chunks = list(real_response.iter_raw())
            response_bytes = b"".join(response_chunks)
        else:
            response_chunks = []
            response_bytes = real_response.read()

        # Sanitize headers and body before writing to disk
        cleaned_headers = sanitize_headers(normalize_headers(dict(request.headers)))
        cleaned_req_body = sanitize_string(normalize_body(body_bytes))
        cleaned_resp_body = sanitize_string(response_bytes.decode("utf-8", errors="replace"))

        cleaned_chunks = [
            sanitize_string(chunk.decode("utf-8", errors="replace")) for chunk in response_chunks
        ]

        recorded_req = RecordedRequest(
            method=request.method,
            url=str(request.url),
            headers=cleaned_headers,
            body=cleaned_req_body,
            request_key=request_key,
        )

        recorded_resp = RecordedResponse(
            status_code=real_response.status_code,
            headers=sanitize_headers(dict(real_response.headers)),
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

        # Re-wrap response so caller can read it cleanly
        if is_streaming:
            return httpx.Response(
                status_code=real_response.status_code,
                headers=real_response.headers,
                stream=_ReplayByteStream(response_chunks),
                request=request,
            )

        return httpx.Response(
            status_code=real_response.status_code,
            headers=real_response.headers,
            content=response_bytes,
            request=request,
        )

    def close(self) -> None:
        if hasattr(self.real_transport, "close"):
            self.real_transport.close()
