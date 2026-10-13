# Cache recorded cassettes in GitHub Actions

Rerunner's pytest plugin replays cassettes by default, so a pull request can run
agent tests without API calls or model credentials. Keep cassette paths stable
and cache only the recorded `.jsonl` files that the tests use.

## 1. Use a stable cassette path

Point the marker at a repository-relative path, for example:

```python
import pytest


@pytest.mark.rerunner("tests/fixtures/agent_run.jsonl")
def test_agent_decision(rerunner_transport):
    ...
```

Record or refresh cassettes locally when the interaction changes:

```bash
pytest --rerunner-record
rerunner verify tests/fixtures/agent_run.jsonl
```

Inspect the resulting files before committing them. They must contain only
sanitized, synthetic data; never put API keys, tokens, customer data, or other
secrets into a cassette or a cache.

## 2. Add a replay workflow

Save this as `.github/workflows/replay.yml`:

```yaml
name: Replay agent tests

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  replay:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    steps:
      - name: Check out the repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install Rerunner and test dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev]"

      - name: Cache recorded cassettes
        uses: actions/cache@v4
        with:
          path: tests/fixtures/**/*.jsonl
          key: rerunner-cassettes-v1-${{ runner.os }}-py${{ matrix.python-version }}-${{ hashFiles('tests/fixtures/**/*.jsonl') }}
          restore-keys: |
            rerunner-cassettes-v1-${{ runner.os }}-py${{ matrix.python-version }}-

      - name: Run replay-only tests
        run: pytest
```

The default `pytest` mode is replay-only. The workflow therefore does not need
an API key and does not call a model. The cache key changes when a cassette
changes, while `restore-keys` can reuse the latest compatible cassette cache
from the same Python version.

GitHub Actions can restore a cache from the default branch for a pull request,
but a pull request from a fork may not be allowed to save a new cache. Seed the
default-branch cache with reviewed cassettes, or commit the sanitized cassettes
needed by the tests so a cache miss remains deterministic.

## Security notes

Use `pull_request` for untrusted contributions. Do not switch this workflow to
`pull_request_target` just to obtain write access to caches or secrets. Caches
can be readable by people who can open pull requests, so treat them as public
artifacts and review every cassette before it is cached. See GitHub's
[dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
for cache scope and pull-request restrictions.
