# Architecture

Rerunner enforces strict inward dependency boundaries via `import-linter` (`lint-imports`) so core data models, integrity, matching, redaction, and storage remain decoupled from transports, integrations, CLI, and MCP interfaces.

```mermaid
flowchart LR
  CLI["cli / mcp_server / setup_wizard / proxy_server"] --> Session["session / transport"]
  Integrations["integrations/*"] --> Session
  Session --> Core["cassette / matcher / integrity / sanitizer / storage"]
  Core --> Models["models"]
```

For the full module-boundary diagram, see [architecture/architecture.mermaid](architecture/architecture.mermaid).

