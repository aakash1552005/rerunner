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
    SENSITIVE_QUERY_PARAMS,
    PiiRedactor,
    SetherRedactor,
    sanitize_headers,
    sanitize_payload,
    sanitize_string,
    sanitize_url,
)
from rerunner.session import (
    CassetteMissingError,
    Session,
    SessionContext,
    fork,
    record,
    replay,
)
from rerunner.side_effects import SideEffectError, record_tool, side_effect
from rerunner.storage import (
    BaseStorageBackend,
    GCSStorageBackend,
    LocalStorageBackend,
    S3StorageBackend,
    StorageBackendError,
    get_storage_backend,
)
from rerunner.transport import CassetteTransport

from rerunner._version import __version__

__all__ = [
    "SECRET_PATTERNS",
    "SENSITIVE_HEADERS",
    "SENSITIVE_QUERY_PARAMS",
    "AsyncCassetteTransport",
    "BaseStorageBackend",
    "Cassette",
    "CassetteError",
    "CassetteMissingError",
    "CassetteTransport",
    "GCSStorageBackend",
    "LocalStorageBackend",
    "PiiRedactor",
    "S3StorageBackend",
    "Session",
    "SessionContext",
    "SetherRedactor",
    "SideEffectError",
    "StorageBackendError",
    "__version__",
    "compute_cassette_metrics",
    "export_cassette_to_otel_file",
    "export_to_otlp",
    "fork",
    "get_storage_backend",
    "record",
    "record_tool",
    "replay",
    "sanitize_headers",
    "sanitize_payload",
    "sanitize_string",
    "sanitize_url",
    "side_effect",
]
