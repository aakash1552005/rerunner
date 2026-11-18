"""Strict offline gate for mutmut 3.8.1 CI/CD JSON statistics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

STATUSES = (
    "killed",
    "survived",
    "no_tests",
    "skipped",
    "suspicious",
    "timeout",
    "check_was_interrupted_by_user",
    "segfault",
)


def assess_stats(data: object, threshold: int = 80) -> tuple[bool, str]:
    if type(threshold) is not int or not 0 <= threshold <= 100:
        return False, "Invalid threshold"
    if not isinstance(data, dict):
        return False, "Invalid statistics object"
    expected = set(STATUSES) | {"total"}
    if set(data) != expected:
        return False, "Missing or unexpected statistics fields"
    if any(type(data[k]) is not int or data[k] < 0 for k in expected):
        return False, "Invalid statistics counts"
    total = data["total"]
    if total == 0:
        return False, "No mutants measured"
    # mutmut omits not_checked from the export but includes it in total.
    if sum(data[k] for k in STATUSES) != total:
        return False, "Incomplete mutation results"
    inconclusive = {
        name: data[name]
        for name in (
            "skipped",
            "suspicious",
            "timeout",
            "check_was_interrupted_by_user",
            "segfault",
        )
        if data[name]
    }
    killed = data["killed"]
    passed = 100 * killed >= threshold * total and not inconclusive
    message = (
        f"{'PASS' if passed else 'FAIL'}: mutation score "
        f"{100 * killed / total:.2f}% ({killed}/{total} killed; "
        f"{data['survived']} survived; {data['no_tests']} without tests); "
        f"threshold {threshold}%"
    )
    if inconclusive:
        details = ", ".join(f"{name}={count}" for name, count in inconclusive.items())
        message += f"; inconclusive outcomes: {details}"
    return passed, message


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stats", required=True, type=Path)
    p.add_argument("--summary", type=Path)
    p.add_argument("--threshold", type=int, default=80)
    args = p.parse_args(argv)
    try:
        passed, message = assess_stats(
            json.loads(args.stats.read_text(encoding="utf-8")), args.threshold
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        passed, message = False, f"Missing or invalid mutation results: {type(exc).__name__}"
    print(message)
    if args.summary:
        try:
            with args.summary.open("a", encoding="utf-8") as f:
                f.write("### Mutation score gate\n\n" + message + "\n")
        except OSError as exc:
            print(f"Could not write summary: {exc}", file=sys.stderr)
            return 1
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
