"""Synthetic cases for the fail-closed mutation score gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_mutation_score import STATUSES, assess_stats


def stats(killed=8, survived=2, no_tests=0):
    d = dict.fromkeys(STATUSES, 0)
    d.update(killed=killed, survived=survived, no_tests=no_tests)
    d["total"] = sum(d[k] for k in STATUSES)
    return d


@pytest.mark.parametrize(
    ("k", "s", "n", "passed"),
    [
        (8, 2, 0, True),
        (7, 3, 0, False),
        (8, 1, 1, True),
        (7, 1, 2, False),
        (0, 0, 0, False),
    ],
)
def test_threshold(k, s, n, passed):
    assert assess_stats(stats(k, s, n))[0] is passed


@pytest.mark.parametrize("bad", [None, [], "text", 123])
def test_invalid_shapes(bad):
    assert not assess_stats(bad)[0]


@pytest.mark.parametrize("bad", [-1, True, 0.5, "8"])
def test_invalid_counts(bad):
    data = stats()
    data["killed"] = bad
    assert not assess_stats(data)[0]


def test_missing_extra_and_incomplete():
    missing = stats()
    missing.pop("killed")
    extra = stats()
    extra["unknown"] = 0
    incomplete = stats()
    incomplete["total"] += 1
    assert all(not assess_stats(x)[0] for x in (missing, extra, incomplete))


@pytest.mark.parametrize(
    "field", ["skipped", "suspicious", "timeout", "check_was_interrupted_by_user", "segfault"]
)
def test_inconclusive(field):
    d = stats()
    d["survived"] -= 1
    d[field] += 1
    passed, message = assess_stats(d)
    assert not passed
    assert "mutation score 80.00%" in message
    assert f"{field}=1" in message


def test_inconclusive_above_threshold_also_fails():
    data = stats(killed=9, survived=1)
    data["survived"] = 0
    data["timeout"] = 1
    passed, message = assess_stats(data)
    assert not passed
    assert "mutation score 90.00%" in message
    assert "timeout=1" in message


@pytest.mark.parametrize("threshold", [-1, 101, "80", True])
def test_invalid_threshold(threshold):
    assert not assess_stats(stats(), threshold)[0]


def run_cli(tmp_path, raw=None, summary=True):
    f = tmp_path / "stats.json"
    out = tmp_path / "summary.md"
    if raw is not None:
        f.write_text(raw, encoding="utf-8")
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "check_mutation_score.py"),
        "--stats",
        str(f),
    ]
    if summary:
        cmd += ["--summary", str(out)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False), out


def test_cli_success(tmp_path):
    result, out = run_cli(tmp_path, json.dumps(stats()))
    assert result.returncode == 0
    assert "80.00%" in result.stdout
    assert "8/10 killed" in out.read_text(encoding="utf-8")


@pytest.mark.parametrize("raw", [None, "{broken", json.dumps(stats(7, 3))])
def test_cli_failures(tmp_path, raw):
    result, out = run_cli(tmp_path, raw)
    assert result.returncode == 1
    assert out.exists()


def test_unwritable_summary_fails(tmp_path):
    f = tmp_path / "stats.json"
    f.write_text(json.dumps(stats()), encoding="utf-8")
    command = [
        sys.executable,
        str(Path(__file__).resolve().parents[1] / "scripts" / "check_mutation_score.py"),
        "--stats",
        str(f),
        "--summary",
        str(tmp_path / "nonexistent" / "summary.md"),
    ]
    assert subprocess.run(command, capture_output=True, check=False).returncode == 1


def test_workflow_and_source_configuration_are_scoped():
    """Guard against reintroducing an unbounded or silently successful run."""
    import tomllib

    root = Path(__file__).resolve().parents[1]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mutmut"]
    assert config["source_paths"] == ["src/rerunner"]
    assert config["only_mutate"] == [
        "src/rerunner/integrity.py",
        "src/rerunner/sanitizer.py",
    ]
    assert config["pytest_add_cli_args_test_selection"] == [
        "tests/test_integrity.py",
        "tests/test_sanitizer.py",
    ]
    workflow = (root / ".github" / "workflows" / "mutation.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: 20" in workflow
    assert "contents: read" in workflow
    assert "mutmut==3.8.1" in workflow
    assert "set -euo pipefail" in workflow
    assert "mutmut export-cicd-stats" in workflow
    assert "mutmut-cicd-stats.json" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "--paths-to-mutate" not in workflow
    assert "|| true" not in workflow
