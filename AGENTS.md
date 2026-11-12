# Agent & Contributor Guidelines

See [`CLAUDE.md`](CLAUDE.md) for the core engineering invariants (non-blocking SSE streaming, `contextvars` isolation, fail-closed replay guarantees, PII sanitization before disk writes, thread-safe step sequencing).

## Architecture & Module Boundaries

Dependencies strictly flow inward — enforced automatically in CI by `lint-imports` (configured in [`pyproject.toml`](pyproject.toml)) and visualized in [`docs/architecture/architecture.mermaid`](docs/architecture/architecture.mermaid):

1. **Domain & Safety Primitives (`models.py`, `integrity.py`, `sanitizer.py`)**: Pure data contracts, SHA-256/HMAC chaining, and redaction. Never imports `httpx`, `typer`, `rich`, `pytest`, or transports.
2. **Core Engine (`storage.py`, `matcher.py`, `cassette.py`, `side_effects.py`)**: Persistence, matching, and side-effect guards. Never imports transports, sessions, CLI, or SDK frameworks.
3. **Transports & Session (`transport.py`, `async_transport.py`, `patcher.py`, `session.py`)**: HTTPX interception and lifecycle orchestration. `patcher.py` communicates with `Session` strictly through `ActiveSessionProtocol` so there are no import cycles.
4. **Adapters & Exporters (`integrations/`, `otel.py`, `eval_exporter.py`, `reports.py`)**: SDK wrappers and telemetry/eval/HTML exporters.
5. **Entry Points (`cli.py`, `pytest_plugin.py`)**: User-facing CLI and Pytest plugin.

## Required Local Checks

Before pushing or marking a PR ready for review:

```bash
ruff check .
ruff format --check .
mypy src
lint-imports
pytest -v
```

## Pull Requests

- Use Conventional Commit PR titles (`feat(scope): ...`, `fix(cli): ...`, `docs: ...`), enforced by `.github/workflows/pr-title.yml`.
- Complete the **Author Readiness** checklist in the PR template after reviewing your full diff, verified by `.github/workflows/pr-readiness.yml`.
