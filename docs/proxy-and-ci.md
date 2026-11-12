# Cross-Language Proxy & CI Viral Loop

## Universal HTTP/SSE Proxy (`rerunner serve`)

Use Rerunner with **TypeScript / Node.js (Vercel AI SDK)**, **Go**, **Rust**, or **Docker microservices** without any Python test code:

```bash
# 1. Record live LLM traffic once
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 \
  rerunner serve tests/cassettes/node_agent.jsonl --mode record --upstream https://api.openai.com

# 2. Replay deterministically in CI (fail-closed 502 on miss, 0 network calls)
OPENAI_BASE_URL=http://127.0.0.1:8080/v1 \
  rerunner serve tests/cassettes/node_agent.jsonl --mode replay
```

Health check endpoint: `GET /__rerunner/health`.

## Sticky GitHub PR Savings Comment (`action.yml`)

Enable `post-pr-comment: 'true'` in your GitHub Actions workflow to upsert a sticky summary comment (`<!-- rerunner-ci-summary -->`) on every PR showing replayed steps, tokens saved, USD avoided, and integrity verification status.

## Self-Contained HTML Flight Trace

Export any cassette into a zero-CDN interactive timeline for CI artifacts and bug reports:

```bash
rerunner inspect tests/cassettes/rag_eval.jsonl --export-html trace.html
```

