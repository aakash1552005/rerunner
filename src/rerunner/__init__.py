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
    "AsyncCassetteTransport",
    "BaseStorageBackend",
    "Cassette",
    "CassetteError",
    "CassetteMissingError",
    "CassetteTransport",
    "GCSStorageBackend",
    "LocalStorageBackend",
    "S3StorageBackend",
    "Session",
    "SessionContext",
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
    "side_effect",
]
