"""Tests for Rerunner's stdio MCP JSON-RPC 2.0 server and cassette tools."""

from __future__ import annotations

import ast
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from rerunner.cassette import Cassette
from rerunner.mcp_server import (
    JSONRPC_INVALID_PARAMS,
    JSONRPC_INVALID_REQUEST,
    JSONRPC_METHOD_NOT_FOUND,
    JSONRPC_PARSE_ERROR,
    TOOL_DEFINITIONS,
    handle_jsonrpc_message,
    serve_stdio,
)
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse


def _build_sample_cassette(
    path: Path,
    *,
    include_secret: bool = False,
    second_prompt: str = "Explain deterministic replay",
) -> Path:
    cassette = Cassette(path)
    api_key = (
        "Bearer sk-proj-supersecret1234567890abcdef" if include_secret else "Bearer [REDACTED]"
    )
    cassette.append_entry(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={"authorization": api_key, "content-type": "application/json"},
                body=json.dumps(
                    {"model": "gpt-4o", "messages": [{"role": "user", "content": second_prompt}]}
                ),
                request_key="req_1",
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {
                        "id": "chatcmpl-1",
                        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                        "usage": {
                            "prompt_tokens": 120,
                            "completion_tokens": 30,
                            "total_tokens": 150,
                        },
                    }
                ),
            ),
        )
    )
    cassette.append_entry(
        CassetteEntry(
            step=2,
            entry_type="side_effect",
            side_effect_name="lookup_order",
            side_effect_args=["ORD-42"],
            side_effect_kwargs={"verbose": True},
            side_effect_result={"status": "shipped"},
        )
    )
    cassette.append_entry(
        CassetteEntry(
            step=3,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {"model": "gpt-4o", "messages": [{"role": "user", "content": "summarize"}]}
                ),
                request_key="req_3",
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=json.dumps(
                    {"usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}}
                ),
            ),
        )
    )
    cassette.save()
    return path


def _call_tool(
    name: str, arguments: dict[str, Any], req_id: int = 1
) -> tuple[dict[str, Any], bool]:
    resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    assert resp is not None
    result = resp["result"]
    payload = json.loads(result["content"][0]["text"])
    return payload, bool(result["isError"])


def test_mcp_initialize_ping_and_tools_list() -> None:
    init_resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert init_resp is not None
    assert init_resp["result"]["protocolVersion"] == "2024-11-05"
    assert init_resp["result"]["serverInfo"]["name"] == "rerunner"
    assert "tools" in init_resp["result"]["capabilities"]

    # Fallback on unsupported protocol version
    fallback_resp = handle_jsonrpc_message(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "1999-01-01"},
        }
    )
    assert fallback_resp is not None
    assert fallback_resp["result"]["protocolVersion"] == "2025-03-26"

    # Notifications emit nothing
    assert handle_jsonrpc_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None

    ping_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert ping_resp == {"jsonrpc": "2.0", "id": 3, "result": {}}

    list_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    assert list_resp is not None
    listed = list_resp["result"]["tools"]
    assert len(listed) == 8
    assert {t["name"] for t in listed} == {t["name"] for t in TOOL_DEFINITIONS}


def test_mcp_error_codes() -> None:
    bad_req = handle_jsonrpc_message({"id": 1, "method": "ping"})
    assert bad_req is not None and bad_req["error"]["code"] == JSONRPC_INVALID_REQUEST

    missing_method = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "no/such"})
    assert missing_method is not None
    assert missing_method["error"]["code"] == JSONRPC_METHOD_NOT_FOUND

    unknown_tool = handle_jsonrpc_message(
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "bogus"}}
    )
    assert unknown_tool is not None
    assert unknown_tool["error"]["code"] == JSONRPC_INVALID_PARAMS


def test_mcp_stdio_newline_and_content_length_framing() -> None:
    newline_msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode("utf-8") + b"\n"
    cl_body = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode("utf-8")
    cl_msg = f"Content-Length: {len(cl_body)}\r\n\r\n".encode("ascii") + cl_body
    bad_json = b"{not valid json\n"

    stdin_buf = io.BytesIO(newline_msg + cl_msg + bad_json)
    stdout_buf = io.BytesIO()
    serve_stdio(stdin=stdin_buf, stdout=stdout_buf)

    lines = [
        json.loads(line) for line in stdout_buf.getvalue().decode("utf-8").splitlines() if line
    ]
    assert len(lines) == 3
    assert lines[0] == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert lines[1]["id"] == 2 and len(lines[1]["result"]["tools"]) == 8
    assert lines[2]["error"]["code"] == JSONRPC_PARSE_ERROR


