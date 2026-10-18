<div align="center">

# 📼 Rerunner

**Deterministic flight recorder, replay engine, and CI test runner for AI agents.**

[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/aakash1552005/rerunner/actions)
[![Release](https://img.shields.io/badge/release-v0.2.1-blue.svg)](https://github.com/aakash1552005/rerunner/releases)
[![PyPI](https://img.shields.io/pypi/v/rerunner.svg)](https://pypi.org/project/rerunner/)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: mypy](https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg)](https://mypy-lang.org/)

*Record your AI agent once. Replay forever in CI in 0ms with $0 API tokens.*

</div>

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │  $ pytest tests/test_agent.py -v                                       │
  │                                                                        │
  │  tests/test_agent.py::test_rag_pipeline ....................... [100%] │
  │                                                                        │
  │  📼 [rerunner] Loaded cassette: tests/cassettes/rag_eval.jsonl        │
  │  ⚡ Replayed: 8 LLM calls (OpenAI gpt-4o + Anthropic Claude 3.7)      │
  │  🛡️ PII Check: 0 leaks | Hash Chain: Verified [3a8f9c1b]              │
  │  ⏱️ Duration: 0.04s (Saved 18.4s of live network calls)               │
  │  💰 Token Cost: $0.00 (Saved $0.24 API credits)                       │
  │                                                                        │
  │  ========================= 1 passed in 0.04s ========================= │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ The Problem

Testing production AI agents and running them in Continuous Integration (CI) creates major bottlenecks:

1. **Flaky CI Builds**: LLMs are non-deterministic. Small model drift breaks downstream assertions across pull requests.
2. **High API Costs**: Running an 8-step agent across dozens of CI runs drains thousands of dollars in LLM API credits.
3. **Reproducibility & Debugging**: When an agent fails at **Step 5**, you cannot reproduce the bug locally without re-running Steps 1 through 4 live.

**Rerunner** solves this by providing a lightweight cassette recorder that intercepts `httpx` traffic natively across the **Anthropic Claude SDK**, **OpenAI SDK**, **Google GenAI SDK**, and custom agent frameworks.

---

## 🚀 Key Features

* **$0 CI Replays**: Record agent interactions to append-only JSONL cassettes and replay in CI with zero network latency and $0 token spend.
* **Fork-from-Step Replay**: Replay steps 1..N from tape for free, and execute step N+1 live against the model with a modified prompt or code fix.
* **Fail-Closed Side-Effect Guard**: The `@side_effect` decorator prevents destructive external actions (database updates, payments, webhooks) during replays, aborting immediately if an unrecorded side-effect is reached.
* **Per-Key Cursor Matching**: Accurately replays repeated identical requests and retry loops in recorded sequential order.
* **Streaming SSE Replay**: Records `text/event-stream` chunks and replays token-by-token with optional simulated network latency (`chunk_delay_ms`).
* **JSON-Safe Secret Redaction**: Automatically scrubs API keys (`sk-ant-...`, `sk-proj-...`, `AIza...`), Bearer tokens, and URL parameters while strictly preserving JSON syntax and numeric values (such as Unix timestamps).
* **Tamper-Evident Integrity**: SHA-256 hash chaining detects accidental line edits, with optional HMAC-SHA256 digital signing via `RERUNNER_HMAC_KEY`.
* **Pytest Integration**: Seamless `@pytest.mark.rerunner` marker and `rerunner_transport` fixture.
* **Pluggable Storage**: Store cassettes locally, in compressed formats (`.jsonl.gz`, `.jsonl.zst`), or directly in AWS S3 (`s3://`) and Google Cloud Storage (`gs://`).

---

## 📊 Comparison

| Feature | `rerunner` | `vcrpy` / `pytest-recording` | `respx` | `LangGraph` Checkpoints |
| :--- | :---: | :---: | :---: | :---: |
| **Primary Focus** | **Deterministic Agent CI Replay** | Generic HTTP recording | Manual HTTPX mocking | Orchestration State |
| **LLM Streaming (SSE) Support** | ✅ **Native SSE token stream replay** | ⚠️ Buffers raw byte stream | ⚠️ Manual stream setup | N/A |
| **Fork-from-Step Execution** | ✅ **Replay 1..N, execute live from N+1** | ❌ No | ❌ No | ⚠️ Subgraph re-execution |
| **Fail-Closed Side-Effect Guard** | ✅ **Yes (`@side_effect`)** | ❌ No | ❌ No | ❌ No |
| **Secret & URL Redaction** | ✅ **Built-in JSON & URL redactor** | ⚠️ Custom filter functions | ❌ No | ❌ No |
| **Zero Cloud Infrastructure** | ✅ **Local JSONL / S3 / GCS** | ✅ Local YAML | ✅ In-memory | ⚠️ Postgres / Redis required |
| **Framework Agnostic** | ✅ **Any HTTPX-based SDK** | ✅ HTTP socket level | ✅ HTTPX | ❌ Locked to LangGraph |

---

## 🔍 Scope & Limitations

* **Transport Layer**: Rerunner intercepts `httpx.BaseTransport` and `httpx.AsyncBaseTransport`. This covers the official Python SDKs for Anthropic Claude, OpenAI, and Google GenAI.
* **Other HTTP Libraries**: SDKs that rely exclusively on standard library `urllib`, `requests`, or raw gRPC (such as AWS Bedrock via `boto3` or Vertex AI gRPC channels) require configuring custom HTTPX client wrappers or transport bridges.

---

## 📦 Installation

```bash
# Standard installation
pip install rerunner

# With optional extras
pip install "rerunner[s3]"         # AWS S3 remote storage
pip install "rerunner[gcs]"        # Google Cloud Storage
pip install "rerunner[zstd]"       # Zstandard compression (.zst)
pip install "rerunner[all]"        # All storage & compression extras
```

---

## 🛠️ Quickstart

### 1. Recording an Agent Session
Rerunner transparently attaches to SDK clients via `httpx.Client(transport=...)`:

```python
import anthropic
import httpx
from rerunner import CassetteTransport

# 1. Record live interactions to a cassette
transport = CassetteTransport("session.jsonl", mode="record")
client = anthropic.Anthropic(http_client=httpx.Client(transport=transport))

response = client.messages.create(
    model="claude-3-7-sonnet-20250219",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze quarterly revenue report."}],
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
    model="claude-3-7-sonnet-20250219",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Analyze quarterly revenue report."}],
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

### 4. Streaming SSE Replay
Rerunner records responses with `text/event-stream` headers as individual chunks and yields them through HTTPX's streaming interface during replay:

```python
import httpx
import openai
from rerunner import CassetteTransport

transport = CassetteTransport("agent_run.jsonl", mode="replay", chunk_delay_ms=20)
client = openai.OpenAI(
    api_key="not-used-during-replay",
    http_client=httpx.Client(transport=transport),
)

stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Summarize this report."}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## 🛡️ Guarding External Side-Effects

Use `@side_effect` to prevent destructive actions (database writes, notifications, payment charges) during replay:

```python
from rerunner import side_effect


@side_effect(name="charge_customer")
def charge_card(user_id: str, amount: float) -> str:
    # Runs live during recording.
    # During replay, returns recorded result and never touches Stripe.
    # If no recorded call matches, fails closed by raising SideEffectError!
    return stripe.charge(user_id, amount)
```

---

## 🧪 Pytest Integration

Mark your tests with `@pytest.mark.rerunner`:

```python
import httpx
import openai
import pytest


@pytest.mark.rerunner("tests/fixtures/agent_run.jsonl")
def test_agent_decision(rerunner_transport):
    client = openai.OpenAI(http_client=httpx.Client(transport=rerunner_transport))
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Evaluate risk factor"}],
    )
    assert "low risk" in completion.choices[0].message.content.lower()
```

Run tests from the terminal:

```bash
# Run test suite in replay mode (0 network calls, $0 token cost)
pytest

# Re-record cassettes when prompts change intentionally
pytest --rerunner-record
```

---

## ⚡ 1-Line Client Wrappers

Wrap existing SDK clients directly:

```python
import anthropic
import openai
from rerunner.integrations import wrap_anthropic, wrap_openai

# Wrap Anthropic Claude client (sync or async)
client_claude = wrap_anthropic(anthropic.Anthropic(), "agent_run.jsonl", mode="replay")

# Wrap OpenAI client (sync or async)
client_openai = wrap_openai(openai.OpenAI(), "agent_run.jsonl", mode="replay")
```

### LangChain & LangGraph Integration
```python
from rerunner.integrations import RerunnerCallbackHandler

handler = RerunnerCallbackHandler("langgraph_agent.jsonl", mode="replay")
agent_executor.invoke({"input": "Fetch stock price"}, config={"callbacks": [handler]})
```

---

## 🔒 Automated Secret & URL Sanitization

Rerunner automatically redacts sensitive data before persisting cassettes:
* **Anthropic Keys** (`sk-ant-...`) $\rightarrow$ `[REDACTED_ANTHROPIC_KEY]`
* **OpenAI Keys** (`sk-proj-...`, `sk-...`) $\rightarrow$ `[REDACTED_OPENAI_KEY]`
* **Google API Keys** (`AIza...`) $\rightarrow$ `[REDACTED_GOOGLE_API_KEY]`
* **URL Query Parameters** (`?key=...`, `?api_key=...`, `?token=...`) $\rightarrow$ `[REDACTED_API_KEY]`
* **Authorization Headers** (`Bearer ...`) $\rightarrow$ `Bearer [REDACTED_TOKEN]`
* **Credit Cards** (validated with Luhn checksum) $\rightarrow$ `[REDACTED_CREDIT_CARD]`
* **JSON Structure Preservation**: Numeric fields (like `"created": 1730000000`) remain valid numbers.

---

## 💻 CLI Commands

```bash
# Calculate CI cost reductions and token savings
rerunner stats session.jsonl

# Visually play back agent execution steps in terminal
rerunner play session.jsonl

# Inspect cassette details and step sequences
rerunner inspect session.jsonl

# Export cassette into OpenTelemetry OTLP trace format
rerunner export-otel session.jsonl -o session.otel.json

# Verify cassette integrity
rerunner verify session.jsonl

# Compare prompt and response divergences between two cassettes
rerunner diff session_v1.jsonl session_v2.jsonl
```

---

## 🤝 Contributing

Contributions are welcomed:
* 🛠️ **Developer Setup**: Read [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup and testing instructions.
* 🏷️ **Starter Issues**: Look for tasks labeled [`good first issue`](https://github.com/aakash1552005/rerunner/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
* 🗺️ **Roadmap**: Check [ROADMAP.md](ROADMAP.md) for upcoming milestones.
* 📜 **Governance**: Review [GOVERNANCE.md](GOVERNANCE.md).

---

## 📜 License

Rerunner is licensed under the [Apache 2.0 License](LICENSE).
