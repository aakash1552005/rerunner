# 🗺️ Rerunner Strategic Roadmap

Our mission is to establish **Rerunner** as the standard deterministic test runner, flight recorder, and CI infrastructure for agentic AI applications.

---

## 🧭 Milestone Overview

| Release | Focus Area | Status | Target Timeline |
| :--- | :--- | :---: | :---: |
| **v0.1.0** | Core Deterministic Replay Engine | ✅ **Shipped** | Foundation |
| **v0.2.0** | SSE Streaming, Remote Stores & Integrations | ✅ **Shipped** | Core Ecosystem |
| **v0.2.1** | Hardened Sanitizer, Fail-Closed Guards & Cursor Matching | 🔄 **Current** | Stability & Safety |
| **v0.3.0** | MCP Protocol Replay & Official GitHub Action | ⏳ **Planned** | Next Up |
| **v1.0.0** | Centralized Replay Registry & Web Flight Deck | 🎯 **Long-Term** | Future Vision |

---

## ✅ v0.1.0 — Core Replay Engine (Shipped)
- [x] Modern PEP 621 packaging and typed architecture (`pyproject.toml`)
- [x] Pydantic v2 Cassette schema with streaming JSONL persistence format
- [x] SHA-256 tamper and corruption detection hash chaining between execution steps
- [x] Synchronous `CassetteTransport` (for Anthropic & OpenAI SDKs)
- [x] Asynchronous `AsyncCassetteTransport` for async agent runtimes
- [x] Tolerant request matching (stripping volatile nonces, timestamps, and `x-stainless-*` headers)
- [x] Fork-from-step engine (replay steps 1..N from tape, execute live from step N+1)
- [x] `@side_effect` decorator for safe external tool stubbing
- [x] Typer + Rich CLI (`inspect`, `verify`, `play`, `diff`, `stats`)
- [x] Native Pytest plugin (`@pytest.mark.rerunner` fixture & marker)

---

## ✅ v0.2.0 — Streaming Replay, Remote Storage & Integrations (Shipped)
- [x] **Streaming SSE Token-by-Token Replayer**: Replay `text/event-stream` chunks for agent streaming tests
- [x] **Configurable Chunk Delay**: Simulated SSE network latency via `chunk_delay_ms`
- [x] **Pluggable Remote Stores**: AWS S3 (`s3://`) and Google Cloud Storage (`gs://`) backend support
- [x] **Zstandard & Gzip Compression**: High-efficiency `.jsonl.zst` and `.jsonl.gz` trace storage
- [x] **OpenTelemetry (OTel) Export**: `rerunner export-otel` converting cassettes into OTLP spans for Datadog, Jaeger, and Grafana Tempo
- [x] **1-Line SDK Wrappers**: Direct attachment for Anthropic, OpenAI, and Google GenAI clients
- [x] **Framework Integrations**: LangChain / LangGraph callback handler & LlamaIndex hooks

---

## 🔄 v0.2.1 — Hardened Sanitizer & Replay Determinism (Current)
- [x] **JSON-Safe Secret Redactor**: Parse JSON bodies to scrub strings without corrupting numeric Unix timestamps or booleans
- [x] **Luhn Check for Credit Cards**: Prevent false positives on 16-digit entity IDs
- [x] **Per-Key Cursor Matching**: Accurately replay repeated identical requests and retry loops in recorded order
- [x] **Fail-Closed Side Effects**: Unrecorded side-effects immediately abort during replay to prevent unauthorized live execution
- [x] **Side-Effect Argument Matching & Sanitization**: Match side-effects by argument hash and redact sensitive arguments/results
- [x] **Gzip Response Header Normalization**: Strip `content-encoding` and `content-length` so decoded bodies replay without DecodingError
- [x] **URL Credential Scrubbing**: Redact API keys from query strings (`?key=...`) and URL paths
- [x] **Proxy Mount Isolation**: Ensure cassette transports take precedence over `HTTPS_PROXY` environment mounts
- [x] **HMAC Cryptographic Signing**: Support HMAC-SHA256 cassette validation via `RERUNNER_HMAC_KEY`

---

## ⏳ v0.3.0 — MCP Protocol Replay & Official GitHub Action (Planned)
- [ ] **Model Context Protocol (MCP) Replay**: Deterministically record and replay MCP tool invocations and server sessions
- [ ] **Official GitHub Action (`rerunner-action`)**: Zero-config marketplace action for cassette caching and drift checks
- [ ] **Drift & Cost Report in CI**: Detailed terminal and PR comment summary showing changed prompts and estimated token savings
- [ ] **Cassette Scrub & Doctor CLI**: `rerunner doctor` and `rerunner scrub` commands to audit existing cassettes for secrets
- [ ] **Cassette-to-Eval Dataset Exporter**: Convert recorded agent trajectories into evaluation regression datasets

---

## 🎯 v1.0.0 — Centralized Replay Registry & Web Flight Deck (Future Vision)
- [ ] **Centralized Replay Registry**: Multi-developer cassette sharing with automatic versioning and CI deduplication
- [ ] **Web Flight Deck UI**: Interactive browser visualizer for scrubbing through multi-step agent executions and tool calls
- [ ] **Semantic Drift Detection**: Embedding-based tolerant matching to alert when prompt alterations diverge from cassette intent

---

## 🤝 Contributing & Submitting RFCs

We actively invite community contributions:
1. For architectural proposals, open an [RFC (Request for Comments)](.github/ISSUE_TEMPLATE/rfc.yml).
2. For starter tasks, check issues tagged [`good first issue`](https://github.com/aakash1552005/rerunner/labels/good%20first%20issue).
3. Review our [Contributing Guide](CONTRIBUTING.md) for code standards and setup instructions.
