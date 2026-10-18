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

    is_record_mode = bool(request.config.getoption("--rerunner-record", False))
    raw_mode = marker.kwargs.get("mode", "record" if is_record_mode else "auto")
    mode_val: SessionMode = cast(
        SessionMode,
        raw_mode if raw_mode in ("auto", "record", "replay", "fork") else "auto",
    )
    auto_patch = bool(marker.kwargs.get("auto_patch", True))

    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch):
        yield


@pytest.fixture
def rerunner_transport(
    request: pytest.FixtureRequest,
) -> Generator[httpx.BaseTransport, None, None]:
    """Pytest fixture providing a pre-configured CassetteTransport for the current test."""
    marker = request.node.get_closest_marker("rerunner")
    cassette_path = "cassette.jsonl"
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    is_record_mode = bool(request.config.getoption("--rerunner-record", False))
    mode: Literal["record", "replay"] = "record" if is_record_mode else "replay"

    transport = CassetteTransport(cassette_path=cassette_path, mode=mode)
    yield transport
    transport.close()


@pytest.fixture
def rerunner_session(
    request: pytest.FixtureRequest,
) -> Generator[Session, None, None]:
    """Pytest fixture providing an active Session."""
    marker = request.node.get_closest_marker("rerunner")
    cassette_path = "cassette.jsonl"
    if marker and marker.args:
        cassette_path = str(marker.args[0])
    elif marker and "cassette" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette"])
    elif marker and "cassette_path" in marker.kwargs:
        cassette_path = str(marker.kwargs["cassette_path"])

    is_record_mode = bool(request.config.getoption("--rerunner-record", False))
    raw_mode = (
        marker.kwargs.get("mode", "record" if is_record_mode else "auto") if marker else "auto"
    )
    mode_val: SessionMode = cast(
        SessionMode,
        raw_mode if raw_mode in ("auto", "record", "replay", "fork") else "auto",
    )
    auto_patch = bool(marker.kwargs.get("auto_patch", True)) if marker else True

    with Session(cassette_path=cassette_path, mode=mode_val, auto_patch=auto_patch) as session:
        yield session
