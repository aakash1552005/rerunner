"""UI-agnostic cassette inspection, verification, diffing, scrubbing, and fork helpers."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from rerunner.cassette import Cassette
from rerunner.integrity import compute_entry_hash, verify_cassette_integrity
from rerunner.models import CassetteEntry
from rerunner.sanitizer import (
    find_sensitive_leaks,
    sanitize_chunks,
    sanitize_headers,
    sanitize_payload,
    sanitize_string,
    sanitize_url,
)

CASSETTE_EXTENSIONS = (".jsonl", ".json", ".jsonl.zst", ".cassette.zst", ".zst", ".jsonl.gz", ".gz")
DEFAULT_COST_PER_M_TOKENS_USD = 10.0
DEFAULT_LIVE_CALL_LATENCY_SECONDS = 1.8

# Blended (input_usd_per_1M, output_usd_per_1M) reference rates for common LLM models
MODEL_PRICING_PER_1M_USD: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "o3-mini": (1.10, 4.40),
    "o1": (15.00, 60.00),
    "claude-3-5-haiku": (0.80, 4.00),
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-7-sonnet": (3.00, 15.00),
    "claude-sonnet-4": (3.00, 15.00),
    "claude-3-opus": (15.00, 75.00),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "command-a": (2.50, 10.00),
    "command-r-plus": (2.50, 10.00),
    "command-r": (0.15, 0.60),
}
DEFAULT_INPUT_OUTPUT_PRICING_USD = (2.50, 10.00)


def extract_model_from_bodies(req_body: str, resp_body: str) -> str | None:
    """Extract model identifier from recorded HTTP response or request JSON payloads."""
    for raw in (resp_body, req_body):
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(data, dict):
            model = data.get("model") or data.get("modelVersion")
            if isinstance(model, str) and model.strip():
                return model.strip()
    return None


def resolve_model_pricing(model: str | None) -> tuple[float, float]:
    """Return ``(input_usd_per_1M, output_usd_per_1M)`` for ``model`` with prefix matching."""
    if not model:
        return DEFAULT_INPUT_OUTPUT_PRICING_USD
    norm = model.lower().strip()
    for prefix in sorted(MODEL_PRICING_PER_1M_USD.keys(), key=len, reverse=True):
        if norm == prefix or norm.startswith(f"{prefix}-") or norm.startswith(prefix):
            return MODEL_PRICING_PER_1M_USD[prefix]
    return DEFAULT_INPUT_OUTPUT_PRICING_USD


def estimate_entry_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    model: str | None = None,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Calculate estimated API USD cost for a single recorded step, accounting for prompt caching."""
    in_rate, out_rate = resolve_model_pricing(model)
    if (
        prompt_tokens > 0
        or completion_tokens > 0
        or cache_creation_input_tokens > 0
        or cache_read_input_tokens > 0
    ):
        base_cost = (prompt_tokens / 1_000_000.0) * in_rate
        completion_cost = (completion_tokens / 1_000_000.0) * out_rate
        cache_write_cost = (cache_creation_input_tokens / 1_000_000.0) * (in_rate * 1.25)
        cache_read_cost = (cache_read_input_tokens / 1_000_000.0) * (in_rate * 0.10)
        return base_cost + completion_cost + cache_write_cost + cache_read_cost
    blended_rate = (in_rate + out_rate) / 2.0
    return (max(0, total_tokens) / 1_000_000.0) * blended_rate


