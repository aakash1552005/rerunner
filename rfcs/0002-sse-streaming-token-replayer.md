# RFC 0002: Faithful Server-Sent Events (SSE) Streaming Replayer

* **RFC PR:** #11
* **Target Release:** v0.2.2
* **Author(s):** Rerunner Core Architecture Working Group
* **Status:** 🟡 Approved
* **Created:** 2026-10-13

---

## 1. Summary

This RFC specifies the architecture for recording and replaying streaming LLM completions (`stream=True`, `text/event-stream`). It extends the `RecordedResponse` data model to store ordered SSE event chunks and introduces a generator-based streaming replay transport that faithfully yields tokens to SDK consumers without network calls.

---

## 2. Motivation

Modern AI applications (chatbots, real-time code copilots, agent flight dashboards) stream model output to the end user. Today, running automated end-to-end frontend and backend tests against streaming agents either burns live API tokens or fails because standard HTTP mockers return entire payloads in a single batch, masking streaming bugs (e.g., UI rendering race conditions, SSE connection drops).

---

## 3. Technical Specification

### 3.1 Streaming Chunk Persistence Format

When an intercepted response has `content-type: text/event-stream`, Rerunner segments chunks into the `RecordedResponse.chunks` list:

```json
{
  "step": 1,
  "entry_type": "http",
  "request": {
    "method": "POST",
    "url": "https://api.openai.com/v1/chat/completions",
    "body": "{\"stream\": true, \"messages\": [...]}"
  },
  "response": {
    "status_code": 200,
    "headers": {"content-type": "text/event-stream"},
    "is_streaming": true,
    "chunks": [
      "data: {\"choices\": [{\"delta\": {\"content\": \"Hello\"}}]}\n\n",
      "data: {\"choices\": [{\"delta\": {\"content\": \" world\"}}]}\n\n",
      "data: [DONE]\n\n"
    ]
  }
}
```

### 3.2 Streaming Transport Generator

During replay mode, `CassetteTransport.handle_request()` returns an `httpx.Response` wrapping an iterator stream:

```python
class StreamingByteIterator:
    def __init__(self, chunks: list[str], chunk_delay_ms: int = 0) -> None:
        self.chunks = chunks
        self.chunk_delay_ms = chunk_delay_ms

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            if self.chunk_delay_ms > 0:
                time.sleep(self.chunk_delay_ms / 1000.0)
            yield chunk.encode("utf-8")
```

---

## 4. Implementation Plan

- [ ] Add `is_streaming` detection and chunk capture to `CassetteTransport`
- [ ] Add `StreamingByteIterator` response builder in `CassetteTransport.handle_request`
- [ ] Implement asynchronous streaming generator for `AsyncCassetteTransport`
- [ ] Add end-to-end streaming tests with OpenAI & Anthropic SDKs in `tests/test_streaming.py`
