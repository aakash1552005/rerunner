"""Project-level default options loaded from ``[tool.rerunner]`` in ``pyproject.toml``."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

VALID_MODES = ("auto", "record", "replay", "fork")

DEFAULT_CASSETTE_DIR = ".rerunner/cassettes"

_table_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}


def find_pyproject(start: Path | str | None = None) -> Path | None:
    """Return the nearest ``pyproject.toml`` walking upward from ``start`` (defaults to cwd)."""
    current = Path(start) if start is not None else Path.cwd()
    if current.is_file():
        current = current.parent
    current = current.resolve()
    for directory in (current, *current.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            return candidate
    return None


def load_tool_config(start: Path | str | None = None) -> dict[str, Any]:
    """Return the ``[tool.rerunner]`` table of the nearest ``pyproject.toml`` ({} when absent)."""
    pyproject = find_pyproject(start)
    if pyproject is None:
        return {}
    key = str(pyproject)
    try:
        stat = pyproject.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        cached = _table_cache.get(key)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        table = raw.get("tool", {}).get("rerunner", {})
        result = dict(table) if isinstance(table, dict) else {}
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    _table_cache[key] = (stamp, result)
    return result


def config_cassette_dir(start: Path | str | None = None) -> str | None:
    """Return ``cassette_dir`` from ``[tool.rerunner]`` (None when unset or invalid)."""
    value = load_tool_config(start).get("cassette_dir")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def config_ignore_fields(start: Path | str | None = None) -> set[str]:
    """Return ``ignore_fields`` from ``[tool.rerunner]`` as a set of field names."""
    value = load_tool_config(start).get("ignore_fields")
    if isinstance(value, str):
        return {item.strip() for item in value.split(",") if item.strip()}
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    return set()


def config_mode(start: Path | str | None = None) -> str | None:
    """Return a validated ``mode`` from ``[tool.rerunner]`` (None when unset or invalid)."""
    value = load_tool_config(start).get("mode")
    if isinstance(value, str) and value.strip().lower() in VALID_MODES:
        return value.strip().lower()
    return None


def config_pricing(start: Path | str | None = None) -> dict[str, tuple[float, float]]:
    """Return custom model pricing from ``[tool.rerunner.pricing]`` in ``pyproject.toml``.

    Supports:
    - Lists/tuples: ``"gpt-4o" = [2.50, 10.00]``
    - Tables: ``[tool.rerunner.pricing.custom-model] input = 1.5; output = 6.0``
    """
    raw_pricing = load_tool_config(start).get("pricing")
    if not isinstance(raw_pricing, dict):
        return {}

    rates: dict[str, tuple[float, float]] = {}
    for model_key, val in raw_pricing.items():
        if not isinstance(model_key, str) or not model_key.strip():
            continue
        norm_key = model_key.lower().strip()
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            try:
                rates[norm_key] = (float(val[0]), float(val[1]))
            except (ValueError, TypeError):
                continue
        elif isinstance(val, dict):
            in_rate = (
                val.get("input") or val.get("input_usd_per_1m") or val.get("input_tokens") or 0.0
            )
            out_rate = (
                val.get("output") or val.get("output_usd_per_1m") or val.get("output_tokens") or 0.0
            )
            try:
                rates[norm_key] = (float(in_rate), float(out_rate))
            except (ValueError, TypeError):
                continue
    return rates
