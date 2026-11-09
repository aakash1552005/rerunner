"""Tests for the --rerunner-record-missing pytest flag."""

from __future__ import annotations

from rerunner.pytest_plugin import _resolve_mode


class _DummyRequest:
    def __init__(self, options: dict[str, bool]) -> None:
        self.config = _DummyConfig(options)


class _DummyConfig:
    def __init__(self, options: dict[str, bool]) -> None:
        self._options = options

    def getoption(self, name: str, default: bool = False) -> bool:
        return self._options.get(name, default)


def test_resolve_mode_record_missing_forces_record() -> None:
    request = _DummyRequest({"--rerunner-record-missing": True})
    assert _resolve_mode(request, None) == "record"


def test_resolve_mode_full_record_takes_precedence() -> None:
    request = _DummyRequest({"--rerunner-record": True, "--rerunner-record-missing": True})
    assert _resolve_mode(request, None) == "record"


def test_resolve_mode_respects_marker_when_no_flags() -> None:
    request = _DummyRequest({})
    marker = type("M", (), {"kwargs": {"mode": "replay"}})()
    assert _resolve_mode(request, marker) == "replay"
