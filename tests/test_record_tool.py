"""Tests verifying @record_tool for both synchronous and asynchronous functions."""

from __future__ import annotations

from pathlib import Path
import pytest

from rerunner import Session, SideEffectError, record_tool


def test_sync_record_tool(tmp_path: Path) -> None:
    cassette_file = tmp_path / "sync_tool.jsonl"
    execution_count = 0

    @record_tool(name="database_query")
    def run_query(sql: str) -> dict[str, str]:
        nonlocal execution_count
        execution_count += 1
        return {"result": f"rows for {sql}"}

    # 1. Record mode
    with Session(cassette_file, mode="record") as session:
        res = run_query("SELECT * FROM users")
        assert res == {"result": "rows for SELECT * FROM users"}
        assert execution_count == 1
        assert len(session.cassette.entries) == 1
        assert session.cassette.entries[0].entry_type == "tool"

    # 2. Replay mode: function body MUST NOT execute again
    with Session(cassette_file, mode="replay"):
        res = run_query("SELECT * FROM users")
        assert res == {"result": "rows for SELECT * FROM users"}
        assert execution_count == 1  # Unchanged!


@pytest.mark.asyncio
async def test_async_record_tool(tmp_path: Path) -> None:
    cassette_file = tmp_path / "async_tool.jsonl"
    execution_count = 0

    @record_tool(name="fetch_customer")
    async def fetch_customer(cust_id: str) -> dict[str, str]:
        nonlocal execution_count
        execution_count += 1
        return {"id": cust_id, "name": "Alice"}

    # 1. Record mode
    async with Session(cassette_file, mode="record") as session:
        res = await fetch_customer("cust_123")
        assert res == {"id": "cust_123", "name": "Alice"}
        assert execution_count == 1
        assert len(session.cassette.entries) == 1

    # 2. Replay mode
    async with Session(cassette_file, mode="replay"):
        res = await fetch_customer("cust_123")
        assert res == {"id": "cust_123", "name": "Alice"}
        assert execution_count == 1


def test_tool_exception_recording_and_replay(tmp_path: Path) -> None:
    cassette_file = tmp_path / "tool_error.jsonl"

    @record_tool
    def faulty_tool(param: str) -> str:
        raise ValueError(f"Invalid param: {param}")

    with (
        Session(cassette_file, mode="record"),
        pytest.raises(ValueError, match="Invalid param: bad"),
    ):
        faulty_tool("bad")

    # In replay mode, reproducing the recorded error
    with (
        Session(cassette_file, mode="replay"),
        pytest.raises(RuntimeError, match="Invalid param: bad"),
    ):
        faulty_tool("bad")


def test_unrecorded_tool_fails_closed_in_replay(tmp_path: Path) -> None:
    cassette_file = tmp_path / "empty.jsonl"

    # Record empty session
    with Session(cassette_file, mode="record"):
        pass

    @record_tool
    def unrecorded_tool() -> str:
        return "live"

    with (
        Session(cassette_file, mode="replay"),
        pytest.raises(SideEffectError, match="No recorded tool execution found"),
    ):
        unrecorded_tool()


def test_record_tool_rehydrates_pydantic_model(tmp_path: Path) -> None:
    from pydantic import BaseModel

    class UserProfile(BaseModel):
        user_id: str
        display_name: str
        login_count: int

    cassette_file = tmp_path / "pydantic_tool.jsonl"
    calls = 0

    @record_tool(name="fetch_user_profile")
    def fetch_user_profile(user_id: str) -> UserProfile:
        nonlocal calls
        calls += 1
        return UserProfile(user_id=user_id, display_name="Test User", login_count=42)

    with Session(cassette_file, mode="record"):
        res = fetch_user_profile("usr_123")
        assert isinstance(res, UserProfile)
        assert res.user_id == "usr_123"
        assert res.login_count == 42
        assert calls == 1

    with Session(cassette_file, mode="replay"):
        res_replay = fetch_user_profile("usr_123")
        assert isinstance(res_replay, UserProfile)
        assert res_replay.user_id == "usr_123"
        assert res_replay.display_name == "Test User"
        assert res_replay.login_count == 42
        assert calls == 1


def test_record_tool_rehydrates_dataclass(tmp_path: Path) -> None:
    from dataclasses import dataclass

    @dataclass
    class InventoryItem:
        sku: str
        stock: int
        price: float

    cassette_file = tmp_path / "dataclass_tool.jsonl"
    calls = 0

    @record_tool(name="lookup_inventory")
    def lookup_inventory(sku: str) -> InventoryItem:
        nonlocal calls
        calls += 1
        return InventoryItem(sku=sku, stock=150, price=29.99)

    with Session(cassette_file, mode="record"):
        res = lookup_inventory("SKU-99")
        assert isinstance(res, InventoryItem)
        assert res.stock == 150
        assert res.price == 29.99
        assert calls == 1

    with Session(cassette_file, mode="replay"):
        res_replay = lookup_inventory("SKU-99")
        assert isinstance(res_replay, InventoryItem)
        assert res_replay.sku == "SKU-99"
        assert res_replay.stock == 150
        assert res_replay.price == 29.99
        assert calls == 1
