"""Tests for the rerunner pytest plugin, especially --rerunner-mode precedence.

Precedence under test: --rerunner-mode / --rerunner-record (CLI) beats
@pytest.mark.rerunner(mode=...), which beats the "auto" default.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]

# Creates a one-entry cassette in the inner run's rootdir so that replay and
# fork sessions can start.
CONFTEST = """
from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse


def pytest_configure(config):
    cassette = Cassette("cassette.jsonl")
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="http://x/1", headers={}, body=""),
            response=RecordedResponse(status_code=200, headers={}, body="ok"),
        )
    )
    cassette.save()
"""

MARKER_TEST = """
import pytest
from rerunner.patcher import get_active_session


@pytest.mark.rerunner(cassette="cassette.jsonl"{mode_kwarg})
def test_requested_mode():
    session = get_active_session()
    assert session is not None
    assert session.requested_mode == "{expected}"
"""


@pytest.fixture(autouse=True)
def _no_env_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # Session honours RERUNNER_MODE itself; keep it out of these tests so the
    # plugin-level precedence is what is being measured.
    monkeypatch.delenv("RERUNNER_MODE", raising=False)


def _run_marker_case(
    pytester: pytest.Pytester,
    *,
    marker_mode: str | None,
    expected: str,
    cli_args: list[str],
) -> None:
    pytester.makeconftest(CONFTEST)
    mode_kwarg = f', mode="{marker_mode}"' if marker_mode is not None else ""
    pytester.makepyfile(
        test_mode=MARKER_TEST.format(mode_kwarg=mode_kwarg, expected=expected)
    )
    result = pytester.runpytest_inprocess(*cli_args)
    result.assert_outcomes(passed=1)


def test_marker_mode_used_without_cli(pytester: pytest.Pytester) -> None:
    _run_marker_case(pytester, marker_mode="record", expected="record", cli_args=[])


def test_no_marker_mode_and_no_cli_defaults_to_auto(pytester: pytest.Pytester) -> None:
    _run_marker_case(pytester, marker_mode=None, expected="auto", cli_args=[])


def test_cli_mode_overrides_marker_mode(pytester: pytest.Pytester) -> None:
    _run_marker_case(
        pytester,
        marker_mode="record",
        expected="replay",
        cli_args=["--rerunner-mode=replay"],
    )


def test_cli_record_flag_overrides_marker_mode(pytester: pytest.Pytester) -> None:
    _run_marker_case(
        pytester,
        marker_mode="replay",
        expected="record",
        cli_args=["--rerunner-record"],
    )


def test_cli_mode_beats_record_flag(pytester: pytest.Pytester) -> None:
    _run_marker_case(
        pytester,
        marker_mode="record",
        expected="fork",
        cli_args=["--rerunner-mode=fork", "--rerunner-record"],
    )


def test_cli_mode_applies_to_rerunner_session_fixture(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        test_mode="""
        def test_session_mode(rerunner_session):
            assert rerunner_session.requested_mode == "record"
        """
    )
    result = pytester.runpytest_inprocess("--rerunner-mode=record")
    result.assert_outcomes(passed=1)


def test_cli_mode_applies_to_rerunner_transport_fixture(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        test_mode="""
        def test_transport_mode(rerunner_transport):
            assert rerunner_transport.mode == "fork"
        """
    )
    result = pytester.runpytest_inprocess("--rerunner-mode=fork")
    result.assert_outcomes(passed=1)


def test_transport_defaults_to_replay_without_cli(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(
        test_mode="""
        def test_transport_mode(rerunner_transport):
            assert rerunner_transport.mode == "replay"
        """
    )
    result = pytester.runpytest_inprocess()
    result.assert_outcomes(passed=1)


def test_invalid_cli_mode_is_rejected(pytester: pytest.Pytester) -> None:
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_mode="def test_noop():\n    pass\n")
    result = pytester.runpytest_inprocess("--rerunner-mode=bogus")
    assert result.ret != 0
    assert "invalid choice" in result.stderr.str() + result.stdout.str()
