"""Unit tests for the OpenTelemetry trace and metrics exporter."""

from __future__ import annotations

import json
from pathlib import Path
from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.otel import (
    compute_cassette_metrics,
    export_cassette_to_otel_file,
    export_to_otlp,
)


def test_export_to_otlp(temp_cassette_path: Path) -> None:
    # 1. Create a cassette with an HTTP step and a side_effect step
    cassette = Cassette(temp_cassette_path)
    entry_http = CassetteEntry(
        step=1,
        entry_type="http",
        request=RecordedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers={"content-type": "application/json"},
            body='{"model": "gpt-4o", "messages": []}',
        ),
        response=RecordedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body='{"id": "chatcmpl-123"}',
        ),
    )
    entry_side_effect = CassetteEntry(
        step=2,
        entry_type="side_effect",
        side_effect_name="query_database",
        side_effect_result={"rows": 42},
    )

    cassette.append(entry_http)
    cassette.append(entry_side_effect)

    # 2. Export to OTLP payload
    payload = export_to_otlp(cassette, service_name="my-enterprise-agent")

    assert "resourceSpans" in payload
    resource_spans = payload["resourceSpans"]
    assert len(resource_spans) == 1

    # Verify Resource attributes
    res_attrs = {
        attr["key"]: attr["value"]["stringValue"]
        for attr in resource_spans[0]["resource"]["attributes"]
    }
    assert res_attrs["service.name"] == "my-enterprise-agent"
    assert res_attrs["telemetry.sdk.name"] == "rerunner"

    # Verify Scope Spans
    scope_spans = resource_spans[0]["scopeSpans"]
    assert len(scope_spans) == 1
    spans = scope_spans[0]["spans"]

    # Expect: 1 Root session span + 2 child spans = 3 spans
    assert len(spans) == 3

    # Check root span
    root = spans[0]
    assert root["parentSpanId"] == ""
    assert "agent.session:" in root["name"]

    # Check HTTP span
    http_span = spans[1]
    assert http_span["parentSpanId"] == root["spanId"]
    assert "POST https://api.openai.com/v1/chat/completions" in http_span["name"]
    http_keys = [a["key"] for a in http_span["attributes"]]
    assert "gen_ai.system" in http_keys
    assert "http.status_code" in http_keys

    # Check side effect span
    se_span = spans[2]
    assert se_span["parentSpanId"] == root["spanId"]
    assert "tool.execution:query_database" in se_span["name"]


def test_compute_cassette_metrics(temp_cassette_path: Path) -> None:
    cassette = Cassette(temp_cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST", url="https://api.anthropic.com/v1/messages", headers={}, body="{}"
            ),
            response=RecordedResponse(status_code=200, headers={}, body="{}"),
        )
    )
    cassette.append(
        CassetteEntry(
            step=2,
            entry_type="side_effect",
            side_effect_name="search_web",
            side_effect_result={"matches": 3},
        )
    )

    metrics = compute_cassette_metrics(cassette)
    assert metrics["total_steps"] == 2
    assert metrics["http_requests_total"] == 1
    assert metrics["side_effects_total"] == 1
    assert metrics["model_provider_distribution"]["anthropic"] == 1
    assert metrics["http_status_distribution"][200] == 1


def test_export_cassette_to_otel_file(temp_cassette_path: Path, tmp_path: Path) -> None:
    cassette = Cassette(temp_cassette_path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.anthropic.com/v1/messages",
                headers={},
                body="{}",
            ),
            response=RecordedResponse(
                status_code=200,
                headers={},
                body="{}",
            ),
        )
    )
    cassette.save()

    out_file = tmp_path / "trace.otel.json"
    export_cassette_to_otel_file(
        temp_cassette_path, out_file, service_name="claude-agent", include_metrics=True
    )

    assert out_file.exists()
    content = json.loads(out_file.read_text(encoding="utf-8"))
    assert "resourceSpans" in content
    assert "metrics" in content
    assert content["metrics"]["total_steps"] == 1
