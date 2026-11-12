"""Zero-dependency stdio MCP (Model Context Protocol) JSON-RPC 2.0 server for Rerunner."""

from __future__ import annotations

import importlib.metadata
import json
import sys
from collections.abc import Callable
from typing import Any, BinaryIO
from rerunner.cassette_ops import (
    diff_cassettes_report,
    estimate_savings_summary,
    fork_cassette_at_step,
    inspect_cassette_summary,
    read_cassette_step_detail,
    scaffold_pytest_regression_code,
    scrub_cassette_file,
    verify_cassette_report,
)

SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL_VERSION = "2025-03-26"

JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def get_rerunner_version() -> str:
    """Return installed package version or fallback string."""
    try:
        return importlib.metadata.version("rerunner")
    except importlib.metadata.PackageNotFoundError:
        return "0.3.1"


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "inspect_cassette",
        "description": (
            "Inspect a Rerunner cassette (.jsonl, .zst, .gz) and return metadata plus bounded "
            "step summaries without loading full HTTP bodies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Path or URI to the cassette file.",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 20,
                    "description": "Maximum number of steps to return.",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "default": 0,
                    "description": "Zero-based offset into the filtered step list.",
                },
                "entry_type": {
                    "type": "string",
                    "enum": ["http", "side_effect", "tool"],
                    "description": "Optional filter for HTTP or tool/side-effect steps.",
                },
            },
            "required": ["cassette_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_cassette_step",
        "description": (
            "Read detailed request, response, token usage, and side-effect payloads for a single "
            "recorded step number."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Path or URI to the cassette file.",
                },
                "step": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Recorded step number to inspect.",
                },
                "max_body_chars": {
                    "type": "integer",
                    "minimum": 100,
                    "default": 4000,
                    "description": "Maximum characters to include for HTTP request/response bodies.",
                },
            },
            "required": ["cassette_path", "step"],
            "additionalProperties": False,
        },
    },
    {
        "name": "diff_cassettes",
        "description": (
            "Compare a baseline cassette against a candidate cassette step-by-step and return "
            "structural drift, prompt changes, status changes, and token deltas."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "baseline_path": {
                    "type": "string",
                    "description": "Path to the baseline cassette file.",
                },
                "candidate_path": {
                    "type": "string",
                    "description": "Path to the candidate cassette file.",
                },
            },
            "required": ["baseline_path", "candidate_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fork_and_replay_step",
        "description": (
            "Truncate a cassette after a given step number and write a forked cassette ready for "
            "deterministic replay up to that point followed by live execution."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Source cassette path.",
                },
                "step": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Keep entries up to and including this step; truncate later steps.",
                },
                "output_path": {
                    "type": "string",
                    "description": (
                        "Destination path for the forked cassette. Defaults to a sibling "
                        "*.fork_step_<step> file so the source cassette is preserved."
                    ),
                },
            },
            "required": ["cassette_path", "step"],
            "additionalProperties": False,
        },
    },
    {
        "name": "scaffold_pytest_regression",
        "description": (
            "Generate a deterministic pytest regression test template bound to an existing cassette."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Path to the cassette to replay in the test.",
                },
                "test_name": {
                    "type": "string",
                    "default": "test_agent_regression",
                    "description": "Python test function name.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replay", "auto", "record"],
                    "default": "replay",
                    "description": "Rerunner session mode used in the generated test.",
                },
            },
            "required": ["cassette_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "verify_cassette",
        "description": (
            "Verify SHA-256 hash chaining, scan for leaked API keys or PII, and compute savings "
            "for a cassette."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Path or URI to the cassette file.",
                },
                "strict_security": {
                    "type": "boolean",
                    "default": True,
                    "description": "Treat unredacted secrets/PII as verification failure.",
                },
            },
            "required": ["cassette_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "scrub_cassette",
        "description": (
            "Scrub sensitive API keys and PII from a cassette and re-compute its SHA-256 hash chain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cassette_path": {
                    "type": "string",
                    "description": "Source cassette path.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional destination path. Overwrites source if omitted.",
                },
                "dry_run": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, simulate scrubbing without writing changes.",
                },
            },
            "required": ["cassette_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "estimate_savings",
        "description": (
            "Estimate total tokens, USD spend, and CI runtime saved across a cassette file or "
            "cassette directory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "default": "tests/cassettes",
                    "description": "Cassette file path or directory containing cassettes.",
                },
            },
            "additionalProperties": False,
        },
    },
]


