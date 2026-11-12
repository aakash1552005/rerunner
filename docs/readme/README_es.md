<div align="center">

# 📼 Rerunner

**Grabadora de vuelo determinista, motor de reproducción y runner de pruebas en CI para agentes de IA.**

[English](../../README.md) · [中文](README_zh.md) · [日本語](README_ja.md) · [한국어](README_ko.md) · **Español** · [Deutsch](README_de.md)

*Graba tu agente de IA una vez. Reprodúcelo para siempre en CI en 0ms y con $0 en tokens.*

</div>

## ⚡ Inicio rápido en 1 línea

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## 🚀 Características principales

- **Reproducción en CI por $0**: Graba tráfico de OpenAI, Anthropic, Google GenAI, Cohere, Bedrock, LangGraph, AutoGen y MCP en casetes JSONL/Zstd y reprodúcelo sin latencia de red.
- **Nativo para agentes de programación (`rerunner mcp`)**: Servidor MCP por stdio y `SKILL.md` para que Claude Code, Cursor y Codex inspeccionen, comparen, anonimicen y bifurquen casetes automáticamente.
- **Proxy universal multi-lenguaje (`rerunner serve`)**: Reproduce tráfico LLM y SSE en TypeScript/Node, Go, Rust o Docker usando `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`.
- **Seguridad e integridad**: Protección fail-closed `@side_effect`, redacción de PII/secretos segura para JSON, cadena de hashes SHA-256 y firma opcional HMAC-SHA256.
- **Depuración con viaje en el tiempo (`rerunner fork`)**: Reproduce los pasos 1–N gratis desde el casete y ejecuta en vivo solo el paso N+1.
- **Estimación de costes y bot de PR**: `rerunner cost --json` y `action.yml` publican automáticamente el ahorro de tokens y dólares en tus Pull Requests.

## 📚 Documentación y Benchmarks

- [Sitio de documentación](https://aakash1552005.github.io/rerunner/)
- [Resultados de benchmarks](../benchmarks.md)
- [Guía de inicio](../ONBOARDING.md) · [Tutorial](../TUTORIAL.md)