def test_mcp_inspect_and_read_step(tmp_path: Path) -> None:
    cassette_path = _build_sample_cassette(tmp_path / "agent.jsonl")

    summary, is_err = _call_tool(
        "inspect_cassette",
        {"cassette_path": str(cassette_path), "limit": 2, "offset": 0},
    )
    assert not is_err
    assert summary["total_entries"] == 3
    assert summary["has_more"] is True
    assert [s["step"] for s in summary["steps"]] == [1, 2]

    http_only, is_err = _call_tool(
        "inspect_cassette",
        {"cassette_path": str(cassette_path), "entry_type": "http"},
    )
    assert not is_err
    assert http_only["filtered_entries"] == 2
    assert [s["step"] for s in http_only["steps"]] == [1, 3]

    step1, is_err = _call_tool(
        "read_cassette_step",
        {"cassette_path": str(cassette_path), "step": 1, "max_body_chars": 20},
    )
    assert not is_err
    assert step1["request"]["method"] == "POST"
    assert step1["request"]["body"]["truncated"] is True
    assert step1["response"]["tokens"]["total"] == 150

    step2, is_err = _call_tool(
        "read_cassette_step",
        {"cassette_path": str(cassette_path), "step": 2},
    )
    assert not is_err
    assert step2["side_effect"]["name"] == "lookup_order"
    assert step2["side_effect"]["result"] == {"status": "shipped"}

    missing, is_err = _call_tool(
        "read_cassette_step",
        {"cassette_path": str(cassette_path), "step": 99},
    )
    assert is_err
    assert "99" in missing["error"]


def test_mcp_verify_scrub_diff_fork_scaffold_and_savings(tmp_path: Path) -> None:
    leaky = _build_sample_cassette(tmp_path / "leaky.jsonl", include_secret=True)
    clean_a = _build_sample_cassette(
        tmp_path / "baseline.jsonl",
        include_secret=False,
        second_prompt="Explain deterministic replay",
    )
    clean_b = _build_sample_cassette(
        tmp_path / "candidate.jsonl", include_secret=False, second_prompt="Modified prompt"
    )

    verify_leaky, is_err = _call_tool(
        "verify_cassette", {"cassette_path": str(leaky), "strict_security": True}
    )
    assert not is_err
    assert verify_leaky["integrity_valid"] is True
    assert verify_leaky["security_passed"] is False
    assert verify_leaky["valid"] is False
    assert verify_leaky["leaks"]

    scrub_dry, is_err = _call_tool("scrub_cassette", {"cassette_path": str(leaky), "dry_run": True})
    assert not is_err and scrub_dry["dry_run"] is True and scrub_dry["initial_leaks"]

    scrub_real, is_err = _call_tool("scrub_cassette", {"cassette_path": str(leaky)})
    assert not is_err and scrub_real["remaining_leaks"] == []

    verify_after, is_err = _call_tool("verify_cassette", {"cassette_path": str(leaky)})
    assert not is_err
    assert verify_after["valid"] is True
    assert verify_after["integrity_valid"] is True
    assert verify_after["leaks"] == []

    diff_res, is_err = _call_tool(
        "diff_cassettes",
        {"baseline_path": str(clean_a), "candidate_path": str(clean_b)},
    )
    assert not is_err
    assert diff_res["has_drift"] is True
    assert diff_res["prompt_diffs"] == 1

    fork_res, is_err = _call_tool(
        "fork_and_replay_step", {"cassette_path": str(clean_b), "step": 2}
    )
    assert not is_err
    forked_path = Path(fork_res["forked_cassette"])
    assert forked_path.exists()
    assert fork_res["retained_steps"] == 2
    assert fork_res["truncated_steps"] == 1
    assert len(Cassette.load(clean_b, verify_integrity=False).entries) == 3

    scaffold, is_err = _call_tool(
        "scaffold_pytest_regression",
        {"cassette_path": str(clean_b), "test_name": "agent_checkout"},
    )
    assert not is_err
    assert scaffold["test_name"] == "test_agent_checkout"
    ast.parse(scaffold["pytest_code"])

    savings, is_err = _call_tool("estimate_savings", {"target_path": str(tmp_path)})
    assert not is_err
    assert savings["cassettes_analyzed"] == 4
    assert savings["total_steps"] == 11


@pytest.mark.parametrize("cmd_args", [["-m", "rerunner.cli", "mcp"]])
def test_cli_mcp_subprocess_smoke(cmd_args: list[str]) -> None:
    payload = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, *cmd_args],
        input=payload,
        text=True,
        capture_output=True,
        timeout=15,
        check=True,
    )
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["result"]["serverInfo"]["name"] == "rerunner"
    assert len(lines[1]["result"]["tools"]) == 8
