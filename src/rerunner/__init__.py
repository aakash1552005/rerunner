"""Rerunner: Deterministic flight recorder, replay engine, and CI test runner for AI agents."""

from __future__ import annotations

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette, CassetteError
from rerunner.otel import export_cassette_to_otel_file, export_to_otlp
from rerunner.sanitizer import sanitize_headers, sanitize_payload, sanitize_string
from rerunner.session import fork, record, replay
from rerunner.side_effects import side_effect
from rerunner.transport import CassetteTransport

__version__ = "0.1.2"

__all__ = [

    "AsyncCassetteTransport",
    "Cassette",
    "CassetteError",
    "CassetteTransport",
    "export_cassette_to_otel_file",
    "export_to_otlp",
    "fork",
    "record",
    "replay",
    "sanitize_headers",
    "sanitize_payload",
    "sanitize_string",
    "side_effect",
]


