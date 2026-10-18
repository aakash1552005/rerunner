"""OpenTelemetry (OTel) trace and metrics exporter for Rerunner cassettes.

Allows exporting recorded agent execution steps into standardized OpenTelemetry
OTLP-compliant trace structures and metrics for Datadog, Jaeger, Grafana Tempo, Dynatrace,
and Prometheus.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rerunner.cassette import Cassette


def _generate_deterministic_id(seed: str, length: int) -> str:
    """Generate a deterministic hex ID from a seed string."""
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return digest[:length]


def export_to_otlp(
    cassette: Cassette,
    service_name: str = "rerunner-agent",
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Convert a loaded Rerunner Cassette into an OpenTelemetry OTLP JSON dictionary.

    Args:
        cassette: The loaded Cassette instance.
        service_name: Name of the service to report in OTel resource attributes.
        trace_id: Optional 32-character hex trace ID. If omitted, derived from cassette metadata.

    Returns:
        A dictionary compliant with the OpenTelemetry OTLP/HTTP trace payload specification.
    """
    from rerunner._version import __version__

    agent_id = cassette.metadata.agent_id or "default-agent"
    base_time_ns = int(cassette.metadata.created_at * 1_000_000_000)

    # 32-character hex string for OpenTelemetry traceId
    if not trace_id:
        seed = f"{agent_id}:{cassette.metadata.created_at}:{cassette.path.name}"
        trace_id = _generate_deterministic_id(seed, 32)
    else:
        trace_id = trace_id.lower().replace("-", "")[:32].zfill(32)

    root_span_id = _generate_deterministic_id(f"{trace_id}:root", 16)

    spans: list[dict[str, Any]] = []

    # 1. Root span representing the entire agent session
    session_duration_ns = max(len(cassette.entries) * 200_000_000, 500_000_000)
    root_span = {
        "traceId": trace_id,
        "spanId": root_span_id,
        "parentSpanId": "",
        "name": f"agent.session:{agent_id}",
        "kind": 1,  # SPAN_KIND_INTERNAL
        "startTimeUnixNano": str(base_time_ns),
        "endTimeUnixNano": str(base_time_ns + session_duration_ns),
        "attributes": [
            {
                "key": "rerunner.format_version",
                "value": {"stringValue": cassette.metadata.format_version},
            },
            {"key": "rerunner.total_steps", "value": {"intValue": len(cassette.entries)}},
            {
                "key": "rerunner.hash_algorithm",
                "value": {"stringValue": cassette.metadata.hash_algorithm},
            },
        ],
        "status": {"code": 1},  # STATUS_CODE_OK
    }
    spans.append(root_span)

    # 2. Child spans for each step in the cassette
    current_time_ns = base_time_ns + 10_000_000
    for entry in cassette.entries:
        step_duration_ns = 150_000_000  # simulated 150ms step duration
        step_span_id = _generate_deterministic_id(f"{trace_id}:step:{entry.step}", 16)

        span_attributes: list[dict[str, Any]] = [
            {"key": "rerunner.step", "value": {"intValue": entry.step}},
            {"key": "rerunner.entry_type", "value": {"stringValue": entry.entry_type}},
        ]
        if entry.entry_hash:
            span_attributes.append(
                {"key": "rerunner.entry_hash", "value": {"stringValue": entry.entry_hash}}
            )

        span_name: str
        if entry.entry_type == "http" and entry.request and entry.response:
            span_name = f"{entry.request.method} {entry.request.url.split('?')[0]}"
            span_attributes.extend(
                [
                    {"key": "http.method", "value": {"stringValue": entry.request.method}},
                    {"key": "http.url", "value": {"stringValue": entry.request.url}},
                    {"key": "http.status_code", "value": {"intValue": entry.response.status_code}},
                ]
            )
            # Detect model provider
            if "api.anthropic.com" in entry.request.url:
                span_attributes.append(
                    {"key": "gen_ai.system", "value": {"stringValue": "anthropic"}}
                )
            elif "api.openai.com" in entry.request.url:
                span_attributes.append({"key": "gen_ai.system", "value": {"stringValue": "openai"}})
            elif "googleapis.com" in entry.request.url:
                span_attributes.append(
                    {"key": "gen_ai.system", "value": {"stringValue": "google_genai"}}
                )
        elif entry.entry_type == "side_effect":
            tool_name = entry.side_effect_name or "unknown_tool"
            span_name = f"tool.execution:{tool_name}"
            span_attributes.append({"key": "gen_ai.tool.name", "value": {"stringValue": tool_name}})
        else:
            span_name = f"agent.step:{entry.step}"

        spans.append(
            {
                "traceId": trace_id,
                "spanId": step_span_id,
                "parentSpanId": root_span_id,
                "name": span_name,
                "kind": 3 if entry.entry_type == "http" else 1,  # SPAN_KIND_CLIENT or INTERNAL
                "startTimeUnixNano": str(current_time_ns),
                "endTimeUnixNano": str(current_time_ns + step_duration_ns),
                "attributes": span_attributes,
                "status": {"code": 1},
            }
        )

        current_time_ns += step_duration_ns + 10_000_000

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {"key": "telemetry.sdk.name", "value": {"stringValue": "rerunner"}},
                        {"key": "telemetry.sdk.version", "value": {"stringValue": __version__}},
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {
                            "name": "rerunner.tracer",
                            "version": __version__,
                        },
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def compute_cassette_metrics(cassette: Cassette) -> dict[str, Any]:
    """Compute OpenTelemetry-compliant metrics summary from cassette entries."""
    http_count = 0
    side_effect_count = 0
    status_distribution: dict[int, int] = {}
    provider_distribution: dict[str, int] = {}

    for entry in cassette.entries:
        if entry.entry_type == "http":
            http_count += 1
            if entry.response:
                status = entry.response.status_code
                status_distribution[status] = status_distribution.get(status, 0) + 1
            if entry.request:
                url = entry.request.url
                if "anthropic" in url:
                    provider_distribution["anthropic"] = (
                        provider_distribution.get("anthropic", 0) + 1
                    )
                elif "openai" in url:
                    provider_distribution["openai"] = provider_distribution.get("openai", 0) + 1
                elif "googleapis" in url:
                    provider_distribution["google"] = provider_distribution.get("google", 0) + 1
                else:
                    provider_distribution["other"] = provider_distribution.get("other", 0) + 1
        elif entry.entry_type == "side_effect":
            side_effect_count += 1

    return {
        "total_steps": len(cassette.entries),
        "http_requests_total": http_count,
        "side_effects_total": side_effect_count,
        "http_status_distribution": status_distribution,
        "model_provider_distribution": provider_distribution,
    }


def export_cassette_to_otel_file(
    cassette_path: Path | str,
    output_path: Path | str,
    service_name: str = "rerunner-agent",
    include_metrics: bool = False,
) -> None:
    """Load a cassette and export its contents to an OpenTelemetry JSON file."""
    from rerunner.cassette import Cassette

    cassette = Cassette.load(Path(cassette_path), verify_integrity=False)
    payload = export_to_otlp(cassette, service_name=service_name)
    if include_metrics:
        payload["metrics"] = compute_cassette_metrics(cassette)

    with Path(output_path).open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
