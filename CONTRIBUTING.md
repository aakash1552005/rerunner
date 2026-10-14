# Contributing to Rerunner

Thank you for your interest in contributing to **Rerunner**! We are building the industry standard for deterministic AI agent testing, replay, and CI/CD pipelines.

Whether you're fixing a bug, adding an SDK transport adapter, optimizing request matching, or improving documentation, your contributions are welcome.

---

## Code of Conduct

All contributors and participants must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to security@rerunner.dev.

---

## Development Setup

We recommend using [uv](https://github.com/astral-sh/uv) or a standard Python virtual environment (Python 3.11+ required).

```bash
# 1. Clone the repository
git clone https://github.com/aakash1552005/rerunner.git
cd rerunner


# 2. Create and activate a virtual environment
python -m venv .venv
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# 3. Install in editable mode with development dependencies
pip install -e ".[dev]"
```

---

## Code Quality Standards

We enforce strict quality standards identical to leading AI and MLOps open-source projects:

### 1. Formatting and Linting
We use [Ruff](https://github.com/astral-sh/ruff) for fast, consistent linting and formatting:
```bash
# Check code style
ruff check .

# Automatically fix format issues
ruff format .
```

### 2. Strict Type Checking
Rerunner is 100% typed with zero `Any` in public APIs:
```bash
mypy src tests
```

### 3. Running Tests
Run the entire test suite locally:
```bash
pytest
```

---

## Pull Request Guidelines

1. **Keep PRs focused**: Each pull request should address a single issue or implement a single feature.
2. **Include tests**: Every bug fix or new feature must be accompanied by comprehensive unit tests.
3. **Update documentation**: If changing user-facing APIs or CLI behavior, update docstrings and README.
4. **Follow conventional commits**:
   - `feat:` for new capabilities
   - `fix:` for bug fixes
   - `docs:` for documentation updates
   - `test:` for test additions or refactors
   - `chore:` for tooling and dependencies

---

## Contribution Tracks

We have organized high-impact work into distinct tracks so contributors can align with their domain expertise:

| Track | Focus Areas | Example PRs |
| :--- | :--- | :--- |
| **Frontier AI Ecosystem** | Agent framework adapters, SDK transports | Google GenAI, AutoGen, CrewAI, LlamaIndex |
| **Enterprise Governance** | Security, compliance, auditing | Presidio PII redaction, Ed25519 signing, secret scrubbers |
| **Observability & MLOps** | Traces, metrics, cloud exporters | OpenTelemetry (OTel), Datadog, Prometheus |
| **Cloud Infrastructure** | Remote cassette caching, storage drivers | AWS S3, Google Cloud Storage, Azure Blob |
| **Developer Experience** | Pytest fixtures, CLI tooling, visualizers | GitHub Actions, diff enhancements, Rich UI |

---

## Proposing Architecture Changes (RFCs)

For major architectural proposals, new protocols, or significant API additions, please submit an **[RFC (Request for Comments)](.github/ISSUE_TEMPLATE/rfc.yml)** first.

1. **Open an RFC issue**: Use our RFC issue template to outline motivation, enterprise impact, and technical specification.
2. **Community Discussion**: Gather input from maintainers and industry peers.
3. **Implementation**: Once aligned, submit PRs referencing the RFC issue number.

---

## How to Get Involved

Check out issues on GitHub:
- [`good first issue`](https://github.com/aakash1552005/rerunner/labels/good%20first%20issue): Well-scoped, bite-sized tasks with code pointers.
- [`help wanted`](https://github.com/aakash1552005/rerunner/labels/help%20wanted): High-priority ecosystem integrations and enterprise features.
- [`rfc`](https://github.com/aakash1552005/rerunner/labels/rfc): Architectural proposals actively seeking feedback.

---

## Recognition & Community

Every contribution matters. Contributors are recognized in:
- The [GitHub Release Notes](https://github.com/aakash1552005/rerunner/releases) for each version.
- The community [AUTHORS.md](AUTHORS.md) Contributor Hall of Fame.
- The project documentation and changelogs.
- High-impact contributors are invited to join the project core triage team.

If you have questions, ideas, or need guidance on an implementation, feel free to start a thread on [GitHub Discussions](https://github.com/aakash1552005/rerunner/discussions) or open an issue.

---

## License

By contributing to Rerunner, you agree that your contributions will be licensed under the project's [Apache 2.0 License](LICENSE).
