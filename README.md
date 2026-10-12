<div align="center">

# 📼 Rerunner

**Deterministic flight recorder, replay engine, and CI test runner for AI agents.**

[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: mypy](https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg)](https://mypy-lang.org/)

*Record your AI agent once. Replay forever in CI in 0ms with $0 API tokens.*

</div>

---

## ⚡ The Problem

Building production AI agents requires automated testing and continuous integration (CI). But running multi-step agents in tests creates three massive bottlenecks:

1. **Flaky CI Builds**: LLMs are non-deterministic. Even at `temperature=0`, small prompt variations break downstream assertions.
2. **Exorbitant API Costs**: Re-running an 8-step agent across 50 pull requests burns thousands of dollars in LLM API credits.
3. **Debug Nightmare**: When an agent fails at **Step 5**, you cannot reproduce the bug locally without paying to re-run Steps 1 through 4.

**Rerunner** solves this by providing a zero-overhead, tamper-evident cassette recorder that intercepts `httpx` traffic natively across the **Anthropic Claude SDK**, **OpenAI SDK**, and custom agents.

---

## 🚀 Key Features

* **$0 CI Replays**: Freeze agent runs into append-only JSONL cassettes. Replay in 0ms without hitting external LLM APIs.
* **Fork from Step N**: Replay Steps 1..4 from the cassette for free, and execute Step 5 live against the model with your new prompt or bug fix.
* **Tolerant Request Matching**: Automatically strips volatile nonces, millisecond timestamps, request IDs, and SDK metadata headers (`x-stainless-*`).
* **Side-Effect Safety**: The `@side_effect` decorator prevents destructive external actions (database writes, Slack webhooks, payments) during replays.
* **Cryptographic Integrity**: SHA-256 tamper-evident hash chaining ensures recorded cassettes have not been altered.
* **Native Pytest Integration**: Seamless `@pytest.mark.rerunner` marker and fixtures.

---

## 📊 Comparison

| Capability | `rerunner` | `vcrpy` | `LangSmith` | `LangGraph` |
| :--- | :---: | :---: | :---: | :---: |
| **Primary Focus** | **Deterministic CI Replay** | Generic HTTP | Web Observability | Orchestration |
| **LLM Streaming (SSE) Support** | ✅ **Yes** | ❌ Breaks | ✅ Yes | N/A |
| **Fork-from-Step Execution** | ✅ **Yes** | ❌ No | ❌ No | ⚠️ Graph-locked |
| **Side-Effect Stubbing** | ✅ **Yes** | ❌ No | ❌ No | ❌ No |
| **Zero Infrastructure / $0 Cost** | ✅ **Local JSONL** | ✅ Local YAML | ❌ Cloud / Paid | ❌ Variable |
| **Framework Agnostic** | ✅ **Any httpx SDK** | ✅ HTTP | ⚠️ Complex | ❌ Locked |

---

## 📦 Installation

```bash
pip install rerunner
```

---

## 🛠️ Quickstart

### 1. Recording an Agent Session
Rerunner transparently attaches to standard SDK clients via `httpx.Client(transport=...)`:

```python
import anthropic
import httpx
from rerunner import CassetteTransport

# 1. Record live interactions to a cassette
transport = CassetteTransport("session.jsonl", mode="record")
client = anthropic.Anthropic(http_client=httpx.Client(transport=transport))

response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze quarterly revenue report."}]
)
print(response.content[0].text)
```

### 2. Deterministic $0 Replay in CI
```python
# 2. Replay locally or in CI without spending API tokens or waiting on network
transport = CassetteTransport("session.jsonl", mode="replay")
client = anthropic.Anthropic(http_client=httpx.Client(transport=transport))

# Instant response, zero cost, completely reproducible
response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze quarterly revenue report."}]
)
```

### 3. Forking from Step 3
```python
from rerunner import fork

# Replay steps 1 through 3 from cassette; run step 4 live with your modified prompt
with fork("session.jsonl", step=3) as session:
    client = session.get_client()
    # Steps 1..3 replayed from tape
    # Step 4 executed live against model
```

### Compressed Cassettes

For long-running agent workflows, use the `.jsonl.gz` extension to store cassettes
in gzip-compressed form:

```python
from rerunner import CassetteTransport

transport = CassetteTransport("session.jsonl.gz", mode="record")
```

Rerunner automatically compresses `.jsonl.gz` cassettes when recording and
decompresses them when replaying. The same CLI commands and SHA-256 integrity
verification work with both `.jsonl` and `.jsonl.gz` files:

```bash
rerunner inspect session.jsonl.gz
rerunner verify session.jsonl.gz
rerunner play session.jsonl.gz
```

---

## 🛡️ Guarding Destructive Side-Effects

Ensure your replayed agents don't charge cards or send duplicate Slack messages:

```python
from rerunner import side_effect

@side_effect(name="post_slack_alert")
def send_slack_notification(channel: str, message: str) -> bool:
    # Runs live during recording. During replay, safely returns recorded result!
    return slack_client.chat_postMessage(channel=channel, text=message)
```

---

## 🧪 Pytest Integration

Mark your unit tests with `@pytest.mark.rerunner`:

```python
import pytest

@pytest.mark.rerunner("tests/fixtures/agent_run.jsonl")
def test_agent_decision(rerunner_transport):
    client = openai.OpenAI(http_client=httpx.Client(transport=rerunner_transport))
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Evaluate risk factor"}]
    )
    assert "low risk" in completion.choices[0].message.content.lower()
```

# Run test suite in replay mode (0 network calls, $0 cost)
pytest

# Re-record all cassettes when prompts change intentionally
pytest --rerunner-record
```

---

## ⚡ 1-Line Client Wrappers

Wrap your existing SDK instances with zero configuration:

```python
import anthropic
import openai
from rerunner.integrations import wrap_anthropic, wrap_openai

# Wrap Anthropic client
client_claude = wrap_anthropic(anthropic.Anthropic(), "agent_run.jsonl", mode="replay")

# Wrap OpenAI client
client_openai = wrap_openai(openai.OpenAI(), "agent_run.jsonl", mode="replay")
```

### LangChain & LangGraph Integration
```python
from rerunner.integrations import RerunnerCallbackHandler

handler = RerunnerCallbackHandler("langgraph_agent.jsonl", mode="replay")
agent_executor.invoke({"input": "Fetch stock price"}, config={"callbacks": [handler]})
```

---

## 🔒 Enterprise Secret & PII Sanitization

Never accidentally commit API keys or auth tokens to GitHub. Rerunner automatically scrubs:
* Anthropic API keys (`sk-ant-...`) $\rightarrow$ `[REDACTED_ANTHROPIC_KEY]`
* OpenAI API keys (`sk-proj-...`, `sk-...`) $\rightarrow$ `[REDACTED_OPENAI_KEY]`
* Authorization headers (`Bearer ...`) $\rightarrow$ `Bearer [REDACTED_TOKEN]`
* AWS access keys (`AKIA...`) $\rightarrow$ `[REDACTED_AWS_KEY_ID]`

---

## 💻 CLI Commands

```bash
# Calculate CI cost reductions and token savings
rerunner stats session.jsonl

# Visually play back agent execution steps in terminal
rerunner play session.jsonl

# Inspect cassette details and step sequences
rerunner inspect session.jsonl

# Cryptographically verify tamper-evident hash chain
rerunner verify session.jsonl

# Compare prompt and response divergences between two cassettes
rerunner diff session_v1.jsonl session_v2.jsonl
```

---

## 🤝 Contributing

Contributions from the community and frontier AI research teams are warmly welcomed.
Please review [CONTRIBUTING.md](CONTRIBUTING.md) to set up your development environment.

---

## 📜 License

Rerunner is licensed under the [Apache 2.0 License](LICENSE).
