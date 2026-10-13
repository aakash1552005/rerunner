# 🗺️ Rerunner Strategic Roadmap

Our mission is to establish **Rerunner** as the industry-standard deterministic test runner, flight recorder, and CI infrastructure for agentic AI applications worldwide.

---

## 🧭 Milestone Overview

| Release | Focus Area | Status | Target Timeline |
| :--- | :--- | :---: | :---: |
| **v0.1.0** | Core Deterministic Replay Engine | ✅ **Shipped** | Q3 2026 |
| **v0.1.1** | Gzip Compression & CI Remote Caching | ✅ **Shipped** | Q4 2026 |
| **v0.2.0** | Observability & Frontier Ecosystem | 🔄 **Current** | Q4 2026 |
| **v0.3.0** | Enterprise Governance & Streaming Replay | ⏳ **Planned** | Q1 2027 |
| **v1.0.0** | Cloud-Native Distributed Flight Recorder | 🎯 **Long-Term** | Q2 2027 |

---

## ✅ v0.1.0 — Core Replay Engine (Completed)
- [x] Modern PEP 621 packaging and strict typed architecture (`pyproject.toml`)
- [x] Pydantic v2 Cassette schema with streaming JSONL persistence format
- [x] Cryptographic SHA-256 tamper-evident hash chaining between execution steps
- [x] Synchronous `CassetteTransport` (for Anthropic & OpenAI SDKs)
- [x] Asynchronous `AsyncCassetteTransport` for async agent runtimes
- [x] Tolerant request matching (stripping volatile nonces, timestamps, and `x-stainless-*` headers)
- [x] Fork-from-step engine (replay steps 1..N from tape, execute live from step N+1)
- [x] `@side_effect` decorator for safe external tool stubbing
- [x] Typer + Rich CLI (`inspect`, `verify`, `play`, `diff`, `stats`)
- [x] Native Pytest plugin (`@pytest.mark.rerunner` fixture & marker)

---

## ✅ v0.1.1 — Compression & Remote Caching (Completed)
- [x] Gzip-compressed cassette archives for large traces (`.jsonl.gz`)
- [x] GitHub Actions remote cassette caching recipe (`actions/cache@v4`)
- [x] Streamlined packaging with automated PyPI publishing workflows

---

## 🔄 v0.2.0 — Observability & Frontier Ecosystem (In Progress)
- [x] **OpenTelemetry (OTel) Export**: `rerunner export-otel` converting cassettes into OTLP-compliant spans for Datadog, Jaeger, Grafana Tempo, and Dynatrace
- [x] **Google GenAI / Vertex AI Adapter**: Zero-friction `wrap_google_genai` / `wrap_vertexai`
- [x] First-class LangChain & LangGraph callback hooks (`RerunnerCallbackHandler`)
- [ ] **LlamaIndex Instrumentation Hook**: Transparent callback handler for index queries
- [ ] **Microsoft AutoGen & Semantic Kernel Interceptors**: Multi-agent orchestration tracing
- [ ] **CrewAI Agent Runner Integration**: Native replay wrapper for multi-role workflows
- [ ] **Official GitHub Action (`rerunner-action`)**: Zero-config marketplace action for cassette caching and drift checks

---

## ⏳ v0.3.0 — Enterprise Governance & Streaming Replay (Planned)
- [ ] **Streaming SSE Token-by-Token Replayer**: Replay `text/event-stream` chunks for live frontend testing with 0 API tokens
- [ ] **Enterprise PII / Secret Sanitization Pipeline**: Pluggable redaction engine using Microsoft Presidio and regex masks
- [ ] **Asymmetric Ed25519 Digital Signatures**: Cryptographically sign cassettes with corporate certs for SOC2/ISO audit compliance
- [ ] **Semantic Drift Detection**: Embedding-based tolerant matching to alert when prompt alterations diverge from cassette intent

---

## 🎯 v1.0.0 — Cloud-Native Distributed Flight Recorder (Future)
- [ ] **Pluggable Remote Cassette Stores**: Direct streaming to AWS S3, Google Cloud Storage (GCS), and Azure Blob
- [ ] **Centralized Replay Registry**: Enterprise team cassette sharing with automatic versioning and CI deduplication
- [ ] **Web Flight Deck UI**: Interactive browser visualizer for scrubbing through multi-step agent executions

---

## 🤝 Contributing & Submitting RFCs

We actively invite engineering teams and research labs to contribute to the roadmap:
1. For architectural proposals, open an [RFC (Request for Comments)](.github/ISSUE_TEMPLATE/rfc.yml).
2. For manageable enhancements, check issues tagged [`good first issue`](https://github.com/aakash1552005/rerunner/labels/good%20first%20issue).

3. Review our [Contributing Guide](CONTRIBUTING.md) for code standards and setup instructions.
