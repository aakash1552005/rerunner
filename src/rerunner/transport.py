"""Synchronous HTTPX transport for buffered and SSE cassette recording and replay."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
import threading
import time
from typing import Literal


import httpx

from rerunner.cassette import Cassette, CassetteError
from rerunner.matcher import (
    MatchingStrategy,
    compute_request_key,
    normalize_body,
    normalize_headers,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.sanitizer import (
    PiiRedactor,
    sanitize_body,
    sanitize_headers,
    sanitize_string,
    sanitize_url,
)


def _is_event_stream(headers: httpx.Headers) -> bool:
    """Return whether headers describe a server-sent event stream."""
    content_type = str(headers.get("content-type", ""))
    media_type = content_type.partition(";")[0].strip().lower()
    return media_type == "text/event-stream"


class _ReplayByteStream(httpx.SyncByteStream):
    """Replay recorded response chunks through HTTPX's synchronous stream API."""

    def __init__(
        self,
        chunks: list[bytes],
        chunk_delay_ms: int = 0,
        chunk_delays_ms: list[float] | None = None,
    ) -> None:
        self.chunks = chunks
        self.chunk_delay_seconds = chunk_delay_ms / 1000 if chunk_delay_ms > 0 else 0.0
        self.chunk_delays_ms = chunk_delays_ms or []

    def __iter__(self) -> Iterator[bytes]:
        for index, chunk in enumerate(self.chunks):
            if index > 0:
                if self.chunk_delay_seconds > 0:
                    time.sleep(self.chunk_delay_seconds)
                elif index < len(self.chunk_delays_ms) and self.chunk_delays_ms[index] > 0:
                    time.sleep(self.chunk_delays_ms[index] / 1000.0)
            yield chunk


class _RecordingSyncByteStream(httpx.SyncByteStream):
    """Pass-through recording byte stream that yields chunks lazily as consumed,

    records per-chunk arrival delays, and persists to the active Cassette upon clean close().
    """

    def __init__(
        self,
        real_response: httpx.Response,
        request: httpx.Request,
        step: int,
        cassette: Cassette,
        request_key: str,
        body_bytes: bytes,
        record_partial_streams: bool = False,
        pii_redactor: PiiRedactor | None = None,
    ) -> None:
        self.real_response = real_response
        self.request = request
        self.step = step
        self.cassette = cassette
        self.request_key = request_key
        self.body_bytes = body_bytes
        self.record_partial_streams = record_partial_streams
        self.pii_redactor = pii_redactor
        self.chunks: list[bytes] = []
        self.chunk_delays_ms: list[float] = []
        self._last_chunk_time: float | None = None
        self._had_exception = False
        self._stream_completed = False
        self._finalized = False

    def __iter__(self) -> Iterator[bytes]:
        self._last_chunk_time = time.perf_counter()
        try:
            for chunk in self.real_response.iter_raw():
                now = time.perf_counter()
                delay_ms = (
                    (now - self._last_chunk_time) * 1000.0
                    if self._last_chunk_time is not None
                    else 0.0
                )
                self._last_chunk_time = now
                self.chunks.append(chunk)
                self.chunk_delays_ms.append(round(delay_ms, 2))
                if b"data: [DONE]" in chunk:
                    self._stream_completed = True
                yield chunk
            self._stream_completed = True
        except GeneratorExit:
            pass
        except Exception:
            self._had_exception = True
            raise
        finally:
            if (self._stream_completed and not self._had_exception) or self.record_partial_streams:
                self._finalize()

    def close(self) -> None:
        try:
            self.real_response.close()
        finally:
            if (self._stream_completed and not self._had_exception) or self.record_partial_streams:
                self._finalize()

    def __del__(self) -> None:
        if (self._stream_completed and not self._had_exception) or self.record_partial_streams:
            self._finalize()

    def _finalize(self) -> None:
        if self._finalized:
            return
        self._finalized = True

        if (
            not (self._stream_completed and not self._had_exception)
            and not self.record_partial_streams
        ):
            return

        response_bytes = b"".join(self.chunks)
        cleaned_headers = sanitize_headers(
            normalize_headers(dict(self.request.headers)), pii_redactor=self.pii_redactor
        )
        cleaned_url = sanitize_url(str(self.request.url), pii_redactor=self.pii_redactor)
        cleaned_req_body = sanitize_body(
            normalize_body(self.body_bytes), pii_redactor=self.pii_redactor
        )
        cleaned_resp_body = sanitize_body(
            response_bytes.decode("utf-8", errors="replace"), pii_redactor=self.pii_redactor
        )

        cleaned_chunks = [
            sanitize_string(chunk.decode("utf-8", errors="replace"), pii_redactor=self.pii_redactor)
            for chunk in self.chunks
        ]

        cleaned_resp_headers = sanitize_headers(
            dict(self.real_response.headers), pii_redactor=self.pii_redactor
        )
        cleaned_resp_headers.pop("content-encoding", None)
        cleaned_resp_headers.pop("content-length", None)

        recorded_req = RecordedRequest(
            method=self.request.method,
            url=cleaned_url,
            headers=cleaned_headers,
            body=cleaned_req_body,
            request_key=self.request_key,
        )

        recorded_resp = RecordedResponse(
            status_code=self.real_response.status_code,
            headers=cleaned_resp_headers,
            body=cleaned_resp_body,
            chunks=cleaned_chunks,
            chunk_delays_ms=self.chunk_delays_ms,
            is_streaming=True,
            http_version=self.real_response.extensions.get("http_version", b"HTTP/1.1").decode(
                "ascii", errors="ignore"
            ),
        )

        entry = CassetteEntry(
            step=self.step,
            entry_type="http",
            request=recorded_req,
            response=recorded_resp,
        )
        self.cassette.append(entry)
        self.cassette.save()