def _require_str(args: dict[str, Any], key: str) -> str:
    val = args.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"Parameter '{key}' must be a non-empty string.")
    return val


def _optional_int(args: dict[str, Any], key: str, default: int) -> int:
    if key not in args or args[key] is None:
        return default
    val = args[key]
    if isinstance(val, bool) or not isinstance(val, int):
        raise ValueError(f"Parameter '{key}' must be an integer.")
    return val


def _handle_inspect_cassette(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    limit = _optional_int(args, "limit", 20)
    offset = _optional_int(args, "offset", 0)
    entry_type = args.get("entry_type")
    if entry_type is not None and not isinstance(entry_type, str):
        raise ValueError("Parameter 'entry_type' must be a string.")
    return inspect_cassette_summary(
        cassette_path,
        limit=limit,
        offset=offset,
        entry_type=entry_type,
    )


def _handle_read_cassette_step(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    step = args.get("step")
    if isinstance(step, bool) or not isinstance(step, int):
        raise ValueError("Parameter 'step' must be an integer.")
    max_body_chars = _optional_int(args, "max_body_chars", 4000)
    return read_cassette_step_detail(
        cassette_path,
        step,
        max_body_chars=max_body_chars,
    )


def _handle_diff_cassettes(args: dict[str, Any]) -> dict[str, Any]:
    baseline = _require_str(args, "baseline_path")
    candidate = _require_str(args, "candidate_path")
    return diff_cassettes_report(baseline, candidate)


def _handle_fork_and_replay_step(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    step = args.get("step")
    if isinstance(step, bool) or not isinstance(step, int):
        raise ValueError("Parameter 'step' must be an integer.")
    output_path = args.get("output_path")
    if output_path is not None and (not isinstance(output_path, str) or not output_path.strip()):
        raise ValueError("Parameter 'output_path' must be a non-empty string if provided.")
    return fork_cassette_at_step(cassette_path, step, output_path=output_path)


def _handle_scaffold_pytest(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    test_name = str(args.get("test_name") or "test_agent_regression")
    mode = str(args.get("mode") or "replay")
    return scaffold_pytest_regression_code(cassette_path, test_name=test_name, mode=mode)


def _handle_verify_cassette(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    strict_security = args.get("strict_security", True)
    if not isinstance(strict_security, bool):
        raise ValueError("Parameter 'strict_security' must be a boolean.")
    return verify_cassette_report(cassette_path, strict_security=strict_security)


def _handle_scrub_cassette(args: dict[str, Any]) -> dict[str, Any]:
    cassette_path = _require_str(args, "cassette_path")
    output_path = args.get("output_path")
    if output_path is not None and (not isinstance(output_path, str) or not output_path.strip()):
        raise ValueError("Parameter 'output_path' must be a non-empty string if provided.")
    dry_run = args.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise ValueError("Parameter 'dry_run' must be a boolean.")
    return scrub_cassette_file(cassette_path, output_path=output_path, dry_run=dry_run)


def _handle_estimate_savings(args: dict[str, Any]) -> dict[str, Any]:
    target_path = args.get("target_path", "tests/cassettes")
    if not isinstance(target_path, str) or not target_path.strip():
        raise ValueError("Parameter 'target_path' must be a non-empty string.")
    return estimate_savings_summary(target_path)


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "inspect_cassette": _handle_inspect_cassette,
    "read_cassette_step": _handle_read_cassette_step,
    "diff_cassettes": _handle_diff_cassettes,
    "fork_and_replay_step": _handle_fork_and_replay_step,
    "scaffold_pytest_regression": _handle_scaffold_pytest,
    "verify_cassette": _handle_verify_cassette,
    "scrub_cassette": _handle_scrub_cassette,
    "estimate_savings": _handle_estimate_savings,
}


def _jsonrpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_jsonrpc_message(message: Any) -> dict[str, Any] | None:
    """Process a parsed JSON-RPC 2.0 request/notification and return a response dict or None."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _jsonrpc_error(
            message.get("id") if isinstance(message, dict) else None,
            JSONRPC_INVALID_REQUEST,
            "Invalid JSON-RPC 2.0 request.",
        )

    method = message.get("method")
    if not isinstance(method, str) or not method:
        return _jsonrpc_error(message.get("id"), JSONRPC_INVALID_REQUEST, "Missing method name.")

    is_notification = "id" not in message
    request_id = message.get("id")
    params = message.get("params") or {}

    if method in ("notifications/initialized", "notifications/cancelled", "initialized"):
        return None

    if is_notification:
        return None

    if method == "ping":
        return _jsonrpc_result(request_id, {})

    if method == "initialize":
        requested_version = params.get("protocolVersion") if isinstance(params, dict) else None
        protocol_version = (
            requested_version
            if isinstance(requested_version, str)
            and requested_version in SUPPORTED_PROTOCOL_VERSIONS
            else DEFAULT_PROTOCOL_VERSION
        )
        return _jsonrpc_result(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "rerunner",
                    "version": get_rerunner_version(),
                },
            },
        )

    if method == "tools/list":
        return _jsonrpc_result(request_id, {"tools": TOOL_DEFINITIONS})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _jsonrpc_error(
                request_id, JSONRPC_INVALID_PARAMS, "tools/call params must be an object."
            )
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(tool_name, str) or tool_name not in TOOL_HANDLERS:
            return _jsonrpc_error(
                request_id, JSONRPC_INVALID_PARAMS, f"Unknown tool: {tool_name!r}"
            )
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return _jsonrpc_error(
                request_id, JSONRPC_INVALID_PARAMS, "Tool arguments must be a JSON object."
            )

        try:
            payload = TOOL_HANDLERS[tool_name](arguments)
            return _jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
                    "isError": False,
                },
            )
        except Exception as exc:
            return _jsonrpc_result(
                request_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"error": str(exc), "tool": tool_name}, indent=2),
                        }
                    ],
                    "isError": True,
                },
            )

    return _jsonrpc_error(request_id, JSONRPC_METHOD_NOT_FOUND, f"Method not found: {method}")


def _read_next_frame(stdin: BinaryIO) -> bytes | None:
    """Read either a newline-delimited JSON line or a Content-Length framed payload."""
    while True:
        raw_line = stdin.readline()
        if not raw_line:
            return None
        stripped = raw_line.strip()
        if not stripped:
            continue

        # Support optional LSP-style Content-Length framing if a client uses it
        if stripped.lower().startswith(b"content-length:"):
            try:
                content_length = int(stripped.split(b":", 1)[1].strip())
            except ValueError:
                return stripped
            # Consume remaining headers until empty CRLF/LF line
            while True:
                header_line = stdin.readline()
                if not header_line or header_line in (b"\r\n", b"\n"):
                    break
            body = stdin.read(content_length)
            return body if body else None

        return stripped


def serve_stdio(
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> None:
    """Run the MCP stdio JSON-RPC 2.0 event loop until EOF."""
    in_stream = stdin if stdin is not None else sys.stdin.buffer
    out_stream = stdout if stdout is not None else sys.stdout.buffer

    while True:
        raw_frame = _read_next_frame(in_stream)
        if raw_frame is None:
            break

        try:
            decoded = json.loads(raw_frame.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            response: dict[str, Any] | None = _jsonrpc_error(
                None, JSONRPC_PARSE_ERROR, f"Parse error: {exc}"
            )
        else:
            response = handle_jsonrpc_message(decoded)

        if response is not None:
            encoded = (json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8")
            out_stream.write(encoded)
            out_stream.flush()
