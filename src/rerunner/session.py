"""High-level context managers for recording, replaying, and forking agent runs."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator
from typing import TYPE_CHECKING
from rerunner.side_effects import set_active_cassette
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    import httpx


class SessionContext:
    """Active flight recorder session context containing transport and cassette configuration."""

    def __init__(self, transport: CassetteTransport) -> None:
        self.transport = transport
        self.cassette = transport.cassette

    def get_client(self) -> httpx.Client:
        """Create an httpx.Client pre-configured with this session's transport."""
        import httpx

        return httpx.Client(transport=self.transport)


@contextmanager
def record(cassette_path: Path | str) -> Iterator[SessionContext]:
    """Context manager to record all HTTP and decorated side-effects to a cassette."""
    transport = CassetteTransport(cassette_path=cassette_path, mode="record")
    set_active_cassette(transport.cassette, mode="record")
    session = SessionContext(transport=transport)
    try:
        yield session
    finally:
        transport.cassette.save()
        set_active_cassette(None)
        transport.close()


@contextmanager
def replay(cassette_path: Path | str) -> Iterator[SessionContext]:
    """Context manager to deterministically replay all interactions from an existing cassette."""
    transport = CassetteTransport(cassette_path=cassette_path, mode="replay")
    set_active_cassette(transport.cassette, mode="replay")
    session = SessionContext(transport=transport)
    try:
        yield session
    finally:
        set_active_cassette(None)
        transport.close()


@contextmanager
def fork(cassette_path: Path | str, step: int) -> Iterator[SessionContext]:
    """Context manager to replay steps 1..step from cassette, and execute live from step+1."""
    transport = CassetteTransport(cassette_path=cassette_path, mode="fork", fork_step=step)
    set_active_cassette(transport.cassette, mode="fork", fork_step=step)
    session = SessionContext(transport=transport)
    try:
        yield session
    finally:
        transport.cassette.save()
        set_active_cassette(None)
        transport.close()
