# 🚀 First-Time Contributor Onboarding Guide

Welcome to **Rerunner**! We are thrilled you want to contribute to the open-source flight recorder and deterministic CI test runner for agentic AI applications.

This guide provides a frictionless, step-by-step walkthrough to get your local environment running and land your first merged pull request in **under 30 minutes**.

---

## ⏱️ The 5-Minute Setup

### 1. Fork and Clone
```bash
# Clone your fork
git clone https://github.com/<your-username>/rerunner.git
cd rerunner

# Add the official upstream repository
git remote add upstream https://github.com/aakash1552005/rerunner.git
```

### 2. Create a Virtual Environment
```bash
# Using Python 3.11+
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On Windows (Command Prompt):
.venv\Scripts\activate.bat
```

### 3. Install in Editable Mode
```bash
# Install core dependencies + dev testing tools
pip install -e ".[dev]"
```

### 4. Verify Local Tests Pass
```bash
# Run the test suite
pytest

# Or if you have 'make' installed:
make test
```
If you see **all tests passing**, your local development environment is 100% verified!

---

## 🎯 How to Pick Your First Task

We tag issues with levels of complexity so you can start with a quick, easy win:

1. **[`good first issue`](https://github.com/aakash1552005/rerunner/labels/good%20first%20issue)**: Well-scoped, bite-sized tasks (20–60 minutes) with explicit instructions, target files, and test commands provided.
2. **[`documentation`](https://github.com/aakash1552005/rerunner/labels/documentation)**: Improving guides, clarifying error messages, adding cookbook examples.
3. **[`help wanted`](https://github.com/aakash1552005/rerunner/labels/help%20wanted)**: New agent framework integrations (e.g., LlamaIndex, CrewAI, AutoGen) and CLI features.

> 💡 **Tip:** Before writing code, drop a quick comment on the issue saying *"I'd like to work on this!"* so maintainers can assign it to you and avoid duplicate efforts.

---

## 🛠️ Development Workflow

### 1. Create a Topic Branch
```bash
git checkout main
git pull upstream main
git checkout -b fix/short-description
```

### 2. Code Quality & Formatting
We use **Ruff** for linting/formatting and **MyPy** for strict static typing:
```bash
# Format your code automatically
make format
# Or: ruff format src tests

# Run linter
make lint
# Or: ruff check src tests

# Run type checker
make typecheck
# Or: mypy src tests
```

### 3. Commit with DCO Sign-off
We require the **Developer Certificate of Origin (DCO)** on all commits. Simply add the `-s` flag when committing:
```bash
git commit -s -m "fix(cli): clarify error message when cassette is missing"
```

### 4. Push and Open a PR
```bash
git push -u origin fix/short-description
```
Then visit [github.com/aakash1552005/rerunner](https://github.com/aakash1552005/rerunner) and click **"Compare & pull request"**.

---

## 🤝 What to Expect from Maintainers

- **Fast First Response:** We aim to review or acknowledge every newcomer PR within **24–48 hours**.
- **Friendly, Constructive Reviews:** We will guide you through any CI failures or style adjustments.
- **Permanent Recognition:** Once merged, your name and GitHub profile will be added to [`AUTHORS.md`](../AUTHORS.md) and celebrated in our release notes!

---

## 💬 Getting Help
- **GitHub Discussions:** Ask questions in [Q&A / Onboarding Discussions](https://github.com/aakash1552005/rerunner/discussions).
- **Issue Comments:** If you get stuck on an assigned issue, mention `@aakash1552005` with your question. We are happy to pair or provide hints!
