# 🗺️ Rerunner Strategic Roadmap

Our mission is to establish **Rerunner** as the standard deterministic test runner, flight recorder, and CI infrastructure for agentic AI applications.

---

## 🧭 Milestone Overview

| Release | Focus Area | Status | Target Timeline |
| :--- | :--- | :---: | :---: |
| **v0.1.0** | Core Deterministic Replay Engine | ✅ **Shipped** | Foundation |
| **v0.2.0** | SSE Streaming, Remote Stores & Integrations | ✅ **Shipped** | Core Ecosystem |
| **v0.2.1** | Hardened Sanitizer, Fail-Closed Guards & Cursor Matching | ✅ **Shipped** | Stability & Safety |
| **v0.3.0** | MCP Protocol Replay, Official GitHub Action & AutoGen/SK | 🔄 **Shipped** | Frontier Agent Infrastructure |
| **v0.4.0** | Semantic Drift Detection & Eval Dataset Exporter | ⏳ **Planned** | Next Up |
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

## ✅ v0.2.1 — Hardened Sanitizer & Replay Determinism (Shipped)
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

## 🚀 v0.3.0 — MCP Protocol Replay & Official GitHub Action (Shipped)
- [x] **Model Context Protocol (MCP) Replay**: Deterministically record and replay MCP tool invocations and server sessions (`RerunnerMCPClient`, `@record_mcp_tool`)
- [x] **Official GitHub Action (`action.yml`)**: Zero-config marketplace action for cassette caching, HMAC verification, and CI cost summaries
- [x] **CI Cost & Token Savings CLI**: `rerunner cost` reporting exact prompt/completion tokens and avoided API spend to `$GITHUB_STEP_SUMMARY`
- [x] **Microsoft AutoGen & Semantic Kernel Wrappers**: 1-line agent wrapping via `wrap_autogen_agent()` and `wrap_semantic_kernel()`
- [x] **LangChain / LangGraph Model Direct Attachment**: `wrap_langchain_model()` attaching transports directly to chat models
- [x] **Anthropic Message Batches Offline Mocker**: `mock_anthropic_batch_response()` for offline eval replay
- [x] **Enterprise PII & Presidio Pipeline**: `sanitize_pii()` with US SSN and optional Presidio analyzer support
- [x] **Cassette Scrub & Doctor CLI**: `rerunner doctor` and `rerunner scrub` commands to audit existing cassettes for secrets and re-sign cryptographic integrity

---

## ⏳ v0.4.0 — Semantic Drift Detection & Eval Exporter (In Progress)
- [x] **Semantic Drift Tolerant Replay Matching**: Embedding and n-gram cosine similarity matching allowing prompt phrasing updates without failing CI (RFC #35)
- [x] **Real-Time Terminal TUI Flight Deck**: Interactive erunner tui\ dashboard for visually inspecting multi-agent trajectories (Issue #36)
- [x] **Enterprise Multi-Cloud Backends**: Microsoft Azure Blob Storage (\z://\) and AWS Bedrock Converse API adapter
- [x] **Pluggable Sether PII Redaction Backend**: Protocol-based international phone and credit card masking (PR #37)
- [ ] **Cassette-to-Eval Dataset Exporter**: Convert recorded agent trajectories into evaluation regression datasets (JSONL, HuggingFace, Argilla)

---

## 🎯 v1.0.0 — Centralized Replay Registry & Web Flight Deck (Future Vision)
- [ ] **Centralized Replay Registry**: Multi-developer cassette sharing with automatic versioning and CI deduplication
- [ ] **Web Flight Deck UI**: Interactive browser visualizer for scrubbing through multi-step agent executions and tool calls
- [ ] **Automated Mock Synthesis**: Generate synthetic edge-case cassettes without making any live LLM calls

---

## 🤝 Contributing & Submitting RFCs

We actively invite community contributions:
1. Check the [Contributor Quest Board](CONTRIBUTING.md#contributor-quests) for starter and intermediate issues.
2. For architectural proposals, open an [RFC (Request for Comments)](.github/ISSUE_TEMPLATE/rfc.yml).
3. Review our [Contributing Guide](CONTRIBUTING.md) for code standards and setup instructions.
