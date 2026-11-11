"""Pytest plugin providing @pytest.mark.rerunner, auto-patching, and fixtures."""

from __future__ import annotations


from collections.abc import Generator
from typing import TYPE_CHECKING, Literal, cast

import pytest

from rerunner.session import Session, SessionMode
from rerunner.transport import CassetteTransport

if TYPE_CHECKING:
    import httpx


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register CLI flags for pytest."""
    group = parser.getgroup("rerunner")
    group.addoption(
        "--rerunner-record",
        action="store_true",
        default=False,
        help="Record new cassettes instead of replaying existing ones",
    )
    group.addoption(
        "--rerunner-mode",
        action="store",
        choices=["auto", "record", "replay", "fork"],
        default=None,
        help=(
            "Force the Rerunner mode for this run (auto, record, replay, or fork). "
            "Takes precedence over --rerunner-record and any @pytest.mark.rerunner(mode=...)."
        ),
    )


_VALID_MODES = ("auto", "record", "replay", "fork")


def _cli_mode(config: pytest.Config) -> SessionMode | None:
    """Mode forced from the command line, if any.

    --rerunner-mode wins over the legacy --rerunner-record flag.
    """
    raw = config.getoption("--rerunner-mode", None)
    if raw in _VALID_MODES:
        return cast(SessionMode, raw)
    if config.getoption("--rerunner-record", False):
        return "record"
    return None


def _resolve_mode(
    config: pytest.Config, marker: pytest.Mark | None
) -> SessionMode:
    """Resolve the session mode: CLI flags, then the marker, then 'auto'.

    The RERUNNER_MODE environment variable is still honoured by
    Session itself when it resolves the effective mode.
    """
    cli = _cli_mode(config)
    if cli is not None:
        return cli
    raw_mode = marker.kwargs.get("mode", "auto") if marker else "auto"
    return cast(
        SessionMode, raw_mode if raw_mode in _VALID_MODES else "auto"
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "rerunner(cassette, mode='auto', auto_patch=True): Record or replay HTTP calls via Rerunner",
    )


@pytest.fixture(autouse=True)
def _rerunner_marker_autouse(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """If the test is marked with @pytest.mark.rerunner, activate a Session with auto_patch=True by default."""
    marker = request.node.get_closest_marker("rerunner")
    if not marker:
        yield
        return

    cassette_path = "cassette.jsonl"
    if marker.args:
        cassette_path = str(marker.args[0])
    elif "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    mode_val = _resolve_mode(request.config, marker)
    auto_patch = bool(marker.kwargs.get("auto_patch", True))

    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch):
        yield


@pytest.fixture
def rerunner_transport(
    request: pytest.FixtureRequest,
) -> Generator[httpx.BaseTransport, None, None]:
    """Pytest fixture providing a pre-configured CassetteTransport for the current test."""
    from rerunner.patcher import get_active_session

    active_session = get_active_session()
    if active_session is not None:
        yield active_session.transport
        return

    marker = request.node.get_closest_marker("rerunner")
    cassette_path = "cassette.jsonl"
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    resolved = _resolve_mode(request.config, marker)
    # CassetteTransport has no "auto": it keeps the historical default of
    # replaying unless a record mode was requested.
    mode: Literal["record", "replay", "fork"] = (
        resolved if resolved in ("record", "replay", "fork") else "replay"
    )

    transport = CassetteTransport(cassette_path=cassette_path, mode=mode)
    yield transport
    transport.close()


@pytest.fixture
def rerunner_session(
    request: pytest.FixtureRequest,
) -> Generator[Session, None, None]:
    """Pytest fixture providing an active Session."""
    from rerunner.patcher import get_active_session

    active_session = get_active_session()
    if active_session is not None:
        yield active_session
        return

    marker = request.node.get_closest_marker("rerunner")
    cassette_path = "cassette.jsonl"
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    mode_val = _resolve_mode(request.config, marker)
    auto_patch = bool(marker.kwargs.get("auto_patch", True)) if marker else True

    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch) as session:
        yield session
