# Rerunner

**Deterministic flight recorder, replay engine, and CI test runner for AI agents.**

Record your AI agent once. Replay forever in CI in milliseconds with `$0` API tokens, fail-closed `@side_effect` guards, JSON-safe PII redaction, and SHA-256 tamper-evident hash chains.

## 1-Line Quickstart

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## Core Workflows

| Workflow | Command / API | What It Solves |
| :--- | :--- | :--- |
| **Pytest Deterministic Replay** | `@pytest.mark.rerunner` | Zero-network, `$0` CI tests with per-test auto-named cassettes |
| **AI Coding Agent MCP** | `rerunner mcp` / `rerunner setup` | Lets Claude Code, Cursor, and Codex inspect, diff, scrub, and fork cassettes natively |
| **Cross-Language Proxy** | `rerunner serve cassette.jsonl --port 8080` | Replay LLM & SSE traffic for TypeScript, Go, Rust, or Docker via `OPENAI_BASE_URL` |
| **Time-Travel Debugging** | `rerunner fork cassette.jsonl --step 5` | Replay steps 1–5 from tape for free, then run step 6 live against your fix |
| **HTML Flight Trace** | `rerunner inspect cassette.jsonl --export-html trace.html` | Self-contained zero-CDN trace viewer for CI failure artifacts |
| **CI Cost & PR Bot** | `rerunner cost --json` / `action.yml` | Model-aware token & USD savings posted directly as sticky PR comments |

## Next Steps

- Read the [Onboarding Guide](ONBOARDING.md) or [Tutorial](TUTORIAL.md)
- Connect your coding agent with [AI Agents & MCP](mcp-and-agents.md)
- Run Node/TypeScript/Go agents via [Universal Proxy & PR Bot](proxy-and-ci.md)
- Inspect reproducible numbers in [Benchmarks](benchmarks.md)

