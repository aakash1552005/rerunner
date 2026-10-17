<div align="center">

# 📼 Rerunner

**Deterministic flight recorder, replay engine, and CI test runner for AI agents.**

[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](https://github.com/aakash1552005/rerunner/actions)
[![Release](https://img.shields.io/badge/release-v0.2.1-blue.svg)](https://github.com/aakash1552005/rerunner/releases)
[![PyPI](https://img.shields.io/pypi/v/rerunner.svg)](https://pypi.org/project/rerunner/)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/aakash1552005/rerunner)
[![Python Version](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Governance](https://img.shields.io/badge/governance-CNCF%20Style-purple.svg)](GOVERNANCE.md)
[![RFCs](https://img.shields.io/badge/architecture-Enterprise%20RFCs-purple.svg)](rfcs/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type Checked: mypy](https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg)](https://mypy-lang.org/)

*Record your AI agent once. Replay forever in CI in 0ms with $0 API tokens.*

</div>

```text
  ┌────────────────────────────────────────────────────────────────────────┐
  │  $ pytest tests/test_agent.py -v --rerunner-mode=replay                │
  │                                                                        │
  │  tests/test_agent.py::test_rag_pipeline ....................... [100%] │
  │                                                                        │
  │  📼 [rerunner] Loaded cassette: tests/cassettes/rag_eval.jsonl        │
  │  ⚡ Replayed: 8 LLM calls (OpenAI gpt-4o + Anthropic Claude 3.5)      │
  │  🛡️ PII Check: 0 leaks | SHA-256: Verified [3a8f9c1b]                 │
  │  ⏱️ Duration: 0.04s (Saved 18.4s of live network calls)               │
  │  💰 Token Cost: $0.00 (Saved $0.24 API credits)                       │
  │                                                                        │
  │  ========================= 1 passed in 0.04s ========================= │
  └────────────────────────────────────────────────────────────────────────┘
```

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

### Streaming Replay

Rerunner records responses with a `text/event-stream` content type as individual
chunks. During replay, those chunks are yielded through HTTPX's streaming
interface without making another network request.

```python
import httpx
import openai

from rerunner import CassetteTransport

transport = CassetteTransport(
    "agent_run.jsonl",
    mode="replay",
)

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

`AsyncCassetteTransport` provides the equivalent asynchronous streaming
interface for consumers using `async for`.

To simulate the timing of a live stream in UI tests, configure a delay between
replayed chunks:

```python
transport = CassetteTransport(
    "agent_run.jsonl",
    mode="replay",
    chunk_delay_ms=25,
)
```

The first chunk is returned immediately. Each subsequent chunk is delayed by
the configured number of milliseconds. The default value is `0`, which adds no
intentional delay. Buffered responses continue to use the existing replay
behavior.

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

For a reusable GitHub Actions workflow that restores recorded cassettes before
replay tests, see the [GitHub Actions cassette caching recipe](docs/recipes/github_actions_caching.md).

---

## ⚡ 1-Line Client Wrappers

Wrap your existing SDK instances with zero configuration:

```python
import anthropic
import openai
from google import genai
from rerunner.integrations import wrap_anthropic, wrap_google_genai, wrap_openai

# Wrap Anthropic Claude client
client_claude = wrap_anthropic(anthropic.Anthropic(), "agent_run.jsonl", mode="replay")

# Wrap OpenAI client
client_openai = wrap_openai(openai.OpenAI(), "agent_run.jsonl", mode="replay")

# Wrap Google GenAI / Vertex AI Gemini client
client_gemini = wrap_google_genai(genai.Client(), "agent_run.jsonl", mode="replay")
```

### LangChain & LangGraph Integration
```python
from rerunner.integrations import RerunnerCallbackHandler

handler = RerunnerCallbackHandler("langgraph_agent.jsonl", mode="replay")
agent_executor.invoke({"input": "Fetch stock price"}, config={"callbacks": [handler]})
```

---

## 🔭 OpenTelemetry (OTel) Distributed Traces

Bridge testing and enterprise observability. Export cassettes to standardized OpenTelemetry trace JSON compatible with **Datadog, Jaeger, Grafana Tempo, and Dynatrace**:

```bash
# Export cassette to OpenTelemetry trace
rerunner export-otel session.jsonl --output trace.otel.json --service-name "fraud-agent"
```

Or programmatically in Python:
```python
from rerunner import export_cassette_to_otel_file

export_cassette_to_otel_file("session.jsonl", "trace.otel.json", service_name="fraud-agent")
```

---

## 🔒 Enterprise Secret & PII Sanitization

Never accidentally commit API keys or auth tokens to GitHub. Rerunner automatically scrubs:
* Anthropic API keys (`sk-ant-...`) $\rightarrow$ `[REDACTED_ANTHROPIC_KEY]`
* OpenAI API keys (`sk-proj-...`, `sk-...`) $\rightarrow$ `[REDACTED_OPENAI_KEY]`
* Google AI Studio / Gemini keys $\rightarrow$ `[REDACTED_API_KEY]`
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

# Export cassette into OpenTelemetry OTLP trace format
rerunner export-otel session.jsonl -o session.otel.json

# Cryptographically verify tamper-evident hash chain
rerunner verify session.jsonl

# Compare prompt and response divergences between two cassettes
rerunner diff session_v1.jsonl session_v2.jsonl
```


---

## 🤝 Contributing & Enterprise Architecture

Contributions from the open-source community and frontier AI research teams are warmly welcomed:

* 🚀 **One-Click Cloud Dev**: Launch an instant ready-to-code workspace via [GitHub Codespaces](https://codespaces.new/aakash1552005/rerunner).
* 📜 **Governance & Maintainership**: Review our [CNCF-style Governance Model & Review SLA](GOVERNANCE.md).
* 🚀 **First-Time Contributors**: Follow our [5-Minute Onboarding Guide](docs/ONBOARDING.md) to set up and submit your first PR.
* 🏷️ **Good First Issues**: Grab starter tasks on [GitHub Issues](https://github.com/aakash1552005/rerunner/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).
* 🛠️ **Developer Setup**: Read [CONTRIBUTING.md](CONTRIBUTING.md) for environment setup and linting rules.
* 🗺️ **Strategic Vision**: Review our [ROADMAP.md](ROADMAP.md) for planned milestones.
* 🏛️ **Enterprise RFCs**: Propose or review major architectural designs in our [RFC Directory](rfcs/) or open an [RFC Issue](https://github.com/aakash1552005/rerunner/issues/new?template=rfc.yml).
* 🏆 **Hall of Fame**: Meet the community members in [AUTHORS.md](AUTHORS.md).

---

## 📜 License

Rerunner is licensed under the [Apache 2.0 License](LICENSE).

