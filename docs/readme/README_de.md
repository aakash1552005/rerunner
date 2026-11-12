<div align="center">

# 📼 Rerunner

**Deterministischer Flugschreiber, Replay-Engine und CI-Testrunner für KI-Agenten.**

[English](../../README.md) · [中文](README_zh.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · [Español](README_es.md) · **Deutsch**

*Nimm deinen KI-Agenten einmal auf. Spiele ihn in der CI dauerhaft in 0ms und für $0 Token-Kosten ab.*

</div>

## ⚡ Einzeiler-Schnellstart

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## 🚀 Hauptfunktionen

- **$0 CI-Replay**: Zeichnet OpenAI-, Anthropic-, Google-GenAI-, Cohere-, Bedrock-, LangGraph-, AutoGen- und MCP-Aufrufe in JSONL/Zstd-Kassetten auf und spielt sie ohne Netzwerklatenz ab.
- **Nativ für Coding-Agenten (`rerunner mcp`)**: Integrierter stdio-MCP-Server und `SKILL.md`, damit Claude Code, Cursor und Codex Kassetten autonom prüfen, vergleichen, bereinigen und forken können.
- **Sprachübergreifender Proxy (`rerunner serve`)**: Deterministisches Replay inkl. SSE-Streaming für TypeScript/Node, Go, Rust oder Docker via `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`.
- **Sicherheit & Integrität**: Fail-closed `@side_effect`-Schutz, JSON-sichere PII-/Secret-Maskierung, SHA-256-Hashkette und optionale HMAC-SHA256-Signierung.
- **Zeitreise-Debugging (`rerunner fork`)**: Schritte 1–N kostenlos aus der Kassette abspielen und nur Schritt N+1 live gegen das Modell testen.
- **CI-Kostenanalyse & PR-Bot**: `rerunner cost --json` und `action.yml` posten eingesparte Tokens und USD-Kosten direkt als PR-Kommentar.

## 📚 Dokumentation & Benchmarks

- [Dokumentationsseite](https://aakash1552005.github.io/rerunner/)
- [Benchmark-Ergebnisse](../benchmarks.md)
- [Onboarding](../ONBOARDING.md) · [Tutorial](../TUTORIAL.md)

