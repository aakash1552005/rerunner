"""Rerunner: Deterministic flight recorder, replay engine, and CI test runner for AI agents."""

from __future__ import annotations

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette, CassetteError
from rerunner.otel import (
    compute_cassette_metrics,
    export_cassette_to_otel_file,
    export_to_otlp,
)
from rerunner.sanitizer import (
    SECRET_PATTERNS,
    SENSITIVE_HEADERS,
    sanitize_headers,
    sanitize_payload,
    sanitize_string,
)
from rerunner.session import fork, record, replay
from rerunner.side_effects import side_effect
from rerunner.storage import (
    BaseStorageBackend,
    GCSStorageBackend,
    LocalStorageBackend,
    S3StorageBackend,
    StorageBackendError,
    get_storage_backend,
)
from rerunner.transport import CassetteTransport

__version__ = "0.2.1"

__all__ = [
    "SECRET_PATTERNS",
    "SENSITIVE_HEADERS",
    "AsyncCassetteTransport",
    "BaseStorageBackend",
    "Cassette",
    "CassetteError",
    "CassetteTransport",
    "GCSStorageBackend",
    "LocalStorageBackend",
    "S3StorageBackend",
    "StorageBackendError",
    "compute_cassette_metrics",
    "export_cassette_to_otel_file",
    "export_to_otlp",
    "fork",
    "get_storage_backend",
    "record",
    "replay",
    "sanitize_headers",
    "sanitize_payload",
    "sanitize_string",
    "side_effect",
]
