"""Tests for cassette persistence, integrity, and matching."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from rerunner.cassette import Cassette, CassetteError
from rerunner.integrity import compute_entry_hash
from rerunner.models import CassetteEntry, CassetteMetadata, RecordedRequest, RecordedResponse


def make_http_entry(step: int = 1, request_key: str | None = None) -> CassetteEntry:
    """Create a representative HTTP cassette entry."""
    request = RecordedRequest(
        method="POST",
        url="http://localhost:11434/api/chat",
        headers={"content-type": "application/json"},
        body='{"model":"llama3.2","stream":false}',
        request_key=request_key or f"request-key-{step}",
    )
    response = RecordedResponse(
        status_code=200,
        headers={"content-type": "application/json"},
        body='{"message":{"role":"assistant","content":"Hello"}}',
    )
    return CassetteEntry(
        step=step,
        entry_type="http",
        request=request,
        response=response,
    )


def test_plain_cassette_round_trip_preserves_metadata_entries_and_matching(
    tmp_path: Path,
) -> None:
    """Plain cassettes persist their data and remain searchable after loading."""
    cassette_path = tmp_path / "nested" / "session.jsonl"
    metadata = CassetteMetadata(agent_id="agent-007", sanitized=False)
    cassette = Cassette(cassette_path, metadata=metadata)
    first = make_http_entry(step=1, request_key="shared-key")
    second = make_http_entry(step=2, request_key="shared-key")
    cassette.append(first)
    cassette.append(second)

    cassette.save()
    loaded = Cassette.load(cassette_path)

    assert loaded.metadata.model_dump() == metadata.model_dump()
    assert [entry.model_dump() for entry in loaded] == [entry.model_dump() for entry in cassette]
    assert len(loaded) == 2
    assert loaded.find_http_match("shared-key") == loaded.entries[0]
    assert loaded.find_http_match("shared-key", step=2) == loaded.entries[1]
    assert loaded.find_http_match("missing-key") is None
    assert not cassette_path.with_suffix(".jsonl.tmp").exists()


def test_gzip_cassette_is_compressed_jsonl_and_round_trips(tmp_path: Path) -> None:
    """The .gz format contains compressed JSONL and loads transparently."""
    cassette_path = tmp_path / "session.jsonl.gz"
    cassette = Cassette(cassette_path)
    cassette.append(make_http_entry())
    cassette.save()

    assert cassette_path.read_bytes().startswith(b"\x1f\x8b")
    with gzip.open(cassette_path, "rt", encoding="utf-8") as file:
        lines = file.read().splitlines()

    assert len(lines) == 2
    assert json.loads(lines[0])["format_version"] == "1.1.0"
    assert json.loads(lines[1])["response"]["status_code"] == 200
    assert Cassette.load(cassette_path).entries[0].model_dump() == (
        cassette.entries[0].model_dump()
    )


def test_append_builds_chain_and_loading_allows_chain_to_continue(tmp_path: Path) -> None:
    """Append owns hash fields and a reopened cassette continues the existing chain."""
    cassette_path = tmp_path / "chain.jsonl"
    cassette = Cassette(cassette_path)
    first = make_http_entry(step=1)
    first.prev_hash = "untrusted previous hash"
    first.entry_hash = "untrusted entry hash"

    cassette.append(first)
    cassette.save()
    loaded = Cassette.load(cassette_path)
    loaded.append(make_http_entry(step=2))
    loaded.save()
    reloaded = Cassette.load(cassette_path)

    assert reloaded.entries[0].prev_hash == "GENESIS"
    assert reloaded.entries[0].entry_hash == compute_entry_hash(reloaded.entries[0], "GENESIS")
    assert reloaded.entries[1].prev_hash == reloaded.entries[0].entry_hash
    assert reloaded.entries[1].entry_hash == compute_entry_hash(
        reloaded.entries[1], reloaded.entries[0].entry_hash
    )


def test_load_rejects_missing_empty_and_malformed_cassettes(tmp_path: Path) -> None:
    """Load failures distinguish absent, empty, bad-header, and bad-entry files."""
    missing_path = tmp_path / "missing.jsonl"
    with pytest.raises(FileNotFoundError, match="Cassette file not found"):
        Cassette.load(missing_path)

    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("", encoding="utf-8")
    with pytest.raises(CassetteError, match="Cassette file is empty"):
        Cassette.load(empty_path)

    bad_header_path = tmp_path / "bad-header.jsonl"
    bad_header_path.write_text("not json\n", encoding="utf-8")
    with pytest.raises(CassetteError, match="Invalid cassette metadata header"):
        Cassette.load(bad_header_path)

    bad_entry_path = tmp_path / "bad-entry.jsonl"
    bad_entry_path.write_text(
        f"{CassetteMetadata().model_dump_json()}\n\nnot json\n",
        encoding="utf-8",
    )
    with pytest.raises(CassetteError, match="Malformed entry on line 3"):
        Cassette.load(bad_entry_path)


@pytest.mark.parametrize("filename", ["tampered.jsonl", "tampered.jsonl.gz"])
def test_load_detects_tampering_unless_verification_is_disabled(
    tmp_path: Path,
    filename: str,
) -> None:
    """Plain and compressed cassettes detect tampering unless verification is disabled."""
    cassette_path = tmp_path / filename
    cassette = Cassette(cassette_path)
    cassette.append(make_http_entry())
    cassette.save()

    if cassette_path.name.endswith(".gz"):
        with gzip.open(cassette_path, "rt", encoding="utf-8") as file:
            lines = file.read().splitlines()
    else:
        lines = cassette_path.read_text(encoding="utf-8").splitlines()

    entry = json.loads(lines[1])
    entry["response"]["status_code"] = 503
    lines[1] = json.dumps(entry)

    if cassette_path.name.endswith(".gz"):
        with gzip.open(cassette_path, "wt", encoding="utf-8") as file:
            file.write("\n".join(lines) + "\n")
    else:
        cassette_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(CassetteError, match="Integrity check failed"):
        Cassette.load(cassette_path)

    loaded = Cassette.load(cassette_path, verify_integrity=False)
    assert loaded.entries[0].response is not None
    assert loaded.entries[0].response.status_code == 503
