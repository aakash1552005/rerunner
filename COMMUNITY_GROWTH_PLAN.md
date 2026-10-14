# 📅 Rerunner 30-Day Contributor Growth Playbook & Calendar

This playbook guides the execution of the 30-day growth plan for `rerunner`, targeting **Goal A (Conservative: 6 new contributors, 8 external PRs, $\le$ 48h response SLA)**.

---

## 🗓️ Contributor Milestones & Check-in Date Slots

| Day | Date Slot | Phase | Key Objective | You Can Ping Me For... |
| :---: | :---: | :---: | :--- | :--- |
| **0** | **Today (Oct 14)** | **Week 0: Foundation** | Setup `ONBOARDING.md`, `AUTHORS.md`, `Makefile`, issue templates | ✅ Completed & verified |
| **3** | **Oct 17, 2026** | **Week 1: Seed Issues** | Post the 4 initial `good first issue` tickets on GitHub & announce on social | Reviewing issue drafts, tailoring announcement copy |
| **7** | **Oct 21, 2026** | **Week 1: First Triage** | Check assigned tickets, triage incoming questions within 48h SLA | Reviewing contributor questions, pairing assistance |
| **14** | **Oct 28, 2026** | **Week 2: First Merges** | Review & merge first 3 external PRs, add names to `AUTHORS.md` | Conducting code reviews, checking DCO/lint, drafting praise comments |
| **21** | **Nov 04, 2026** | **Week 3: Scale Sprint** | Post batch 2 issues (LlamaIndex / CrewAI / AutoGen wrappers) | Scoping architectural issues, setting up mock fixtures |
| **30** | **Nov 13, 2026** | **Week 4: Celebration** | Measure KPIs, release v0.2.2/v0.3.0 notes celebrating contributors | Aggregating release notes, updating contributor hall of fame |

---

## 📦 Ready-to-Post Initial Issue Templates (Post on Oct 17)

Copy and paste these exact issues into GitHub:

### Issue 1: `[good-first-issue] Add CLI --help and --version integration tests`
* **Labels:** `good first issue`, `testing`, `cli`
* **Estimated Time:** 20–30 minutes
* **Description:**
```markdown
### Background
Rerunner includes a Typer-based CLI (`rerunner.cli`), but we need dedicated integration tests ensuring that top-level flags like `--help` and `--version` display formatted outputs and exit with code 0.

### Expected Steps
1. Open `tests/test_cli.py`.
2. Use Typer's `CliRunner` to invoke `app` with `["--help"]` and assert `result.exit_code == 0`.
3. Invoke `app` with `["--version"]` and assert `result.exit_code == 0` and that `__version__` appears in stdout.
4. Run `pytest tests/test_cli.py` to verify.

### Useful Commands
- Run test: `pytest tests/test_cli.py`
- Lint: `ruff check tests/test_cli.py`

### Help & Mentorship
Need help? Drop a comment below and mention @aakash1552005!
```

---

### Issue 2: `[good-first-issue] Add cookbook example for OpenAI Structured Outputs`
* **Labels:** `good first issue`, `documentation`, `examples`
* **Estimated Time:** 30–45 minutes
* **Description:**
```markdown
### Background
Rerunner supports deterministic recording and replaying of OpenAI SDK calls. We want a clear cookbook example showing how `rerunner.session.record` and `replay` work with OpenAI's `client.beta.chat.completions.parse()` (Structured Outputs using Pydantic).

### Expected Steps
1. Create `examples/openai_structured_outputs.py`.
2. Define a simple Pydantic response model (e.g., `CityInfo(name=str, country=str, population=int)`).
3. Demonstrate a recorded session that writes to `cassettes/openai_structured.jsonl`.
4. Demonstrate a replay session showing $0 token usage and instant response.
5. Add a test in `tests/test_integrations.py` or standalone test script.

### Help & Mentorship
Drop a comment below and we will assign the ticket to you!
```

---

### Issue 3: `[good-first-issue] Add CVV and Bearer JWT sanitization regexes`
* **Labels:** `good first issue`, `security`, `enhancement`
* **Estimated Time:** 20–30 minutes
* **Description:**
```markdown
### Background
`rerunner.sanitizer` masks sensitive tokens and PII before cassettes are written to disk. We want to add explicit pattern matching for Credit Card CVV (3-4 digit codes adjacent to CVV labels) and standard 3-segment JWT tokens.

### Expected Steps
1. In `src/rerunner/sanitizer.py`, add regex patterns to `SECRET_PATTERNS` for JWT tokens (`eyJ...`).
2. Add corresponding tests in `tests/test_sanitizer.py`.
3. Run `pytest tests/test_sanitizer.py` and `ruff check src tests`.

### Help & Mentorship
Mention @aakash1552005 for quick guidance!
```

---

## 💬 Ready-to-Use Response Templates

### Welcome & First-Response Comment (Within 24–48h)
```markdown
Hi @{user} — thanks for opening this! This is a fantastic contribution. Welcome to Rerunner 👋

I’ll review your PR within 24–48 hours. In the meantime, please ensure:
- [ ] You ran `pytest` and all tests pass locally.
- [ ] Your commits include DCO sign-off (`git commit -s`).

If you have any questions or get stuck, feel free to ask here. Thanks for helping make Rerunner better!
```

### PR Merge & Praise Comment
```markdown
Awesome work, @{user}! Merging this in now 🚀

Thank you for your contribution to Rerunner. We have added you to [`AUTHORS.md`](https://github.com/aakash1552005/rerunner/blob/main/AUTHORS.md) and will celebrate your work in our next release notes! 🎉
```
