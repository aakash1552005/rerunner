# Rerunner Justfile - Modern cross-platform developer workflows

default:
    @just --list

# Run entire test suite with pytest
test:
    uv run pytest -v

# Run lint checks with Ruff
lint:
    uv run ruff check .

# Auto-format codebase with Ruff
format:
    uv run ruff format .
    uv run ruff check --fix .

# Run strict static type checking with Mypy
typecheck:
    uv run mypy src

# Run format, lint, typecheck, and unit tests in sequence
check: format lint typecheck test

# Run latency and token savings benchmark
bench:
    uv run python benchmarks/bench_replay_latency.py

# Verify all runnable cookbooks in examples/
cookbooks:
    uv run python examples/01_openai_quickstart.py
    uv run python examples/02_anthropic_sse_streaming.py
    uv run python examples/03_mcp_sqlite_replayer.py
    uv run python examples/04_chaos_fault_injection.py
