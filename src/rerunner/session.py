"""High-level context managers and Session class for recording, replaying, and forking agent runs."""

from __future__ import annotations

from collections.abc import Callable

import contextvars
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import httpx

from rerunner.async_transport import AsyncCassetteTransport
from rerunner.cassette import Cassette, CassetteError
from rerunner.matcher import MatchingStrategy
from rerunner.patcher import reset_active_session, set_active_session
from rerunner.sanitizer import PiiRedactor
from rerunner.side_effects import reset_active_cassette, set_active_cassette
from rerunner.storage import get_storage_backend
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    pass

SessionMode = Literal["auto", "record", "replay", "fork"]
ResolvedMode = Literal["record", "replay", "fork"]


class CassetteMissingError(CassetteError, FileNotFoundError):
    """Raised when a cassette file does not exist or is empty in replay mode."""


class SessionContext:
    """Active flight recorder session context containing transport and cassette configuration."""

    def __init__(
        self,
        transport: CassetteTransport,
        async_transport: AsyncCassetteTransport | None = None,
    ) -> None:
        self.transport = transport
        self.async_transport = (
            async_transport
            if async_transport is not None
            else AsyncCassetteTransport(
                cassette_path=transport.cassette_path,
                mode=transport.mode,
                fork_step=transport.fork_step,
                cassette=transport.cassette,
                pii_redactor=transport.pii_redactor,
            )
        )
        self.cassette = transport.cassette
        self.mode = transport.mode

    def get_client(self) -> httpx.Client:
        """Create an httpx.Client configured with this session's transport."""
        return httpx.Client(transport=self.transport)

    def get_async_client(self) -> httpx.AsyncClient:
        """Create an httpx.AsyncClient configured with this session's async transport."""
        return httpx.AsyncClient(transport=self.async_transport)


