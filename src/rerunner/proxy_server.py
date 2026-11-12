"""Cross-language HTTP/SSE replay & record proxy server (`rerunner serve`)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from rerunner.cassette import Cassette
from rerunner.matcher import MatchingStrategy, compute_request_key
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.sanitizer import (
    sanitize_body,
    sanitize_chunks,
    sanitize_headers,
    sanitize_url,
)
from rerunner.storage import cassette_exists

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
}


class ProxyReplayConfig:
    """Thread-safe shared state for ``RerunnerProxyServer``."""

    def __init__(
        self,
        cassette_path: Path | str,
        *,
        mode: str = "replay",
        upstream_url: str | None = None,
        matching_strategy: MatchingStrategy = "strict",
        simulate_latency: bool = False,
        verify_integrity: bool = False,
    ) -> None:
        if mode not in ("replay", "record", "auto"):
            raise ValueError("mode must be one of: replay, record, auto")

        self.cassette_path = cassette_path
        self.mode = mode
        self.upstream_url = upstream_url.rstrip("/") if upstream_url else None
        self.matching_strategy = matching_strategy
        self.simulate_latency = simulate_latency
        self.lock = threading.Lock()

        exists = cassette_exists(cassette_path)
        if mode == "replay":
            if not exists:
                raise FileNotFoundError(f"Cassette not found for replay mode: {cassette_path}")
            self.cassette = Cassette.load(cassette_path, verify_integrity=verify_integrity)
            self.effective_mode = "replay"
        elif mode == "record":
            if not self.upstream_url:
                raise ValueError("--upstream is required when running in record mode.")
            self.cassette = Cassette(cassette_path)
            self.effective_mode = "record"
        else:
            if exists:
                self.cassette = Cassette.load(cassette_path, verify_integrity=verify_integrity)
                self.effective_mode = "replay"
            else:
                if not self.upstream_url:
                    raise ValueError(
                        f"Cassette '{cassette_path}' does not exist and --upstream is not set."
                    )
                self.cassette = Cassette(cassette_path)
                self.effective_mode = "record"

    def resolve_target_url(self, request_path: str) -> str:
        """Build full upstream URL from incoming proxy request path."""
        if request_path.startswith(("http://", "https://")):
            return request_path
        if self.upstream_url:
            if request_path.startswith("/"):
                return f"{self.upstream_url}{request_path}"
            return f"{self.upstream_url}/{request_path}"
        return request_path

    def find_replay_match(
        self,
        method: str,
        request_path: str,
        body: bytes,
    ) -> CassetteEntry | None:
        """Match an incoming proxy HTTP request against recorded cassette entries."""
        target_url = self.resolve_target_url(request_path)
        req_key = compute_request_key(method, target_url, body, strategy=self.matching_strategy)
        entry = self.cassette.find_http_match(
            req_key,
            strategy=self.matching_strategy,
            incoming_method=method,
            incoming_url=target_url,
            incoming_body=body,
        )
        if entry is not None:
            return entry

        # Allow OPENAI_BASE_URL=http://127.0.0.1:PORT/v1 style relative paths without --upstream
        if not request_path.startswith(("http://", "https://")):
            incoming_path = urlparse(request_path).path
            candidate_urls: list[str] = []
            seen: set[str] = set()
            for recorded in self.cassette.entries:
                if (
                    recorded.entry_type == "http"
                    and recorded.request
                    and recorded.request.method.upper() == method.upper()
                    and urlparse(recorded.request.url).path == incoming_path
                    and recorded.request.url not in seen
                ):
                    seen.add(recorded.request.url)
                    candidate_urls.append(recorded.request.url)

            for rec_url in candidate_urls:
                alt_key = compute_request_key(
                    method, rec_url, body, strategy=self.matching_strategy
                )
                entry = self.cassette.find_http_match(
                    alt_key,
                    strategy=self.matching_strategy,
                    incoming_method=method,
                    incoming_url=rec_url,
                    incoming_body=body,
                )
                if entry is not None:
                    return entry
        return None


def _make_handler(config: ProxyReplayConfig) -> type[BaseHTTPRequestHandler]:
    class _RerunnerProxyHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_request_body(self) -> bytes:
            raw_len = self.headers.get("Content-Length")
            if not raw_len:
                return b""
            try:
                length = max(0, int(raw_len))
            except ValueError:
                return b""
            return self.rfile.read(length) if length > 0 else b""

        def _write_json_error(self, status_code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_recorded_response(self, recorded: RecordedResponse) -> None:
            self.send_response(recorded.status_code)
            has_ct = False
            for k, v in recorded.headers.items():
                if k.lower() in HOP_BY_HOP_HEADERS:
                    continue
                if k.lower() == "content-type":
                    has_ct = True
                self.send_header(k, v)

            if recorded.is_streaming and recorded.chunks:
                if not has_ct:
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                for idx, chunk in enumerate(recorded.chunks):
                    if config.simulate_latency and idx < len(recorded.chunk_delays_ms):
                        delay = recorded.chunk_delays_ms[idx]
                        if delay > 0:
                            time.sleep(delay / 1000.0)
                    self.wfile.write(chunk.encode("utf-8"))
                    self.wfile.flush()
                self.close_connection = True
                return

            payload = recorded.body.encode("utf-8")
            if not has_ct:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _handle_live_record(self, method: str, req_body: bytes) -> None:
            target_url = config.resolve_target_url(self.path)
            fwd_headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in ("host", "content-length", "connection")
            }
            with httpx.Client(timeout=60.0) as client:
                upstream_resp = client.request(
                    method=method,
                    url=target_url,
                    headers=fwd_headers,
                    content=req_body,
                )

            raw_resp_headers = {k.lower(): v for k, v in upstream_resp.headers.items()}
            is_sse = "text/event-stream" in raw_resp_headers.get("content-type", "").lower()
            resp_text = upstream_resp.text
            chunks = (
                [line + "\n" for line in resp_text.splitlines()] if is_sse and resp_text else []
            )

            req_key = compute_request_key(
                method, target_url, req_body, strategy=config.matching_strategy
            )
            recorded_req = RecordedRequest(
                method=method,
                url=sanitize_url(target_url),
                headers=sanitize_headers(dict(self.headers.items())),
                body=sanitize_body(req_body.decode("utf-8", errors="replace")),
                request_key=req_key,
            )
            recorded_resp = RecordedResponse(
                status_code=upstream_resp.status_code,
                headers=sanitize_headers(raw_resp_headers),
                body=sanitize_body(resp_text),
                chunks=sanitize_chunks(chunks) if chunks else [],
                is_streaming=is_sse,
            )
            with config.lock:
                step_num = config.cassette.next_step()
                config.cassette.append_entry(
                    CassetteEntry(
                        step=step_num,
                        entry_type="http",
                        request=recorded_req,
                        response=recorded_resp,
                    )
                )
                config.cassette.save()

            self._send_recorded_response(
                RecordedResponse(
                    status_code=upstream_resp.status_code,
                    headers=raw_resp_headers,
                    body=resp_text,
                    chunks=chunks,
                    is_streaming=is_sse,
                )
            )

        def _dispatch(self, method: str) -> None:
            if self.path == "/__rerunner/health":
                self._write_json_error(
                    200,
                    {
                        "status": "ok",
                        "mode": config.effective_mode,
                        "steps": len(config.cassette.entries),
                    },
                )
                return

            req_body = self._read_request_body()
            if config.effective_mode == "record":
                try:
                    self._handle_live_record(method, req_body)
                except Exception as exc:
                    self._write_json_error(502, {"error": f"Upstream proxy error: {exc}"})
                return

            entry = config.find_replay_match(method, self.path, req_body)
            if entry is None or entry.response is None:
                self._write_json_error(
                    502,
                    {
                        "error": "Rerunner replay miss: no matching recorded HTTP interaction found.",
                        "method": method,
                        "path": self.path,
                    },
                )
                return

            self._send_recorded_response(entry.response)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def do_PUT(self) -> None:
            self._dispatch("PUT")

        def do_PATCH(self) -> None:
            self._dispatch("PATCH")

        def do_DELETE(self) -> None:
            self._dispatch("DELETE")

    return _RerunnerProxyHandler


class RerunnerProxyServer:
    """Lifecycle wrapper around ``ThreadingHTTPServer`` for CLI and test usage."""

    def __init__(
        self,
        cassette_path: Path | str,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        mode: str = "replay",
        upstream_url: str | None = None,
        matching_strategy: MatchingStrategy = "strict",
        simulate_latency: bool = False,
    ) -> None:
        self.config = ProxyReplayConfig(
            cassette_path,
            mode=mode,
            upstream_url=upstream_url,
            matching_strategy=matching_strategy,
            simulate_latency=simulate_latency,
        )
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(self.config))
        self.host = host
        self.port = int(self._httpd.server_address[1])
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        """Return the base HTTP URL where the proxy is listening."""
        return f"http://{self.host}:{self.port}"

    def serve_forever(self) -> None:
        """Run the proxy server loop in the current thread until shutdown."""
        self._httpd.serve_forever()

    def start_in_thread(self) -> RerunnerProxyServer:
        """Start serving in a background daemon thread and return ``self``."""
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def shutdown(self) -> None:
        """Stop the server and close the listening socket cleanly."""
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
