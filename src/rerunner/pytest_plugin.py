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
        choices=("auto", "record", "replay", "fork"),
        default=None,
        help="Override Rerunner session mode for marked tests and fixtures (auto|record|replay|fork)",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "rerunner(cassette, mode='auto', auto_patch=True): Record or replay HTTP calls via Rerunner",
    )


def _resolve_pytest_cassette_and_mode(
    request: pytest.FixtureRequest,
) -> tuple[str, SessionMode, bool]:
    """Extract cassette path, effective session mode, and auto_patch flag for a test node."""
    marker = request.node.get_closest_marker("rerunner")
    cassette_path = "cassette.jsonl"
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    cli_mode = request.config.getoption("--rerunner-mode", None)
    is_record_mode = bool(request.config.getoption("--rerunner-record", False))
    marker_mode = marker.kwargs.get("mode") if marker else None

    if cli_mode in ("auto", "record", "replay", "fork"):
        raw_mode = cli_mode
    elif is_record_mode:
        raw_mode = "record"
    elif marker_mode in ("auto", "record", "replay", "fork"):
        raw_mode = marker_mode
    else:
        raw_mode = "auto"

    mode_val = cast(SessionMode, raw_mode)
    auto_patch = bool(marker.kwargs.get("auto_patch", True)) if marker else True
    return cassette_path, mode_val, auto_patch


@pytest.fixture(autouse=True)
def _rerunner_marker_autouse(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """If the test is marked with @pytest.mark.rerunner, activate a Session with auto_patch=True by default."""
    marker = request.node.get_closest_marker("rerunner")
    if not marker:
        yield
        return

    cassette_path, mode_val, auto_patch = _resolve_pytest_cassette_and_mode(request)
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

    cassette_path, mode_val, _ = _resolve_pytest_cassette_and_mode(request)
    # CassetteTransport does not accept 'auto'; default standalone fixture to 'replay' unless recorded
    transport_mode: Literal["record", "replay", "fork"] = (
        "record" if mode_val == "record" else ("fork" if mode_val == "fork" else "replay")
    )

    transport = CassetteTransport(cassette_path=cassette_path, mode=transport_mode)
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
        yield cast(Session, active_session)
        return

    cassette_path, mode_val, auto_patch = _resolve_pytest_cassette_and_mode(request)
    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch) as session:
        yield session
