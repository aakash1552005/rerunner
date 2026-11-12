# AI Agents & MCP Integration

Rerunner ships an out-of-the-box **Model Context Protocol (MCP)** stdio server and a 1-command setup wizard so coding agents in **Claude Code**, **Cursor**, and **Codex** can inspect, diff, scrub, and debug failing cassettes autonomously.

## 1-Command Setup

```bash
rerunner setup --clients claude-project,cursor,codex
```

Before modifying any existing config file (`.mcp.json`, `~/.claude.json`, `.cursor/mcp.json`, `.codex/config.toml`), `rerunner setup` creates a `.bak` backup and merges the `rerunner` MCP entry idempotently.

## Available MCP Tools (`rerunner mcp`)

| Tool | Purpose |
| :--- | :--- |
| `inspect_cassette` | Summarize entry count, entry types, tokens, and SHA-256 chain status |
| `read_cassette_step` | Read a single recorded step (request, response, metadata) |
| `diff_cassettes` | Compare two cassettes step-by-step to pinpoint prompt/output drift |
| `fork_and_replay_step` | Truncate a cassette after step `N` to replay up to `N` and re-run `N+1` live |
| `scaffold_pytest_regression` | Generate a deterministic `pytest` regression test from a cassette |
| `verify_cassette` | Verify SHA-256 hash chain and optional HMAC-SHA256 signature |
| `scrub_cassette` | Redact PII/secrets and optionally re-chain integrity hashes |
| `estimate_savings` | Compute model-aware token and USD cost savings |

## Plugin Manifests & Skills

Rerunner includes native manifests for agent marketplaces:

- `server.json` (MCP Registry)
- `.claude-plugin/marketplace.json` & `.claude-plugin/plugin.json`
- `.codex-plugin/plugin.json` & `.codex-plugin/mcp.json`
- `skills/rerunner/SKILL.md`

