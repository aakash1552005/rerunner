<div align="center">

# 📼 Rerunner

**面向 AI Agent 的确定性飞行记录仪、重放引擎与 CI 测试运行器。**

[English](../../README.md) · **中文** · [日本語](README_ja.md) · [한국어](README_ko.md) · [Español](README_es.md) · [Deutsch](README_de.md)

*录制一次 AI Agent，在 CI 中以 0ms 延迟和 $0 Token 成本永久确定性重放。*

</div>

## ⚡ 一行代码快速开始

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## 🚀 核心能力

- **$0 CI 重放**：将 OpenAI、Anthropic、Google GenAI、Cohere、Bedrock、LangGraph、AutoGen 与 MCP 调用录制为仅追加的 JSONL/Zstd 磁带（Cassette），在 CI 中零网络延迟重放。
- **AI Coding Agent 原生集成 (`rerunner mcp`)**：内置 stdio MCP 服务器与 `SKILL.md`，让 Claude Code、Cursor 和 Codex 自动检查、对比、脱敏并分叉调试失败的磁带。
- **跨语言通用代理 (`rerunner serve`)**：通过 `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` 为 TypeScript/Node、Go、Rust 或 Docker 微服务提供确定性重放（支持 SSE 流式输出）。
- **默认安全与防篡改**：Fail-closed `@side_effect` 守卫、JSON 安全的 PII/密钥脱敏、SHA-256 哈希链与可选 HMAC-SHA256 签名。
- **时间旅行调试 (`rerunner fork`)**：从磁带免费重放第 1–N 步，仅在第 N+1 步实时请求模型以验证修复。
- **CI 成本统计与 PR 评论机器人**：通过 `rerunner cost --json` 与 `action.yml` 在 PR 上自动发布节省的 Token 与美元金额摘要。

## 📚 文档与基准测试

- [完整文档站点](https://aakash1552005.github.io/rerunner/)
- [基准测试报告](../benchmarks.md)
- [新手引导](../ONBOARDING.md) · [教程](../TUTORIAL.md)

