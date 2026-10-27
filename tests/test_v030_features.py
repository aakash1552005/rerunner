"""Unit tests for v0.3.0 architectural features: MCP, AutoGen, Semantic Kernel, LangChain model, Batch Mock, Presidio PII, and Cost CLI."""

from __future__ import annotations

from pathlib import Path
import httpx
import pytest
from typer.testing import CliRunner

from rerunner.cli import app
from rerunner.integrations.anthropic import mock_anthropic_batch_response
from rerunner.integrations.autogen import wrap_autogen_agent, wrap_autogen_client
from rerunner.integrations.langchain import wrap_langchain_model
from rerunner.integrations.mcp import RerunnerMCPClient, record_mcp_tool
from rerunner.integrations.semantic_kernel import wrap_semantic_kernel
from rerunner.sanitizer import sanitize_pii

runner = CliRunner()


class DummySubClient:
    def __init__(self) -> None:
        self._client = httpx.Client()


class DummyAutoGenAgent:
    def __init__(self) -> None:
        self.client = type(
            "OpenAIWrapper", (), {"_clients": [DummySubClient(), DummySubClient()]}
        )()


class DummySemanticKernel:
    def __init__(self) -> None:
        self.services = {
            "chat": type("ChatService", (), {"client": httpx.Client()})(),
            "embed": type("EmbedService", (), {"async_client": httpx.AsyncClient()})(),
        }


def test_autogen_agent_and_client_wrapping(temp_cassette_path: Path) -> None:
    agent = DummyAutoGenAgent()
    wrapped_agent = wrap_autogen_agent(agent, temp_cassette_path, mode="record")
    assert wrapped_agent is agent
    for sub in wrapped_agent.client._clients:
        assert hasattr(sub._client, "_transport")

    single_client = DummySubClient()
    wrapped_single = wrap_autogen_client(single_client, temp_cassette_path, mode="replay")
    assert hasattr(wrapped_single._client, "_transport")


def test_semantic_kernel_wrapping(temp_cassette_path: Path) -> None:
    kernel = DummySemanticKernel()
    wrapped_kernel = wrap_semantic_kernel(kernel, temp_cassette_path, mode="record")
    assert hasattr(wrapped_kernel.services["chat"].client, "_transport")
    assert hasattr(wrapped_kernel.services["embed"].async_client, "_transport")


def test_langchain_model_wrapping(temp_cassette_path: Path) -> None:
    class DummyLangChainModel:
        def __init__(self) -> None:
            self.http_client = httpx.Client()
            self.http_async_client = httpx.AsyncClient()

    model = DummyLangChainModel()
    wrapped = wrap_langchain_model(model, str(temp_cassette_path), mode="replay")
    assert hasattr(wrapped.http_client, "_transport")
    assert hasattr(wrapped.http_async_client, "_transport")


def test_mock_anthropic_batch_response() -> None:
    batch = mock_anthropic_batch_response(
        batch_id="msgbatch_xyz", status="ended", total_requests=5, succeeded_requests=5
    )
    assert batch["id"] == "msgbatch_xyz"
    assert batch["processing_status"] == "ended"
    assert batch["request_counts"]["succeeded"] == 5
    assert batch["ended_at"] is not None


def test_mcp_client_record_and_replay(temp_cassette_path: Path) -> None:
    # 1. Record mode
    with RerunnerMCPClient(temp_cassette_path, mode="record") as client:
        result = client.call_tool("read_file", {"path": "/etc/hosts"})
        assert "Mock MCP execution" in result["content"]

    # 2. Replay mode
    with RerunnerMCPClient(temp_cassette_path, mode="replay") as client:
        replayed = client.call_tool("read_file", {"path": "/etc/hosts"})
        assert replayed == result

    # 3. Unrecorded tool in replay mode raises fail-closed error
    with (
        RerunnerMCPClient(temp_cassette_path, mode="replay") as client,
        pytest.raises(RuntimeError, match="Unrecorded MCP tool call"),
    ):
        client.call_tool("unrecorded_tool", {"action": "delete"})


@pytest.mark.asyncio
async def test_async_mcp_client(temp_cassette_path: Path) -> None:
    async with RerunnerMCPClient(temp_cassette_path, mode="record") as client:
        result = await client.a_call_tool("web_search", {"query": "pytest rerunner"})
        assert "web_search" in result["content"]

    async with RerunnerMCPClient(temp_cassette_path, mode="replay") as client:
        replayed = await client.a_call_tool("web_search", {"query": "pytest rerunner"})
        assert replayed == result


def test_record_mcp_tool_decorator(temp_cassette_path: Path) -> None:
    @record_mcp_tool(name="calculate_sum")
    def calculate_sum(a: int, b: int) -> int:
        return a + b

    # When no active cassette, executes directly
    assert calculate_sum(2, 3) == 5

    # In active record cassette
    with RerunnerMCPClient(temp_cassette_path, mode="record"):
        res = calculate_sum(10, 20)
        assert res == 30

    # In replay mode
    with RerunnerMCPClient(temp_cassette_path, mode="replay"):
        res = calculate_sum(10, 20)
        assert res == 30


def test_sanitize_pii_entities() -> None:
    text = "User email is aakash@example.com, ssn: 123-45-6789, phone: 555-123-4567"
    scrubbed = sanitize_pii(text)
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_SSN]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "123-45-6789" not in scrubbed


def test_cli_cost_command(temp_cassette_path: Path) -> None:
    # First record an entry with tokens
    with RerunnerMCPClient(temp_cassette_path, mode="record") as client:
        client.call_tool("demo", {"a": 1})

    result = runner.invoke(app, ["cost", str(temp_cassette_path)])
    assert result.exit_code == 0
    assert "Execution Steps" in result.stdout

    # Test markdown output
    result_md = runner.invoke(app, ["cost", str(temp_cassette_path), "--markdown"])
    assert result_md.exit_code == 0
    assert "### ⚡ Rerunner CI Replay Savings Report" in result_md.stdout
