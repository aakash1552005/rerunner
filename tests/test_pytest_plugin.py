"""Tests for the Rerunner pytest plugin CLI flags and marker precedence."""

from __future__ import annotations

from pathlib import Path
import pytest

pytest_plugins = ["pytester"]


def test_pytest_rerunner_mode_flag_overrides_marker(pytester: pytest.Pytester) -> None:
    cassette_path = pytester.path / "missing_strict.jsonl"
    pytester.makepyfile(
        f"""
        import httpx
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_strict_replay_fails_when_missing():
            httpx.get("https://api.example.com/hello")
        """
    )

    result = pytester.runpytest("--rerunner-mode=replay")
    # Fixture setup raises CassetteMissingError because --rerunner-mode=replay overrides mode="auto"
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*CassetteMissingError*"])


def test_pytest_rerunner_mode_precedence_over_record_flag(pytester: pytest.Pytester) -> None:
    cassette_path = pytester.path / "precedence.jsonl"
    cassette_path.write_text("", encoding="utf-8")
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_session_mode(rerunner_session):
            assert rerunner_session.mode == "replay"
        """
    )

    # Empty cassette still raises CassetteMissingError in replay mode even if --rerunner-record is passed
    result = pytester.runpytest("--rerunner-record", "--rerunner-mode=replay")
    assert result.ret != 0
    result.stdout.fnmatch_lines(["*CassetteMissingError*"])


def test_pytest_rerunner_transport_respects_mode_flag(pytester: pytest.Pytester) -> None:
    cassette_path = Path(pytester.path) / "transport_mode.jsonl"
    pytester.makepyfile(
        f"""
        import pytest

        @pytest.mark.rerunner(cassette={str(cassette_path)!r}, mode="auto")
        def test_transport_mode(rerunner_transport):
            assert rerunner_transport.mode == "record"
        """
    )

    result = pytester.runpytest("--rerunner-mode=record")
    assert result.ret == 0
