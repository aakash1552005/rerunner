# Rerunner Roadmap

Our objective is to become the de-facto standard deterministic test runner and flight recorder for agentic AI applications.

## v0.1.0 — Core Replay Engine (Current)
- [x] Modern PEP 621 packaging and typed architecture
- [ ] Pydantic v2 Cassette schema (JSONL streaming format)
- [ ] Cryptographic SHA-256 tamper-evident hash chaining
- [ ] Synchronous `CassetteTransport` (for Anthropic & OpenAI SDKs)
- [ ] Asynchronous `AsyncCassetteTransport`
- [ ] Tolerant request matching (sanitizing volatile headers and session IDs)
- [ ] Fork-from-step engine (replay steps 1..N, execute live from step N+1)
- [ ] `@tool(side_effect=True)` safe stubbing
- [ ] Typer + Rich CLI (`record`, `replay`, `fork`, `diff`, `verify`)
- [ ] Native Pytest plugin (`@pytest.mark.rerunner`)

## v0.2.0 — Extended Ecosystem Integrations
- [ ] First-class LangChain & LangGraph callback hooks
- [ ] LlamaIndex instrumentation hook
- [ ] CrewAI and AutoGen agent runner integrations
- [x] Gzip-compressed cassette archives for large-scale traces (`.jsonl.gz`) *(Shipped in v0.1.1)*

## v0.3.0 — Enterprise Governance
- [ ] Automatic secret & PII redaction pipeline before disk persistence
- [ ] Asymmetric Ed25519 cassette digital signatures for enterprise audit compliance
- [x] Remote cassette caching recipe with GitHub Actions (`actions/cache@v4`) *(Shipped in v0.1.1)*
