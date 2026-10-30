# Rerunner v0.3.1 — Interactive Terminal Flight Deck, Azure Blob Storage & AWS Bedrock

We are thrilled to announce **Rerunner v0.3.1**, introducing our new interactive Terminal Flight Deck, native Microsoft Azure Blob Storage caching, and the AWS Bedrock Converse API adapter.

---

## 🚀 What's New in v0.3.1

### 1. 🖥️ Interactive Terminal Flight Deck (`rerunner tui` — Resolves #36)
Inspect complex multi-turn agent execution trajectories directly inside your terminal with an executive multi-pane flight deck:
* **Trajectory Tree View**: Visual tree of all agent steps with request methods, tool badges, HTTP status codes, and latency metrics.
* **Deep Step Inspection**: Inspect prompt bodies, tool arguments, completions, token usage breakdown, and streaming flags.
* **Security & Integrity Badges**: Real-time display of PII redaction audit status and SHA-256 cryptographic chain verification.
```bash
rerunner tui tests/cassettes/agent_run.jsonl
rerunner tui tests/cassettes/agent_run.jsonl --step 2
```

### 2. ☁️ Microsoft Azure Blob Storage Backend (`az://` & `azure://`)
Enterprise teams running on Microsoft Azure can now persist and stream cassettes directly to and from Azure Blob containers:
* Full support for `az://container/blob_name` and `azure://container/blob_name` URIs.
* Configurable via standard `AZURE_STORAGE_CONNECTION_STRING` or `AZURE_STORAGE_ACCOUNT_URL`.
* Install via `pip install rerunner[azure]`.

### 3. 🛡️ AWS Bedrock Adapter & Offline Converse API Mocker
First-class support for teams building on Amazon Bedrock:
* `wrap_bedrock_client()`: Direct deterministic cassette transport attachment for Bedrock HTTP clients and sessions.
* `mock_bedrock_converse_response()`: Generate deterministic AWS Bedrock Converse API response structures for offline CI evaluations without live AWS credentials.
* Install via `pip install rerunner[bedrock]`.

---

## 🧪 Quality & Integrity
* **101 / 101 Unit Tests Passing** across Python 3.11, 3.12, and 3.13.
* **100% Strict Type Checking** (`mypy --strict`) across all 26 source modules.
* **Zero Ruff Diagnostics & Full Code Formatting**.

---

## 📦 Installation
```bash
pip install --upgrade rerunner
```

