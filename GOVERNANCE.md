# Project Governance

**Rerunner** is an open-source, community-governed project dedicated to deterministic, cost-effective, and safe testing for autonomous AI agents.

This document describes how the project is managed, how decisions are made, and how contributors earn maintainer roles.

---

## 🎯 Core Values

1. **Transparency**: All discussions, roadmaps, architecture proposals (RFCs), and releases happen publicly on GitHub.
2. **Speed & Reliability**: We maintain a strict **24–48 hour SLA** on initial reviews for community issues and pull requests.
3. **Enterprise Safety**: We treat security, PII hygiene, deterministic cryptographic integrity, and compliance as first-class citizens.
4. **Welcoming Meritocracy**: Anyone who consistently contributes quality code, reviews, documentation, or RFCs can earn committer and maintainer privileges.

---

## 👥 Roles & Responsibilities

### 1. Contributors
Everyone who submits an issue, pull request, documentation update, or architectural feedback.
* **Responsibilities**: Adhere to our [Code of Conduct](CODE_OF_CONDUCT.md), follow [CONTRIBUTING.md](CONTRIBUTING.md), and ensure all tests pass.

### 2. Reviewers & Triagers
Experienced contributors who actively review pull requests, reproduce reported bugs, and assist new contributors with onboarding.
* **Privileges**: Issue triage permissions, PR review assignments.
* **Path**: Consistent participation, high-quality reviews on at least 3 pull requests.

### 3. Core Maintainers
Maintainers hold write access to the repository and publishing credentials.
* **Responsibilities**:
  - Review and merge pull requests.
  - Steer the architectural roadmap via [Enterprise RFCs](rfcs/).
  - Ensure zero regressions in CI and maintain release health.
  - Protect user security and respond to vulnerabilities per [SECURITY.md](SECURITY.md).
* **Current Lead Maintainer**: Aakash S S ([@aakash1552005](https://github.com/aakash1552005))

---

## 🏛️ Decision-Making Process

* **Routine Fixes & Minor Enhancements**: Merged upon receiving approval from at least one Core Maintainer and passing 100% of CI tests.
* **Major Architectural Shifts & Integrations**: Must go through our [RFC process](rfcs/README.md). An RFC is open for community comment for a minimum of 72 hours before formal adoption.
* **Consensus Seeking**: We strive for consensus among active contributors. In the rare event of deadlock, the Lead Maintainer has final decision authority to maintain momentum.

---

## 🌟 Contributor Ladder

We believe in elevating top contributors:
1. **Tier 1 (First-Time Contributor)**: Merges first PR $\rightarrow$ Listed in [AUTHORS.md](AUTHORS.md) and Release Notes.
2. **Tier 2 (Regular Contributor)**: 3+ merged contributions $\rightarrow$ Invited to triage issues and co-author RFCs.
3. **Tier 3 (Core Maintainer)**: Consistent leadership across integrations, CI, or security $\rightarrow$ Nominated and voted in by existing maintainers.

---

## 🤝 Questions & Community
Have questions about governance or wish to sponsor/partner with Rerunner? Open a discussion or reach out to maintainers via GitHub Issues.
