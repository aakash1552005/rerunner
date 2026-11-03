# 📼 Rerunner Runnable Examples & Cookbooks

This directory contains standalone, production-ready examples demonstrating how to use Rerunner across popular AI frameworks and protocols.

Every example is runnable locally out of the box using `uv` or standard `python`.

---

## 📂 Cookbooks Overview

| Example | Framework / Topic | Description | Command |
| :--- | :--- | :--- | :--- |
| **[`01_openai_quickstart.py`](01_openai_quickstart.py)** | **OpenAI SDK** | Basic recording & replay with zero external latency and $0 token spend. | `uv run python examples/01_openai_quickstart.py` |
| **[`02_anthropic_sse_streaming.py`](02_anthropic_sse_streaming.py)** | **Anthropic Claude SDK** | Token-by-token Server-Sent Events (SSE) streaming replay with realistic simulated delay. | `uv run python examples/02_anthropic_sse_streaming.py` |
| **[`03_mcp_sqlite_replayer.py`](03_mcp_sqlite_replayer.py)** | **Model Context Protocol (MCP)** | Recording and replaying MCP database/API tool executions deterministically without touching external backends. | `uv run python examples/03_mcp_sqlite_replayer.py` |
| **[`04_chaos_fault_injection.py`](04_chaos_fault_injection.py)** | **Chaos Engineering** | Simulating upstream API 429 rate limits, exponential backoff retries, and offline failover testing. | `uv run python examples/04_chaos_fault_injection.py` |

---

## 🚀 Running the Cookbooks

### Prerequisites
Install dependencies using `uv` (recommended) or `pip`:
```bash
uv sync --all-extras
```

### Run Any Example:
```bash
uv run python examples/01_openai_quickstart.py
uv run python examples/02_anthropic_sse_streaming.py
uv run python examples/03_mcp_sqlite_replayer.py
uv run python examples/04_chaos_fault_injection.py
```

All examples create isolated temporary cassettes and clean up automatically.

