# Rerunner - Architecture & Engineering Guide

## Overview

Rerunner is a deterministic flight recorder, replay engine, and CI test runner for AI agents. It intercepts HTTP traffic (via HTTPX transports) and external side-effects/tools, records interactions into append-only cryptographic JSONL/Zstandard cassettes, and replays them in CI with 0ms network latency and $0 API token costs.

---

## Architecture & Module Map (`src/rerunner/`)

- **`session.py`**: High-level `Session` context manager (supporting sync `with` and async `async with`), convenience helpers (`record`, `replay`, `fork`), and `CassetteMissingError`. Automatically resolves modes (`auto`, `record`, `replay`, `fork`) and supports global overrides via `RERUNNER_MODE`.
- **`patcher.py`**: Zero-touch SDK auto-patching for `httpx.Client` and `httpx.AsyncClient`. Routes outbound SDK calls to the active session transport while maintaining unpatched upstream clients for recording.
- **`transport.py`**: Synchronous HTTPX `CassetteTransport` implementation. Features non-blocking pass-through streaming (`_RecordingSyncByteStream`) that lazily yields SSE chunks as consumed while capturing chunk delays and persisting clean cassette entries upon stream close.
- **`async_transport.py`**: Asynchronous HTTPX `AsyncCassetteTransport` implementation. Features `_RecordingAsyncByteStream` wrapping `aiter_raw()` and persisting entries on `aclose()`.
- **`cassette.py`**: In-memory `Cassette` model with `threading.RLock` synchronization. Handles atomic step allocation (`next_step()`), cursor tracking, cryptographic hash chaining, and atomic disk persistence across `.zst`, `.cassette.zst`, `.gz`, `.jsonl.gz`, `.jsonl`, and `.json`.
- **`matcher.py`**: Tolerant request matching and normalization. Strips volatile headers (`x-stainless-*`, `authorization`, `api-key`, `user-agent`, `traceparent`, `date`), and supports `"strict"`, `"content"`, and `"fuzzy"` strategies.
- **`side_effects.py`**: External tool and side-effect guards (`@side_effect` and `@record_tool`) for sync and async functions. Thread and coroutine isolation via `contextvars.ContextVar` with clean token restoration.
- **`sanitizer.py`**: JSON-safe PII, credit card (Luhn algorithm), bearer token, and API key redaction that strictly preserves JSON structure and numeric timestamps.
- **`integrity.py`**: Tamper-evident SHA-256 hash chaining and HMAC-SHA256 digital signing.
- **`storage.py`**: Pluggable storage abstraction for local filesystem (`LocalStorageBackend`), AWS S3 (`S3StorageBackend`), and Google Cloud Storage (`GCSStorageBackend`).
- **`otel.py`**: OpenTelemetry trace export and metric calculation for agent sessions.
- **`cli.py`**: Typer & Rich CLI providing `inspect`, `diff` (with `--fail-on-drift`), `verify`, and `stats`.
- **`pytest_plugin.py`**: Pytest integration offering `@pytest.mark.rerunner` (with `auto_patch=True` enabled by default) and fixtures (`rerunner_transport`, `rerunner_session`).

---

## Development & Verification Commands

### Environment Setup
```bash
pip install -e ".[dev]"
```

### Running Tests
```bash
# Run entire test suite
pytest -v

# Run with coverage
pytest -v --cov=rerunner
```

### Linting & Formatting
```bash
# Check code style and rules
ruff check src/ tests/

# Check formatting
ruff format --check src/ tests/

# Automatically apply formatting fixes
ruff format src/ tests/
```

### Static Type Checking
```bash
# Run strict type checking across the library
mypy src/
```

---

## Core Engineering Invariants

1. **Non-Blocking Streaming**: In record mode, streaming SSE responses must NEVER be buffered or eagerly consumed before returning the response. Chunks must be yielded to the consumer in real time with arrival delays tracked lazily.
2. **Context Isolation**: Sessions, transports, and active cassettes must use `contextvars` with proper token restoration on enter/exit so concurrent `asyncio.gather()` coroutines and multi-threaded test workers never leak state or collide.
3. **Zero-Network Guarantee in Replay Mode**: Replay mode must never make live outbound network requests. Any unrecorded HTTP call or unrecorded side-effect must fail closed immediately with a clear error.
4. **PII Sanitization Before Disk Write**: All sensitive tokens, API keys, credentials, and PII must be scrubbed before entries are appended to the cassette or written to disk.
5. **Thread-Safe Step Sequencing**: Step counter allocation and cassette modifications must be guarded by `Cassette._lock` to ensure deterministic execution orders under concurrent requests.
