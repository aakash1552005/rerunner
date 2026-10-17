"""Cassette storage engine for streaming plain, gzip-compressed, and remote JSONL reading and writing."""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING
from rerunner.integrity import compute_entry_hash, verify_cassette_integrity
from rerunner.models import CassetteEntry, CassetteMetadata
from rerunner.storage import get_storage_backend

if TYPE_CHECKING:
    from collections.abc import Iterator


class CassetteError(Exception):
    """Raised when cassette file operations fail or integrity is violated."""


class Cassette:
    """Represents a recorded agent session cassette stored as append-only JSONL (.jsonl),

    gzip-compressed JSONL (.jsonl.gz), or remote URIs (s3://, gs://).
    """

    def __init__(self, path: Path | str, metadata: CassetteMetadata | None = None) -> None:
        self.uri = str(path)
        self.path = Path(path) if not (self.uri.startswith("s3://") or self.uri.startswith("gs://")) else Path(self.uri.split("/")[-1])
        self.metadata = metadata or CassetteMetadata()
        self.entries: list[CassetteEntry] = []
        self._last_hash = "GENESIS"

    @classmethod
    def load(cls, path: Path | str, verify_integrity: bool = True) -> Cassette:
        """Load an existing plain, gzip-compressed, or remote cassette and optionally verify its cryptographic chain."""
        uri_str = str(path)
        backend = get_storage_backend(uri_str)

        if not backend.exists(uri_str):
            raise FileNotFoundError(f"Cassette file not found: {uri_str}")

        raw_bytes = backend.read_bytes(uri_str)
        if not raw_bytes:
            raise CassetteError(f"Cassette file is empty: {uri_str}")

        if uri_str.endswith(".gz"):
            with gzip.open(io.BytesIO(raw_bytes), "rt", encoding="utf-8") as file:
                lines = file.read().splitlines()
        elif uri_str.endswith(".zst"):
            try:
                import zstandard as zstd  # type: ignore[import-untyped]
            except ImportError as err:
                raise CassetteError(
                    "zstandard is required to load .zst cassettes. "
                    "Install it via `pip install rerunner[zstd]` or `pip install zstandard`."
                ) from err
            dctx = zstd.ZstdDecompressor()
            decompressed = dctx.decompress(raw_bytes)
            lines = decompressed.decode("utf-8").splitlines()
        else:
            lines = raw_bytes.decode("utf-8").splitlines()

        if not lines:
            raise CassetteError(f"Cassette file has no valid lines: {uri_str}")

        # Parse header
        try:
            header_dict = json.loads(lines[0])
            metadata = CassetteMetadata(**header_dict)
        except Exception as exc:
            raise CassetteError(f"Invalid cassette metadata header in {uri_str}: {exc}") from exc

        cassette = cls(uri_str, metadata=metadata)

        for line_num, line in enumerate(lines[1:], start=2):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                entry_dict = json.loads(line_str)
                entry = CassetteEntry(**entry_dict)
                cassette.entries.append(entry)
            except Exception as exc:
                raise CassetteError(
                    f"Malformed entry on line {line_num} in {uri_str}: {exc}"
                ) from exc

        if cassette.entries:
            cassette._last_hash = cassette.entries[-1].entry_hash

        if verify_integrity:
            is_valid, error = verify_cassette_integrity(cassette.entries)
            if not is_valid:
                raise CassetteError(f"Integrity check failed for {uri_str}: {error}")

        return cassette

    def append(self, entry: CassetteEntry) -> None:
        """Append a new entry to the in-memory cassette with tamper-evident chaining."""
        entry.prev_hash = self._last_hash
        entry.entry_hash = compute_entry_hash(entry, self._last_hash)
        self.entries.append(entry)
        self._last_hash = entry.entry_hash

    def save(self) -> None:
        """Write the complete cassette to disk or remote storage atomically, using gzip (.gz) or zstandard (.zst)."""
        backend = get_storage_backend(self.uri)

        # Assemble formatted payload
        text_content = self.metadata.model_dump_json() + "\n"
        for entry in self.entries:
            text_content += entry.model_dump_json() + "\n"

        if self.uri.endswith(".gz"):
            buf = io.BytesIO()
            with gzip.open(buf, "wt", encoding="utf-8") as gz_file:
                gz_file.write(text_content)
            data_bytes = buf.getvalue()
        elif self.uri.endswith(".zst"):
            try:
                import zstandard as zstd  # type: ignore[import-untyped]
            except ImportError as err:
                raise CassetteError(
                    "zstandard is required to save .zst cassettes. "
                    "Install it via `pip install rerunner[zstd]` or `pip install zstandard`."
                ) from err
            cctx = zstd.ZstdCompressor()
            data_bytes = cctx.compress(text_content.encode("utf-8"))
        else:
            data_bytes = text_content.encode("utf-8")

        backend.write_bytes(self.uri, data_bytes)

    def find_http_match(self, request_key: str, step: int | None = None) -> CassetteEntry | None:
        """Find a recorded HTTP response matching the request key, optionally at a specific step."""
        for entry in self.entries:
            if (
                entry.entry_type == "http"
                and entry.request
                and entry.request.request_key == request_key
                and (step is None or entry.step == step)
            ):
                return entry
        return None

    def __len__(self) -> int:
        return len(self.entries)

    def __iter__(self) -> Iterator[CassetteEntry]:
        return iter(self.entries)
