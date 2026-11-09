# CrewAI Multi-Agent Deterministic Replay with Rerunner

This tutorial demonstrates how to use **Rerunner** to record and deterministically replay multi-agent workflows created with **CrewAI** (or custom multi-agent architectures).

## Why Deterministic Replay for Multi-Agent Systems?

Multi-agent frameworks like CrewAI involve sequential or hierarchical interactions across multiple specialized agents (e.g. Researcher $\rightarrow$ Writer $\rightarrow$ Reviewer). Testing them in CI or during local development normally causes:
1. **Flaky assertions** due to non-deterministic model completions.
2. **High API costs** ($$$) spent repeating the same agent turns.
3. **Slow test suites** bound by LLM generation latencies.

With Rerunner, you record the crew's interactions **once** into a lightweight compressed cassette (`.zst`). Future CI runs and regression tests replay the entire multi-turn exchange **in milliseconds with zero API costs**.

---

## Quickstart

### 1. Run the Standalone Example
```bash
python examples/crewai/05_crewai_multi_agent.py
```

### 2. Run the Pytest Test
```bash
pytest examples/crewai/test_crewai_replay.py
```

---

## How It Works

### Wrapping Crew Execution with a Rerunner Session

```python
from rerunner import Session

# 1. Record Mode (Live execution)
with Session(cassette_path="crew_session.zst", mode="record") as session:
    # Any HTTP client used by CrewAI (or LiteLLM/OpenAI) is recorded
    client = session.get_client()
    ...

# 2. Replay Mode (CI / Offline test)
with Session(cassette_path="crew_session.zst", mode="replay") as session:
    client = session.get_client()
    # Replays sequential multi-agent prompts with 100% fidelity & zero network access!
```