class Session:
    """Universal flight recorder session manager supporting sync and async context managers.

    Supports 'auto', 'record', 'replay', and 'fork' modes with optional RERUNNER_MODE environment override.
    """

    def __init__(
        self,
        cassette_path: Path | str,
        mode: SessionMode = "auto",
        fork_step: int | None = None,
        auto_patch: bool = True,
        chunk_delay_ms: int = 0,
        record_partial_streams: bool = False,
        matching_strategy: MatchingStrategy = "strict",
        pii_redactor: PiiRedactor | None = None,
        semantic_threshold: float = 0.80,
        embedding_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        self.cassette_path = Path(cassette_path)
        self.requested_mode = mode
        self.fork_step = fork_step
        self.auto_patch = auto_patch
        self.chunk_delay_ms = chunk_delay_ms
        self.record_partial_streams = record_partial_streams
        self.matching_strategy = matching_strategy
        self.pii_redactor = pii_redactor
        self.semantic_threshold = semantic_threshold
        self.embedding_fn = embedding_fn

        self.effective_mode: ResolvedMode = "record"
        self.transport: CassetteTransport
        self.async_transport: AsyncCassetteTransport
        self.cassette: Cassette

        self._cassette_token: contextvars.Token[Cassette | None] | None = None
        self._patch_token: contextvars.Token[Session | None] | None = None

    @property
    def mode(self) -> str:
        """Return the active effective mode of the session."""
        return self.effective_mode

    def _resolve_mode(self) -> ResolvedMode:
        """Resolve mode respecting RERUNNER_MODE environment variable and file existence."""
        env_mode = os.getenv("RERUNNER_MODE")
        mode_str = env_mode.lower().strip() if env_mode else self.requested_mode.lower().strip()

        backend = get_storage_backend(str(self.cassette_path))
        exists_and_non_empty = False
        if backend.exists(str(self.cassette_path)):
            try:
                raw = backend.read_bytes(str(self.cassette_path))
                exists_and_non_empty = len(raw.strip()) > 0
            except Exception:
                exists_and_non_empty = False

        if mode_str == "auto":
            resolved: ResolvedMode = "replay" if exists_and_non_empty else "record"
        elif mode_str in ("record", "replay", "fork"):
            resolved = mode_str  # type: ignore[assignment]
        else:
            raise ValueError(f"Invalid rerunner mode: {mode_str}")

        if resolved in ("replay", "fork") and not exists_and_non_empty:
            raise CassetteMissingError(
                f"Cassette file does not exist or is empty in {resolved} mode: {self.cassette_path}"
            )

        return resolved

    def _setup_session(self) -> None:
        self.effective_mode = self._resolve_mode()

        if self.effective_mode in ("replay", "fork") and self.cassette_path.exists():
            self.cassette = Cassette.load(self.cassette_path)
            if self.effective_mode == "fork" and self.fork_step is not None:
                self.cassette.truncate_after_step(self.fork_step)
        else:
            self.cassette = Cassette(self.cassette_path)

        self.transport = CassetteTransport(
            cassette_path=self.cassette_path,
            mode=self.effective_mode,
            fork_step=self.fork_step,
            chunk_delay_ms=self.chunk_delay_ms,
            record_partial_streams=self.record_partial_streams,
            matching_strategy=self.matching_strategy,
            cassette=self.cassette,
            pii_redactor=self.pii_redactor,
            semantic_threshold=self.semantic_threshold,
            embedding_fn=self.embedding_fn,
        )

        self.async_transport = AsyncCassetteTransport(
            cassette_path=self.cassette_path,
            mode=self.effective_mode,
            fork_step=self.fork_step,
            chunk_delay_ms=self.chunk_delay_ms,
            record_partial_streams=self.record_partial_streams,
            matching_strategy=self.matching_strategy,
            cassette=self.cassette,
            pii_redactor=self.pii_redactor,
            semantic_threshold=self.semantic_threshold,
            embedding_fn=self.embedding_fn,
        )

        self._cassette_token = set_active_cassette(
            self.cassette, mode=self.effective_mode, fork_step=self.fork_step
        )

        if self.auto_patch:
            self._patch_token = set_active_session(self)

    def _teardown_session(self) -> None:
        if self._patch_token is not None:
            reset_active_session(self._patch_token)
            self._patch_token = None

        if self.effective_mode in ("record", "fork") and (
            self.cassette.entries or not self.cassette_path.exists()
        ):
            self.cassette.save()

        if self._cassette_token is not None:
            reset_active_cassette(self._cassette_token)
            self._cassette_token = None

        self.transport.close()

    def get_client(self) -> httpx.Client:
        """Create an httpx.Client pre-configured with this session's transport."""
        return httpx.Client(transport=self.transport)

    def get_async_client(self) -> httpx.AsyncClient:
        """Create an httpx.AsyncClient pre-configured with this session's async transport."""
        return httpx.AsyncClient(transport=self.async_transport)

    def unpatched_client(self) -> httpx.Client:
        """Create an unpatched httpx.Client that hits live upstream endpoints."""
        return httpx.Client(transport=httpx.HTTPTransport())

    def unpatched_async_client(self) -> httpx.AsyncClient:
        """Create an unpatched httpx.AsyncClient that hits live upstream endpoints."""
        return httpx.AsyncClient(transport=httpx.AsyncHTTPTransport())

    def __enter__(self) -> Session:
        self._setup_session()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._teardown_session()

    async def __aenter__(self) -> Session:
        self._setup_session()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._teardown_session()
        await self.async_transport.aclose()


def record(
    cassette_path: Path | str,
    auto_patch: bool = True,
    chunk_delay_ms: int = 0,
    record_partial_streams: bool = False,
    matching_strategy: MatchingStrategy = "strict",
    pii_redactor: PiiRedactor | None = None,
) -> Session:
    """Return a Session configured in record mode."""
    return Session(
        cassette_path=cassette_path,
        mode="record",
        auto_patch=auto_patch,
        chunk_delay_ms=chunk_delay_ms,
        record_partial_streams=record_partial_streams,
        matching_strategy=matching_strategy,
        pii_redactor=pii_redactor,
    )


def replay(
    cassette_path: Path | str,
    auto_patch: bool = True,
    chunk_delay_ms: int = 0,
    matching_strategy: MatchingStrategy = "strict",
    semantic_threshold: float = 0.80,
    embedding_fn: Callable[[str], list[float]] | None = None,
) -> Session:
    """Return a Session configured in replay mode."""
    return Session(
        cassette_path=cassette_path,
        mode="replay",
        auto_patch=auto_patch,
        chunk_delay_ms=chunk_delay_ms,
        matching_strategy=matching_strategy,
        semantic_threshold=semantic_threshold,
        embedding_fn=embedding_fn,
    )


def fork(
    cassette_path: Path | str,
    step: int,
    auto_patch: bool = True,
    chunk_delay_ms: int = 0,
    matching_strategy: MatchingStrategy = "strict",
    pii_redactor: PiiRedactor | None = None,
) -> Session:
    """Return a Session configured in fork mode from the specified step."""
    return Session(
        cassette_path=cassette_path,
        mode="fork",
        fork_step=step,
        auto_patch=auto_patch,
        chunk_delay_ms=chunk_delay_ms,
        matching_strategy=matching_strategy,
        pii_redactor=pii_redactor,
    )
