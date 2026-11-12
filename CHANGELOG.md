# Changelog

## [0.3.2](https://github.com/aakash1552005/rerunner/compare/v0.3.1...v0.3.2) (2026-11-12)


### Features

* add cassette security pre-commit hook ([#46](https://github.com/aakash1552005/rerunner/issues/46)) ([#65](https://github.com/aakash1552005/rerunner/issues/65)) ([367fd9a](https://github.com/aakash1552005/rerunner/commit/367fd9a92a22c9f0db1966a257294309628ba120))
* **cli:** add '--json' output flag to 'rerunner stats' (closes [#43](https://github.com/aakash1552005/rerunner/issues/43)) ([#50](https://github.com/aakash1552005/rerunner/issues/50)) ([be0b8bc](https://github.com/aakash1552005/rerunner/commit/be0b8bc206b38f2e187c9f6f9b9b579cb8f323fa))
* **cli:** add export-eval command for fine-tuning and benchmark datasets ([2af0997](https://github.com/aakash1552005/rerunner/commit/2af0997c96053c484208e8e72c76fbcf41a4c2d4))
* **enterprise:** add model pricing, ignore-fields, cassette merge, auto-naming, and nightly mutmut ([#93](https://github.com/aakash1552005/rerunner/issues/93)) ([5b40039](https://github.com/aakash1552005/rerunner/commit/5b40039889c0c67554bf20412e05672394113cdd))
* **integrations:** add BaseProviderAdapter protocol and unified rerunner.wrap API ([f4c90cf](https://github.com/aakash1552005/rerunner/commit/f4c90cf3fda92bfe70ed9b8c0dc0741a8ccad4d0))
* **integrations:** add LangGraph multi-agent checkpointer, justfile, and contributor scaffolding ([a9802ca](https://github.com/aakash1552005/rerunner/commit/a9802caab8551d81648545d24400631e6dbb16bf))
* **integrations:** add wrap_cohere for the Cohere SDK (closes [#59](https://github.com/aakash1552005/rerunner/issues/59)) ([#68](https://github.com/aakash1552005/rerunner/issues/68)) ([32ecb11](https://github.com/aakash1552005/rerunner/commit/32ecb11fa8998ed82951d2604ec6030fb8cc941f))
* **matcher:** add semantic drift tolerant replay matching via embeddings and cosine similarity (resolves [#35](https://github.com/aakash1552005/rerunner/issues/35)) ([0cba454](https://github.com/aakash1552005/rerunner/commit/0cba454a763dd1afe0347413ec512ad139bfa698))
* **mcp:** add stdio MCP server, setup wizard, and agent plugins ([#91](https://github.com/aakash1552005/rerunner/issues/91)) ([6a2e9c2](https://github.com/aakash1552005/rerunner/commit/6a2e9c2164f26a259880e34320d8bd0e584db79d))
* **moat:** add requests/aiohttp patchers, Pseudonymizer, Ed25519+Merkle signing, and cached remote storage ([#95](https://github.com/aakash1552005/rerunner/issues/95)) ([ea64efa](https://github.com/aakash1552005/rerunner/commit/ea64efa69716bef7ccd3e57fab8a699d338dd2b2))
* **proxy:** add rerunner serve proxy, trace viewer, sticky PR bot, and conformance tests ([#92](https://github.com/aakash1552005/rerunner/issues/92)) ([056b8ef](https://github.com/aakash1552005/rerunner/commit/056b8ef344d5579fd8943d81d7402d6ecc077ff4))
* **reports:** add standalone HTML cost & token savings report generator (closes [#44](https://github.com/aakash1552005/rerunner/issues/44)) ([aff8663](https://github.com/aakash1552005/rerunner/commit/aff86632e16075b90ed3a47a54aaa7b1f37dee27))
* **sanitizer:** add optional Sether PII redaction backend ([ee90675](https://github.com/aakash1552005/rerunner/commit/ee906759bf1dc5f1eed2513904378d2e2a202b28))
* **sanitizer:** support custom regex patterns via RERUNNER_REDACT_PATTERNS (closes [#49](https://github.com/aakash1552005/rerunner/issues/49)) ([#51](https://github.com/aakash1552005/rerunner/issues/51)) ([30a2b6a](https://github.com/aakash1552005/rerunner/commit/30a2b6a5bfe86b81601c35a188fd8f31dcb6ff51))


### Bug Fixes

* resolve core URI/CLI/plugin bugs and harden CI architecture boundaries ([#90](https://github.com/aakash1552005/rerunner/issues/90)) ([77b87d0](https://github.com/aakash1552005/rerunner/commit/77b87d0a2a2d86d66870a481b6dfc8255caed363))
* **sanitizer:** ensure Presidio operator placeholders match canonical redaction and fallback rules ([aa071e8](https://github.com/aakash1552005/rerunner/commit/aa071e879d49bc85a21bc7f3bbc20a9c55f68013))
* **sanitizer:** keep records whose keys sanitize to the same placeholder ([31ccfda](https://github.com/aakash1552005/rerunner/commit/31ccfda0f45f0ace77db996ad9a88b8c3eea9b98))
* **sanitizer:** redact split stream values and preserve colliding keys ([7aefa2e](https://github.com/aakash1552005/rerunner/commit/7aefa2e363139509b44eef20596cd6050f2d11af))
* **sanitizer:** redact values split across streamed chunks ([27b1ecf](https://github.com/aakash1552005/rerunner/commit/27b1ecfb94ed71fbe29c6229b5e412a89287794a))
* **security:** use parsed URL hostname checks in otel provider detection ([#97](https://github.com/aakash1552005/rerunner/issues/97)) ([dd2dd67](https://github.com/aakash1552005/rerunner/commit/dd2dd67ba1ca62854b80c4c5729b61fd2632b7ad))
* **types:** resolve strict mypy issues and bandit SAST warnings ([0f3cba9](https://github.com/aakash1552005/rerunner/commit/0f3cba9f043eaba4d9a78a40fb01d6b92e1d46f8))


### Performance Improvements

* **sanitizer:** bound the rescan when settling streamed chunks ([2afa2a4](https://github.com/aakash1552005/rerunner/commit/2afa2a4ddee333926da188db5ffea10b67bb71b0))
* **sanitizer:** confirm settle points that end in a redacted value ([f1800c8](https://github.com/aakash1552005/rerunner/commit/f1800c8efccd0cc36b791dc481ae8a04eaec6297))


### Documentation

* add latency & cost benchmarks and runnable examples gallery ([075b46e](https://github.com/aakash1552005/rerunner/commit/075b46e62cc504d8d882d9bb5a6ce1781de1db7e))
* **authors:** recognize community contributor [@emorilebo](https://github.com/emorilebo) for Sether PII backend (PR [#37](https://github.com/aakash1552005/rerunner/issues/37)) ([65c3bb7](https://github.com/aakash1552005/rerunner/commit/65c3bb7456fe784d336c11e72476eefdc4ff0a13))
* **examples:** add CrewAI multi-agent integration example and tutorial ([#42](https://github.com/aakash1552005/rerunner/issues/42)) ([#58](https://github.com/aakash1552005/rerunner/issues/58)) ([78d43a4](https://github.com/aakash1552005/rerunner/commit/78d43a420aac6e73271db698ab36e1ae3cff2404))
* **launch:** add MkDocs Material site, benchmark SVGs, localized READMEs, release-please, and CodeQL ([#94](https://github.com/aakash1552005/rerunner/issues/94)) ([3119ba0](https://github.com/aakash1552005/rerunner/commit/3119ba016a184f3b670b23c53d74aaf8ae8b1482))
* **readme:** highlight interactive TUI flight deck, Azure Blob and AWS Bedrock ([b9a4a54](https://github.com/aakash1552005/rerunner/commit/b9a4a54f384ead90ba76d38b0f6281f5edb29d9e))
