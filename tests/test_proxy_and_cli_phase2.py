"""Tests for Phase 2: `rerunner serve` proxy, `cost --json`, `inspect` filters, and HTML trace export."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx
from typer.testing import CliRunner
from rerunner.cassette import Cassette
from rerunner.cli import app
from rerunner.matcher import compute_request_key
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.proxy_server import RerunnerProxyServer

runner = CliRunner()


def _create_proxy_cassette(path: Path) -> Path:
    cassette = Cassette(path)

    body_1 = json.dumps({"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    url_1 = "https://api.openai.com/v1/chat/completions"
    cassette.append_entry(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url=url_1,
                headers={"content-type": "application/json"},
                body=body_1,
                request_key=compute_request_key("POST", url_1, body_1),
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "id": "chatcmpl-proxy",
                        "choices": [
                            {"message": {"role": "assistant", "content": "hello from proxy"}}
                        ],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    }
                ),
            ),
        )
    )

    body_2 = json.dumps({"model": "gpt-4o", "stream": True})
    cassette.append_entry(
        CassetteEntry(
            step=2,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url=url_1,
                headers={"content-type": "application/json"},
                body=body_2,
                request_key=compute_request_key("POST", url_1, body_2),
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "text/event-stream"},
                is_streaming=True,
                chunks=[
                    'data: {"delta":"hello"}\n\n',
                    "data: [DONE]\n\n",
                ],
                chunk_delays_ms=[1.0, 1.0],
            ),
        )
    )

    cassette.append_entry(
        CassetteEntry(
            step=3,
            entry_type="side_effect",
            side_effect_name="db_lookup",
            side_effect_args=["<script>alert(1)</script>"],
            side_effect_result={"ok": True},
        )
    )
    cassette.save()
    return path


def test_proxy_server_replay_json_sse_health_and_miss(tmp_path: Path) -> None:
    cassette_path = _create_proxy_cassette(tmp_path / "proxy.jsonl")
    server = RerunnerProxyServer(cassette_path, port=0, mode="replay").start_in_thread()
    try:
        health = httpx.get(f"{server.base_url}/__rerunner/health", timeout=5.0)
        assert health.status_code == 200
        assert health.json()["mode"] == "replay"
        assert health.json()["steps"] == 3

        # Relative OPENAI_BASE_URL style request matches recorded https://api.openai.com/v1/chat/completions
        resp1 = httpx.post(
            f"{server.base_url}/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
            timeout=5.0,
        )
        assert resp1.status_code == 200
        assert resp1.json()["choices"][0]["message"]["content"] == "hello from proxy"

        # SSE streaming replay
        with httpx.stream(
            "POST",
            f"{server.base_url}/v1/chat/completions",
            json={"model": "gpt-4o", "stream": True},
            timeout=5.0,
        ) as stream_resp:
            assert stream_resp.status_code == 200
            stream_body = "".join(stream_resp.iter_text())
        assert 'data: {"delta":"hello"}' in stream_body
        assert "data: [DONE]" in stream_body

        # Replay miss fails closed with 502
        miss = httpx.post(
            f"{server.base_url}/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "unrecorded"}]},
            timeout=5.0,
        )
        assert miss.status_code == 502
        assert "replay miss" in miss.json()["error"].lower()
    finally:
        server.shutdown()


def test_proxy_server_record_mode_scrubs_and_persists(tmp_path: Path) -> None:
    class _MockUpstream(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            _ = self.rfile.read(length)
            payload = json.dumps({"ok": True, "echo_path": self.path}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _MockUpstream)
    upstream_port = int(upstream.server_address[1])
    t = threading.Thread(target=upstream.serve_forever, daemon=True)
    t.start()

    rec_path = tmp_path / "recorded_proxy.jsonl"
    proxy = RerunnerProxyServer(
        rec_path,
        port=0,
        mode="record",
        upstream_url=f"http://127.0.0.1:{upstream_port}",
    ).start_in_thread()
    try:
        r = httpx.post(
            f"{proxy.base_url}/v1/messages",
            headers={"Authorization": "Bearer sk-proj-topsecret1234567890abcdef"},
            json={"prompt": "ping"},
            timeout=5.0,
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True, "echo_path": "/v1/messages"}
    finally:
        proxy.shutdown()
        upstream.shutdown()
        upstream.server_close()

    loaded = Cassette.load(rec_path, verify_integrity=True)
    assert len(loaded.entries) == 1
    req = loaded.entries[0].request
    assert req is not None
    assert req.headers["authorization"] == "[REDACTED]"


def test_cli_cost_json_and_inspect_filters_and_html_trace(tmp_path: Path) -> None:
    cassette_path = _create_proxy_cassette(tmp_path / "trace.jsonl")

    cost_res = runner.invoke(app, ["cost", str(cassette_path), "--json"])
    assert cost_res.exit_code == 0
    cost_data = json.loads(cost_res.output)
    assert cost_data["cassette_files"] == 1
    assert cost_data["total_steps"] == 3
    assert cost_data["total_http"] == 2
    assert cost_data["total_tools"] == 1
    assert cost_data["total_tokens"] == 15

    trace_html = tmp_path / "trace.html"
    inspect_res = runner.invoke(
        app,
        [
            "inspect",
            str(cassette_path),
            "--limit",
            "1",
            "--entry-type",
            "http",
            "--export-html",
            str(trace_html),
        ],
    )
    assert inspect_res.exit_code == 0
    assert "offset=0" in inspect_res.output
    assert trace_html.exists()
    html_text = trace_html.read_text(encoding="utf-8")
    assert "Rerunner Flight Trace" in html_text
    assert "SHA-256 Verified" in html_text
    # Ensure HTML escaping neutralizes raw <script> tag from side-effect payload
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