class CassetteTransport(httpx.BaseTransport):
    """Record or replay synchronous HTTP traffic, including chunked SSE responses."""

    def __init__(
        self,
        cassette_path: Path | str,
        mode: Literal["record", "replay", "fork"] = "replay",
        fork_step: int | None = None,
        real_transport: httpx.BaseTransport | None = None,
        chunk_delay_ms: int = 0,
        record_partial_streams: bool = False,
        matching_strategy: MatchingStrategy = "strict",
        cassette: Cassette | None = None,
        pii_redactor: PiiRedactor | None = None,
        semantic_threshold: float = 0.80,
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        if chunk_delay_ms < 0:
            raise ValueError("chunk_delay_ms must be non-negative")

        self.cassette_path = Path(cassette_path)
        self.mode = mode
        self.fork_step = fork_step
        self.real_transport = real_transport or httpx.HTTPTransport()
        self.chunk_delay_ms = chunk_delay_ms
        self.record_partial_streams = record_partial_streams
        self.matching_strategy = matching_strategy
        self.pii_redactor = pii_redactor
        self.semantic_threshold = semantic_threshold
        self.embedding_fn = embedding_fn
        self._step_lock = threading.Lock()
        self._step_counter = 0
        self._active_recording_streams: list[_RecordingSyncByteStream] = []

        if cassette is not None:
            self.cassette = cassette
        elif self.mode in ("replay", "fork") and self.cassette_path.exists():
            self.cassette = Cassette.load(self.cassette_path)
            if self.mode == "fork" and self.fork_step is not None:
                self.cassette.truncate_after_step(self.fork_step)
        else:
            self.cassette = Cassette(self.cassette_path)

    @property
    def current_step(self) -> int:
        """Current step index tracked on this transport instance."""
        with self._step_lock:
            return self._step_counter

    def next_step(self) -> int:
        """Atomically increment and return the next step index."""
        with self._step_lock:
            self._step_counter += 1
            return self._step_counter

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        current_step = self.next_step()
        body_bytes = request.read()
        request_key = compute_request_key(
            request.method, str(request.url), body_bytes, strategy=self.matching_strategy
        )

        # Decide whether to replay from cassette or hit live network
        should_replay = self.mode == "replay" or (
            self.mode == "fork" and self.fork_step is not None and current_step <= self.fork_step
        )

        if should_replay:
            if not self.cassette_path.exists() and not self.cassette.entries:
                raise FileNotFoundError(
                    f"Cassette file not found in replay mode: {self.cassette_path}"
                )

            match = self.cassette.find_http_match(
                request_key,
                strategy=self.matching_strategy,
                incoming_method=request.method,
                incoming_url=str(request.url),
                incoming_body=body_bytes,
                semantic_threshold=self.semantic_threshold,
                embedding_fn=self.embedding_fn,
            )
            if match is None or match.response is None:
                raise CassetteError(
                    f"[Step {current_step}] No cassette match found in replay mode for "
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
                        chunk_delays_ms=match.response.chunk_delays_ms,
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

        live_return_headers = dict(real_response.headers)
        live_return_headers.pop("content-encoding", None)
        live_return_headers.pop("content-length", None)

        if is_streaming:
            stream = _RecordingSyncByteStream(
                real_response=real_response,
                request=request,
                step=current_step,
                cassette=self.cassette,
                request_key=request_key,
                body_bytes=body_bytes,
                record_partial_streams=self.record_partial_streams,
                pii_redactor=self.pii_redactor,
            )
            self._active_recording_streams.append(stream)
            return httpx.Response(
                status_code=real_response.status_code,
                headers=live_return_headers,
                stream=stream,
                request=request,
            )

        response_bytes = real_response.read()

        # Sanitize headers, url, and body before writing to disk
        cleaned_headers = sanitize_headers(
            normalize_headers(dict(request.headers)), pii_redactor=self.pii_redactor
        )
        cleaned_url = sanitize_url(str(request.url), pii_redactor=self.pii_redactor)
        cleaned_req_body = sanitize_body(normalize_body(body_bytes), pii_redactor=self.pii_redactor)
        cleaned_resp_body = sanitize_body(
            response_bytes.decode("utf-8", errors="replace"), pii_redactor=self.pii_redactor
        )

        cleaned_resp_headers = sanitize_headers(
            dict(real_response.headers), pii_redactor=self.pii_redactor
        )
        cleaned_resp_headers.pop("content-encoding", None)
        cleaned_resp_headers.pop("content-length", None)

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
            chunks=[],
            is_streaming=False,
            http_version=real_response.extensions.get("http_version", b"HTTP/1.1").decode(
                "ascii", errors="ignore"
            ),
        )

        entry = CassetteEntry(
            step=current_step,
            entry_type="http",
            request=recorded_req,
            response=recorded_resp,
        )
        self.cassette.append(entry)
        self.cassette.save()

        return httpx.Response(
            status_code=real_response.status_code,
            headers=live_return_headers,
            content=response_bytes,
            request=request,
        )

    def close(self) -> None:
        for stream in self._active_recording_streams:
            stream.close()
        if hasattr(self.real_transport, "close"):
            self.real_transport.close()
