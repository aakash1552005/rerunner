# Getting Started with `rerunner`: 5-Minute Tutorial

This tutorial walks through using `rerunner` to record real LLM and HTTP interactions and replay them in CI with **$0 token cost** and **zero network dependency**.

---

## 1. Installation

Install `rerunner` from PyPI:

```bash
pip install rerunner
```

To enable cloud storage backends (AWS S3 or Google Cloud Storage):

```bash
pip install "rerunner[s3]"   # For s3:// URIs
pip install "rerunner[gcs]"  # For gs:// URIs
```

---

## 2. Basic Recording & Replay Workflow

`rerunner` records outgoing HTTP requests and incoming responses into deterministic, version-controlled JSONL cassettes.

### Step 1: Record Mode (Generating the Cassette)

Set the recording mode to `record` when running tests locally or against real staging endpoints:

```python
import pytest
from rerunner import Cassette

def test_openai_agent_completion():
    cassette = Cassette("cassettes/openai_agent.jsonl", mode="record")
    with cassette:
        # Real API call runs once and response is recorded
        response = call_llm_agent(prompt="Summarize customer feedback")
        assert response.status == "success"
```

### Step 2: Replay Mode (Zero-Token CI Tests)

In CI or automated test environments, set mode to `replay` (the default):

```python
def test_openai_agent_offline():
    cassette = Cassette("cassettes/openai_agent.jsonl", mode="replay")
    with cassette:
        # Replays exactly what was recorded with zero network calls and 0ms latency
        response = call_llm_agent(prompt="Summarize customer feedback")
        assert response.status == "success"
```

---

## 3. Streaming SSE Token Replay

`rerunner` natively supports Server-Sent Events (SSE) streaming token deltas for streaming agent UIs:

```python
from rerunner import Cassette

def test_streaming_agent():
    cassette = Cassette("cassettes/streaming_agent.jsonl", mode="replay")
    with cassette:
        tokens = []
        for delta in stream_chat_completion(model="gpt-4o", prompt="Hello"):
            tokens.append(delta)
        assert "".join(tokens).startswith("Hello")
```

---

## 4. Built-in Security & PII Sanitization

Before cassettes touch disk or version control, `rerunner` automatically scrubs sensitive keys and customer identifiers:

```python
from rerunner.sanitizer import sanitize_data

raw_payload = {
    "api_key": "sk-proj-abc1234567890",
    "user_email": "john.doe@example.com",
    "credit_card": "4532-1234-5678-9012"
}

clean_payload = sanitize_data(raw_payload)
# Result: API keys and customer PII are replaced with masked tokens like [REDACTED_API_KEY]
```

---

## 5. Next Steps

- Check out [recipes/github-actions.md](recipes/) to configure cassette caching in GitHub Actions.
- View [ONBOARDING.md](ONBOARDING.md) for local development and test suite instructions.
