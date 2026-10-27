"""Shared fixtures and mocks for the Rerunner test suite."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import httpx
import pytest


class MockRealTransport(httpx.BaseTransport):
    """Mock transport that simulates an external LLM API without network calls."""

    def __init__(self) -> None:
        self.call_count = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json", "x-request-id": f"req_{self.call_count}"},
            content=b'{"id": "chatcmpl-test", "choices": [{"message": {"content": "Hello AI World"}}]}',
            request=request,
        )


class MockAsyncRealTransport(httpx.AsyncBaseTransport):
    """Asynchronous mock transport simulating an external LLM API."""

    def __init__(self) -> None:
        self.call_count = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=b'{"choices": [{"message": {"content": "Async Hello"}}]}',
            request=request,
        )


@pytest.fixture
def mock_transport() -> MockRealTransport:
    return MockRealTransport()


@pytest.fixture
def mock_async_transport() -> MockAsyncRealTransport:
    return MockAsyncRealTransport()


@pytest.fixture
def temp_cassette_path(tmp_path: Path) -> Path:
    return tmp_path / "test_session.jsonl"


@pytest.fixture(autouse=True)
def _isolate_rerunner_context() -> Generator[None, None, None]:
    """Ensure contextvars are never leaked between tests in the suite."""
    from rerunner.side_effects import set_active_cassette

    yield
    set_active_cassette(None)
