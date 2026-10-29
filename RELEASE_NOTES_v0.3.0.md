# 🚀 Rerunner v0.3.0 — Model Context Protocol (MCP) Replay & Official GitHub Action

We are thrilled to announce **Rerunner v0.3.0**! This milestone establishes Rerunner as the leading deterministic test runner and CI infrastructure for modern AI agents, introducing native **MCP protocol replay**, our **official GitHub Action**, **Microsoft AutoGen & Semantic Kernel** adapters, and **enterprise PII redaction**.

---

## 🌟 What's New in v0.3.0

### 🤖 1. Model Context Protocol (MCP) Replay Support
Record and deterministically replay MCP tool calls, prompts, and resources offline in CI with **$0 token costs and 0ms latency** without launching local server subprocesses or Docker containers.

```python
from rerunner.integrations import RerunnerMCPClient, record_mcp_tool

with RerunnerMCPClient("cassettes/mcp_flight.jsonl", mode="replay") as mcp:
    result = mcp.call_tool("read_file", {"path": "/workspace/data.json"})
```

### ⚡ 2. Official GitHub Marketplace Action
Add zero-latency cassette caching and executive token cost summaries to your CI in 3 lines:

```yaml
- name: Rerunner CI Replay & Cache
  uses: aakash1552005/rerunner@v0.3.0
  with:
    cassette-dir: 'tests/cassettes'
    report-savings: 'true'
```

### 💰 3. CI Token & Cost Savings CLI (`rerunner cost`)
Automatically calculate exact prompt/completion tokens, latency avoided, and dollar savings across all cassettes, posting a clean markdown summary table directly to `$GITHUB_STEP_SUMMARY`.

### 🤝 4. Microsoft AutoGen (AG2) & Semantic Kernel Wrappers
1-line client interception for multi-agent workflows:
* `wrap_autogen_agent(agent, cassette_path)`
* `wrap_semantic_kernel(kernel, cassette_path)`
* `wrap_langchain_model(model, cassette_path)`

### 🛡️ 5. Enterprise PII & Presidio Redaction Pipeline
Comprehensive redaction for US SSNs, emails, phone numbers, and Luhn-validated credit cards with optional Microsoft Presidio analyzer integration.

### 📦 6. Claude 3.5/3.7 Message Batches Offline Mocker
Deterministic mock response generator (`mock_anthropic_batch_response()`) allowing large-scale Anthropic Batch API test suites to replay instantly without queue delays.

---

## 🗺️ Open Source Contributor Quest Board

We are building a global community for agent reliability! Check out our new [Contributor Quest Board](https://github.com/aakash1552005/rerunner/blob/main/CONTRIBUTING.md#contributor-quest-board) to pick up beginner, intermediate, and advanced open-source quests:

* 🟢 **CrewAI Flight Demo**
* 🟢 **CLI `--json` Output Flag**
* 🟡 **LiteLLM Proxy Adapter**
* 🟡 **Ollama Local GPU Model Replayer**
* 🔴 **Cassette-to-Eval Benchmark Exporter**

All merged PRs are recognized in the [AUTHORS.md](https://github.com/aakash1552005/rerunner/blob/main/AUTHORS.md) Hall of Fame!

---

## 📦 Installation

```bash
pip install --upgrade rerunner
```
