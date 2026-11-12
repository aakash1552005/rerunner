---
name: rerunner
description: Inspect AI agent cassettes, diagnose failing or drifting agent trajectories, verify SHA-256 chains and secret scrubbing, fork from any step, and scaffold deterministic pytest regression tests using Rerunner's MCP tools.
---

# Rerunner Agent Workflow

Use Rerunner's MCP server tools whenever working with recorded AI agent sessions (`.jsonl`, `.zst`, `.gz` cassettes) or building deterministic regression suites.

## Core Tools

- `inspect_cassette`: Get cassette metadata and bounded step summaries (`limit`, `offset`, `entry_type`) before reading large HTTP bodies.
- `read_cassette_step`: Fetch detailed request, response, token usage, and `@side_effect` payload for a specific `step`.
- `verify_cassette`: Validate cryptographic SHA-256 hash chaining, scan for leaked API keys/PII, and calculate cost/latency savings.
- `scrub_cassette`: Redact leaked credentials/PII and re-sign the SHA-256 hash chain before committing cassettes to Git.
- `diff_cassettes`: Compare baseline vs candidate cassettes step-by-step for structural, prompt, status, or token drift.
- `fork_and_replay_step`: Truncate a cassette after `step` into a forked cassette so earlier steps replay offline and later steps execute live.
- `scaffold_pytest_regression`: Generate a `@rerunner.replay(...)` pytest regression test from a verified cassette.
- `estimate_savings`: Estimate tokens, USD cost, and CI time saved across a file or cassette directory.

## Recommended Debugging Loop

1. Call `inspect_cassette` first (`limit=20`) to locate the failing or unexpected step.
2. Call `read_cassette_step` only on the step(s) of interest to keep token context minimal.
3. If secrets or PII appear in a recording, run `scrub_cassette` and confirm cleanliness with `verify_cassette`.
4. To reproduce or iterate on a failure without re-paying earlier LLM steps, call `fork_and_replay_step(cassette_path, step=N-1)`.
5. Once fixed, lock the behavior in CI with `scaffold_pytest_regression`.

