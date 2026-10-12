"""Cassette storage engine for streaming JSONL reading and writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from rerunner.integrity import compute_entry_hash, verify_cassette_integrity
from rerunner.models import CassetteEntry, CassetteMetadata
import gzip

if TYPE_CHECKING:
    from collections.abc import Iterator


class CassetteError(Exception):
    """Raised when cassette file operations fail or integrity is violated."""


class Cassette:
    """Represents a recorded agent session cassette stored as append-only JSONL."""

    def __init__(self, path: Path | str, metadata: CassetteMetadata | None = None) -> None:
        self.path = Path(path)
        self.metadata = metadata or CassetteMetadata()
        self.entries: list[CassetteEntry] = []
        self._last_hash = "GENESIS"

    @classmethod
    def load(cls, path: Path | str, verify_integrity: bool = True) -> Cassette:
        """Load an existing cassette from disk and optionally verify its cryptographic chain."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Cassette file not found: {file_path}")

        if file_path.name.endswith(".gz"):
            with gzip.open(file_path, "rt", encoding="utf-8") as file:
                lines = file.read().splitlines()
        else:
            lines = file_path.read_text(encoding="utf-8").splitlines()

        if not lines:
            raise CassetteError(f"Cassette file is empty: {file_path}")

        # Parse header
        try:
            header_dict = json.loads(lines[0])
            metadata = CassetteMetadata(**header_dict)
        except Exception as exc:
            raise CassetteError(f"Invalid cassette metadata header in {file_path}: {exc}") from exc

        cassette = cls(file_path, metadata=metadata)

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
                    f"Malformed entry on line {line_num} in {file_path}: {exc}"
                ) from exc

        if cassette.entries:
            cassette._last_hash = cassette.entries[-1].entry_hash

        if verify_integrity:
            is_valid, error = verify_cassette_integrity(cassette.entries)
            if not is_valid:
                raise CassetteError(f"Integrity check failed for {file_path}: {error}")

        return cassette

    def append(self, entry: CassetteEntry) -> None:
        """Append a new entry to the in-memory cassette with tamper-evident chaining."""
        entry.prev_hash = self._last_hash
        entry.entry_hash = compute_entry_hash(entry, self._last_hash)
        self.entries.append(entry)
        self._last_hash = entry.entry_hash

    def save(self) -> None:
        """Write the complete cassette to disk atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")

        if self.path.name.endswith(".gz"):
            with gzip.open(temp_path, "wt", encoding="utf-8") as file:
                file.write(self.metadata.model_dump_json() + "\n")
                for entry in self.entries:
                    file.write(entry.model_dump_json() + "\n")
        else:
            with temp_path.open("w", encoding="utf-8") as file:
                # Write metadata header
                file.write(self.metadata.model_dump_json() + "\n")
                for entry in self.entries:
                    file.write(entry.model_dump_json() + "\n")

        temp_path.replace(self.path)

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