def extract_detailed_tokens_from_body(body_str: str) -> dict[str, int]:
    """Extract prompt, completion, total, and prompt-caching token counts from a JSON response body."""
    result = {
        "prompt": 0,
        "completion": 0,
        "total": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    if not body_str:
        return result
    try:
        data = json.loads(body_str)
        if isinstance(data, dict):
            usage = data.get("usage")
            if isinstance(usage, dict):
                prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                comp = usage.get("completion_tokens") or usage.get("output_tokens") or 0
                cache_creation = (
                    usage.get("cache_creation_input_tokens")
                    or usage.get("cache_creation_tokens")
                    or 0
                )
                cache_read = (
                    usage.get("cache_read_input_tokens") or usage.get("cache_read_tokens") or 0
                )
                total = usage.get("total_tokens")
                if total is None or not isinstance(total, int):
                    total = int(prompt) + int(comp) + int(cache_creation) + int(cache_read)
                result["prompt"] = int(prompt) if isinstance(prompt, (int, float)) else 0
                result["completion"] = int(comp) if isinstance(comp, (int, float)) else 0
                result["cache_creation_input_tokens"] = (
                    int(cache_creation) if isinstance(cache_creation, (int, float)) else 0
                )
                result["cache_read_input_tokens"] = (
                    int(cache_read) if isinstance(cache_read, (int, float)) else 0
                )
                result["total"] = int(total)
    except (json.JSONDecodeError, TypeError, ValueError, KeyError):
        pass
    return result


def extract_tokens_from_body(body_str: str) -> int | None:
    """Return total tokens reported in ``body_str`` or ``None`` if unavailable."""
    tokens = extract_detailed_tokens_from_body(body_str)["total"]
    return tokens if tokens > 0 else None


def extract_entry_info(entry: CassetteEntry) -> dict[str, Any]:
    """Build a compact summary dictionary for a single cassette entry."""
    step = entry.step
    if entry.entry_type == "http" and entry.request and entry.response:
        entry_type = "HTTP"
        target = f"{entry.request.method} {entry.request.url}"
        status = str(entry.response.status_code)
        streaming = "Yes" if entry.response.is_streaming else "No"
        tokens = extract_tokens_from_body(entry.response.body)
        latency = (
            f"{sum(entry.response.chunk_delays_ms):.1f}ms"
            if entry.response.chunk_delays_ms and sum(entry.response.chunk_delays_ms) > 0
            else "-"
        )
    elif entry.entry_type in ("side_effect", "tool"):
        entry_type = "Tool"
        target = f"{entry.side_effect_name or 'tool'}(...)"
        status = "Error" if entry.side_effect_exception else "OK"
        streaming = "-"
        tokens = None
        latency = "-"
    else:
        entry_type = "Unknown"
        target = "Unknown payload"
        status = "-"
        streaming = "-"
        tokens = None
        latency = "-"

    return {
        "step": step,
        "type": entry_type,
        "target": target,
        "status": status,
        "streaming": streaming,
        "tokens": tokens,
        "latency": latency,
        "entry": entry,
    }


def scan_entry_leaks(entry: CassetteEntry, *, include_url_and_chunks: bool = True) -> list[str]:
    """Return deduplicated sensitive-data leak descriptions found in ``entry``."""
    leaks: list[str] = []
    if entry.entry_type == "http" and entry.request and entry.response:
        if include_url_and_chunks:
            leaks.extend(find_sensitive_leaks(entry.request.url))
        leaks.extend(find_sensitive_leaks(entry.request.headers))
        leaks.extend(find_sensitive_leaks(entry.request.body))
        leaks.extend(find_sensitive_leaks(entry.response.headers))
        leaks.extend(find_sensitive_leaks(entry.response.body))
        if include_url_and_chunks and entry.response.chunks:
            leaks.extend(find_sensitive_leaks(entry.response.chunks))
    elif entry.entry_type in ("side_effect", "tool"):
        if entry.side_effect_args:
            leaks.extend(find_sensitive_leaks(entry.side_effect_args))
        if entry.side_effect_kwargs:
            leaks.extend(find_sensitive_leaks(entry.side_effect_kwargs))
        if entry.side_effect_result:
            leaks.extend(find_sensitive_leaks(entry.side_effect_result))
        if include_url_and_chunks and entry.side_effect_exception:
            leaks.extend(find_sensitive_leaks(entry.side_effect_exception))
    return list(dict.fromkeys(leaks))


def scan_cassette_leaks(cassette: Cassette, *, include_url_and_chunks: bool = True) -> list[str]:
    """Scan all entries in ``cassette`` for unredacted API keys or PII."""
    leaks: list[str] = []
    for entry in cassette.entries:
        leaks.extend(scan_entry_leaks(entry, include_url_and_chunks=include_url_and_chunks))
    return list(dict.fromkeys(leaks))


def verify_cassette_report(
    cassette_path: Path | str,
    *,
    strict_security: bool = True,
) -> dict[str, Any]:
    """Verify hash chaining, scan for leaked secrets/PII, and compute savings."""
    cassette = Cassette.load(cassette_path, verify_integrity=False)
    is_valid, integrity_error = verify_cassette_integrity(cassette.entries)
    leaks = scan_cassette_leaks(cassette, include_url_and_chunks=True)

    total_chars = 0
    http_steps = 0
    side_effect_steps = 0
    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            http_steps += 1
            total_chars += len(entry.request.body) + len(entry.response.body)
        elif entry.entry_type in ("side_effect", "tool"):
            side_effect_steps += 1

    est_tokens = max(0, total_chars // 4)
    est_dollars_saved = (est_tokens / 1_000_000) * DEFAULT_COST_PER_M_TOKENS_USD
    est_duration_saved = http_steps * DEFAULT_LIVE_CALL_LATENCY_SECONDS
    security_passed = len(leaks) == 0

    return {
        "cassette": str(cassette_path),
        "integrity_valid": is_valid,
        "integrity_error": integrity_error,
        "security_passed": security_passed,
        "strict_security": strict_security,
        "valid": is_valid and (security_passed or not strict_security),
        "leaks": leaks,
        "total_steps": len(cassette.entries),
        "http_steps": http_steps,
        "side_effect_steps": side_effect_steps,
        "estimated_tokens_saved": est_tokens,
        "estimated_cost_saved_usd": round(est_dollars_saved, 4),
        "estimated_time_saved_seconds": round(est_duration_saved, 2),
    }


def _truncate_preview(text: str, max_chars: int = 1200) -> dict[str, Any]:
    """Return bounded text with truncation metadata for token-efficient agent inspection."""
    if len(text) <= max_chars:
        return {"text": text, "truncated": False, "total_chars": len(text)}
    return {
        "text": text[:max_chars],
        "truncated": True,
        "total_chars": len(text),
    }


def inspect_cassette_summary(
    cassette_path: Path | str,
    *,
    limit: int = 20,
    offset: int = 0,
    entry_type: str | None = None,
) -> dict[str, Any]:
    """Return bounded step summaries and cassette metadata without full payload bloat."""
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if offset < 0:
        raise ValueError("offset must be >= 0")

    cassette = Cassette.load(cassette_path, verify_integrity=False)
    filtered: list[CassetteEntry] = cassette.entries
    if entry_type:
        norm = entry_type.strip().lower()
        if norm in ("tool", "side_effect"):
            filtered = [e for e in filtered if e.entry_type in ("tool", "side_effect")]
        else:
            filtered = [e for e in filtered if e.entry_type.lower() == norm]

    sliced = filtered[offset : offset + limit]
    steps = []
    for entry in sliced:
        info = extract_entry_info(entry)
        steps.append(
            {
                "step": info["step"],
                "entry_type": entry.entry_type,
                "type_label": info["type"],
                "target": info["target"],
                "status": info["status"],
                "streaming": info["streaming"] == "Yes",
                "tokens": info["tokens"],
                "latency": info["latency"],
            }
        )

    return {
        "cassette": str(cassette_path),
        "metadata": cassette.metadata.model_dump(),
        "total_entries": len(cassette.entries),
        "filtered_entries": len(filtered),
        "offset": offset,
        "limit": limit,
        "has_more": offset + limit < len(filtered),
        "steps": steps,
    }


def read_cassette_step_detail(
    cassette_path: Path | str,
    step: int,
    *,
    max_body_chars: int = 4000,
) -> dict[str, Any]:
    """Return detailed request/response or tool payload for a single recorded step."""
    cassette = Cassette.load(cassette_path, verify_integrity=False)
    match = next((entry for entry in cassette.entries if entry.step == step), None)
    if match is None:
        available = [entry.step for entry in cassette.entries[:25]]
        raise ValueError(f"Step {step} not found in cassette. Available sample steps: {available}")

    result: dict[str, Any] = {
        "cassette": str(cassette_path),
        "step": match.step,
        "entry_type": match.entry_type,
        "timestamp": match.timestamp,
        "entry_hash": match.entry_hash,
        "prev_hash": match.prev_hash,
    }
    if match.entry_type == "http" and match.request and match.response:
        result["request"] = {
            "method": match.request.method,
            "url": match.request.url,
            "request_key": match.request.request_key,
            "headers": match.request.headers,
            "body": _truncate_preview(match.request.body, max_chars=max_body_chars),
        }
        result["response"] = {
            "status_code": match.response.status_code,
            "http_version": match.response.http_version,
            "is_streaming": match.response.is_streaming,
            "chunk_count": len(match.response.chunks),
            "headers": match.response.headers,
            "tokens": extract_detailed_tokens_from_body(match.response.body),
            "body": _truncate_preview(match.response.body, max_chars=max_body_chars),
        }
    else:
        result["side_effect"] = {
            "name": match.side_effect_name,
            "args": match.side_effect_args,
            "kwargs": match.side_effect_kwargs,
            "result": match.side_effect_result,
            "exception": match.side_effect_exception,
        }
    return result


def diff_cassettes_report(cassette_a: Path | str, cassette_b: Path | str) -> dict[str, Any]:
    """Compare two cassettes step-by-step and return structured drift telemetry."""
    c1 = Cassette.load(cassette_a, verify_integrity=False)
    c2 = Cassette.load(cassette_b, verify_integrity=False)

    max_len = max(len(c1.entries), len(c2.entries))
    has_drift = False
    tokens_a = 0
    tokens_b = 0
    added_steps = 0
    removed_steps = 0
    prompt_diffs = 0
    status_diffs = 0
    steps_diff: list[dict[str, Any]] = []

    for i in range(max_len):
        e1 = c1.entries[i] if i < len(c1.entries) else None
        e2 = c2.entries[i] if i < len(c2.entries) else None

        info1 = extract_entry_info(e1) if e1 else None
        info2 = extract_entry_info(e2) if e2 else None

        if info1 and info1["tokens"]:
            tokens_a += info1["tokens"]
        if info2 and info2["tokens"]:
            tokens_b += info2["tokens"]

        step_type = info1["type"] if info1 else (info2["type"] if info2 else "Unknown")
        step_drift = False
        drift_reasons: list[str] = []

        if e1 is None:
            has_drift = True
            step_drift = True
            added_steps += 1
            drift_reasons.append("Added in B")
        elif e2 is None:
            has_drift = True
            step_drift = True
            removed_steps += 1
            drift_reasons.append("Removed from B")
        else:
            if info1 and info2 and info1["type"] != info2["type"]:
                has_drift = True
                step_drift = True
                drift_reasons.append("Type mismatch")
            elif info1 and info2 and info1["target"] != info2["target"]:
                has_drift = True
                step_drift = True
                drift_reasons.append("Target modified")
            elif info1 and info2 and info1["status"] != info2["status"]:
                has_drift = True
                step_drift = True
                status_diffs += 1
                drift_reasons.append(f"Status ({info1['status']} != {info2['status']})")

            if e1.entry_type == "http" and e2.entry_type == "http":
                if e1.request and e2.request and e1.request.body != e2.request.body:
                    has_drift = True
                    step_drift = True
                    prompt_diffs += 1
                    drift_reasons.append("Prompt modified")
            elif (
                e1.entry_type in ("side_effect", "tool")
                and e2.entry_type in ("side_effect", "tool")
                and (
                    e1.side_effect_args != e2.side_effect_args
                    or e1.side_effect_kwargs != e2.side_effect_kwargs
                )
            ):
                has_drift = True
                step_drift = True
                prompt_diffs += 1
                drift_reasons.append("Tool args modified")

        steps_diff.append(
            {
                "index": i + 1,
                "type": step_type,
                "a_target": info1["target"] if info1 else None,
                "a_status": info1["status"] if info1 else None,
                "b_target": info2["target"] if info2 else None,
                "b_status": info2["status"] if info2 else None,
                "drift": step_drift,
                "reasons": drift_reasons,
            }
        )

    return {
        "cassette_a": str(cassette_a),
        "cassette_b": str(cassette_b),
        "steps_a": len(c1.entries),
        "steps_b": len(c2.entries),
        "tokens_a": tokens_a,
        "tokens_b": tokens_b,
        "token_delta": tokens_b - tokens_a,
        "added_steps": added_steps,
        "removed_steps": removed_steps,
        "prompt_diffs": prompt_diffs,
        "status_diffs": status_diffs,
        "has_drift": has_drift,
        "steps": steps_diff,
    }


def _sanitize_json_or_text(raw_body: str) -> str:
    """Scrub structured JSON payloads when valid JSON, otherwise sanitize plain text."""
    try:
        body_json = json.loads(raw_body)
        return json.dumps(sanitize_payload(body_json), separators=(",", ":"))
    except Exception:
        return sanitize_string(raw_body)


def scrub_cassette_file(
    cassette_path: Path | str,
    *,
    output_path: Path | str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scrub secrets and PII from a cassette, re-signing its SHA-256 chain."""
    cassette = Cassette.load(cassette_path, verify_integrity=False)
    initial_leaks = scan_cassette_leaks(cassette, include_url_and_chunks=True)

    scrubbed_count = 0
    expected_prev = "GENESIS"

    for entry in cassette.entries:
        if entry.entry_type == "http" and entry.request and entry.response:
            entry.request.url = sanitize_url(entry.request.url)
            entry.request.headers = sanitize_headers(entry.request.headers)
            entry.request.body = _sanitize_json_or_text(entry.request.body)

            entry.response.headers = sanitize_headers(entry.response.headers)
            entry.response.body = _sanitize_json_or_text(entry.response.body)

            if entry.response.chunks:
                entry.response.chunks = sanitize_chunks(entry.response.chunks)
            scrubbed_count += 1
        elif entry.entry_type in ("side_effect", "tool"):
            if entry.side_effect_args:
                entry.side_effect_args = sanitize_payload(entry.side_effect_args)
            if entry.side_effect_kwargs:
                entry.side_effect_kwargs = sanitize_payload(entry.side_effect_kwargs)
            if entry.side_effect_result:
                entry.side_effect_result = sanitize_payload(entry.side_effect_result)
            if entry.side_effect_exception:
                entry.side_effect_exception = sanitize_string(entry.side_effect_exception)
            scrubbed_count += 1

        entry.prev_hash = expected_prev
        entry.entry_hash = compute_entry_hash(entry, expected_prev)
        expected_prev = entry.entry_hash

    cassette._last_hash = expected_prev
    target = output_path if output_path is not None else cassette_path

    if not dry_run:
        cassette.save(target)

    return {
        "cassette": str(cassette_path),
        "target": str(target),
        "dry_run": dry_run,
        "total_steps": len(cassette.entries),
        "scrubbed_steps": scrubbed_count,
        "initial_leaks": initial_leaks,
        "remaining_leaks": scan_cassette_leaks(cassette, include_url_and_chunks=True),
        "new_head_hash": expected_prev,
    }


def _default_fork_destination(cassette_path: Path | str, step: int) -> str:
    """Derive a non-destructive forked cassette filename next to ``cassette_path``."""
    raw = str(cassette_path)
    for ext in CASSETTE_EXTENSIONS:
        if raw.endswith(ext):
            stem = raw[: -len(ext)]
            return f"{stem}.fork_step_{step}{ext}"
    return f"{raw}.fork_step_{step}.jsonl"


def fork_cassette_at_step(
    cassette_path: Path | str,
    step: int,
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Create a forked cassette truncated after ``step`` ready for deterministic fork-replay."""
    if step < 0:
        raise ValueError("step must be >= 0")

    cassette = Cassette.load(cassette_path, verify_integrity=False)
    original_steps = len(cassette.entries)
    cassette.truncate_after_step(step)
    retained_steps = len(cassette.entries)

    destination = (
        output_path if output_path is not None else _default_fork_destination(cassette_path, step)
    )
    cassette.save(destination)

    dest_str = str(destination)
    return {
        "source_cassette": str(cassette_path),
        "forked_cassette": dest_str,
        "fork_step": step,
        "original_steps": original_steps,
        "retained_steps": retained_steps,
        "truncated_steps": max(0, original_steps - retained_steps),
        "next_step": retained_steps + 1,
        "python_snippet": (f'with rerunner.fork("{dest_str}", step={step}):\n    run_agent()'),
    }


def _is_cassette_filename(name: str) -> bool:
    lower = name.lower()
    return any(lower.endswith(ext) for ext in CASSETTE_EXTENSIONS)


def estimate_savings_summary(target_path: Path | str = "tests/cassettes") -> dict[str, Any]:
    """Estimate token, USD cost, and CI latency savings for a cassette file or directory."""
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"Target path does not exist: {target_path}")

    files: list[Path]
    if target.is_file():
        files = [target]
    else:
        files = []
        for root, _, filenames in os.walk(target):
            for fname in sorted(filenames):
                if _is_cassette_filename(fname):
                    files.append(Path(root) / fname)

    total_steps = 0
    total_http = 0
    total_side_effects = 0
    total_tokens = 0
    total_cost = 0.0
    total_time = 0.0
    per_file: list[dict[str, Any]] = []
    warnings: list[str] = []

    for fpath in files:
        try:
            report = verify_cassette_report(fpath, strict_security=False)
        except Exception as exc:
            warnings.append(f"{fpath}: {exc}")
            continue
        total_steps += report["total_steps"]
        total_http += report["http_steps"]
        total_side_effects += report["side_effect_steps"]
        total_tokens += report["estimated_tokens_saved"]
        total_cost += report["estimated_cost_saved_usd"]
        total_time += report["estimated_time_saved_seconds"]
        if len(per_file) < 25:
            per_file.append(
                {
                    "cassette": str(fpath),
                    "total_steps": report["total_steps"],
                    "http_steps": report["http_steps"],
                    "estimated_tokens_saved": report["estimated_tokens_saved"],
                    "estimated_cost_saved_usd": report["estimated_cost_saved_usd"],
                    "integrity_valid": report["integrity_valid"],
                }
            )

    return {
        "target_path": str(target_path),
        "cassettes_analyzed": len(files) - len(warnings),
        "total_steps": total_steps,
        "http_steps": total_http,
        "side_effect_steps": total_side_effects,
        "estimated_tokens_saved": total_tokens,
        "estimated_cost_saved_usd": round(total_cost, 4),
        "estimated_time_saved_seconds": round(total_time, 2),
        "cassettes": per_file,
        "warnings": warnings,
    }


def scaffold_pytest_regression_code(
    cassette_path: Path | str,
    *,
    test_name: str = "test_agent_regression",
    mode: str = "replay",
) -> dict[str, Any]:
    """Generate a clean pytest regression test snippet for a recorded cassette."""
    clean_name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in test_name).strip("_")
    if not clean_name:
        clean_name = "test_agent_regression"
    if not clean_name.startswith("test_"):
        clean_name = f"test_{clean_name}"

    cassette_str = str(cassette_path).replace("\\", "/")
    cassette = Cassette.load(cassette_path, verify_integrity=False)

    code = (
        "import rerunner\n\n\n"
        f'@rerunner.replay("{cassette_str}")\n'
        f"def {clean_name}() -> None:\n"
        '    """Deterministic regression test generated from recorded cassette."""\n'
        "    # Replace the body below with your agent entry point call\n"
        '    raise NotImplementedError("Invoke your agent workflow here")\n'
    )
    if mode != "replay":
        code = (
            "import rerunner\n\n\n"
            f"def {clean_name}() -> None:\n"
            '    """Deterministic session test generated from recorded cassette."""\n'
            f'    with rerunner.Session("{cassette_str}", mode="{mode}"):\n'
            "        # Replace the body below with your agent entry point call\n"
            '        raise NotImplementedError("Invoke your agent workflow here")\n'
        )

    return {
        "cassette": cassette_str,
        "test_name": clean_name,
        "recorded_steps": len(cassette.entries),
        "mode": mode,
        "pytest_code": code,
        "run_command": f"pytest -k {clean_name}",
    }


def _entry_dedup_key(entry: CassetteEntry) -> str:
    if entry.entry_type == "http" and entry.request:
        return f"http:{entry.request.method}:{entry.request.url}:{entry.request.request_key}"
    return (
        f"tool:{entry.entry_type}:{entry.side_effect_name}:"
        f"{json.dumps(entry.side_effect_args, sort_keys=True, default=str)}:"
        f"{json.dumps(entry.side_effect_kwargs, sort_keys=True, default=str)}"
    )


def verify_sources(input_paths: Sequence[Path | str]) -> None:
    """Verify SHA-256/HMAC integrity of every input shard, raising on the first failure."""
    for src in input_paths:
        try:
            Cassette.load(src, verify_integrity=True)
        except Exception as exc:
            raise ValueError(
                f"Integrity verification failed for input shard '{src}': {exc}"
            ) from exc


def merge_cassettes(
    input_paths: Sequence[Path | str],
    output_path: Path | str,
    *,
    deduplicate: bool = False,
    verify_all: bool = False,
) -> dict[str, Any]:
    """Merge multiple cassettes into one re-numbered, SHA-256 re-signed cassette."""
    if not input_paths:
        raise ValueError("At least one input cassette path is required.")

    if verify_all:
        verify_sources(input_paths)

    merged = Cassette(output_path)
    seen_keys: set[str] = set()
    deduplicated_removed = 0
    expected_prev = "GENESIS"
    step_num = 0

    for src in input_paths:
        loaded = Cassette.load(src, verify_integrity=False)
        for entry in loaded.entries:
            if deduplicate:
                key = _entry_dedup_key(entry)
                if key in seen_keys:
                    deduplicated_removed += 1
                    continue
                seen_keys.add(key)

            step_num += 1
            copied = entry.model_copy(deep=True)
            copied.step = step_num
            copied.prev_hash = expected_prev
            copied.entry_hash = compute_entry_hash(copied, expected_prev)
            expected_prev = copied.entry_hash
            merged.entries.append(copied)

    merged._last_hash = expected_prev
    merged._step_counter = step_num
    merged.save(output_path)

    return {
        "output_path": str(output_path),
        "input_cassettes": len(input_paths),
        "merged_steps": step_num,
        "deduplicated_removed": deduplicated_removed,
        "head_hash": expected_prev,
    }
