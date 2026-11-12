<div align="center">

# 📼 Rerunner

**AI エージェントのための決定論的フライトレコーダー、リプレイエンジン、CI テストランナー。**

[English](../../README.md) · [中文](README_zh.md) · **日本語** · [한국어](README_ko.md) · [Español](README_es.md) · [Deutsch](README_de.md)

*AI エージェントを一度記録すれば、CI 上で 0ms・$0 トークンで何度でも再現できます。*

</div>

## ⚡ 1行クイックスタート

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## 🚀 主な機能

- **$0 CI リプレイ**：OpenAI、Anthropic、Google GenAI、Cohere、Bedrock、LangGraph、AutoGen、MCP の通信を追記型 JSONL/Zstd カセットに記録し、CI でネットワーク遅延ゼロでリプレイします。
- **AI コーディングエージェント対応 (`rerunner mcp`)**：Claude Code、Cursor、Codex がカセットの検査・差分比較・PII 除去・ステップ分岐を自律実行できる stdio MCP サーバーを搭載。
- **多言語ユニバーサルプロキシ (`rerunner serve`)**：`OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` を通じて TypeScript/Node、Go、Rust、Docker サービスでも決定論的リプレイと SSE ストリーミングを利用可能。
- **エンタープライズ級の安全性**：Fail-closed `@side_effect` ガード、JSON 構造を壊さない PII/シークレットマスキング、SHA-256 ハッシュチェーンおよび HMAC-SHA256 署名に対応。
- **タイムトラベルデバッグ (`rerunner fork`)**：ステップ 1〜N をローカルから無料でリプレイし、ステップ N+1 だけをライブ実行して修正を検証できます。
- **CI コスト集計 & PR コメントボット**：`rerunner cost --json` と `action.yml` により、節約したトークン数と API 費用を PR に自動投稿します。

## 📚 ドキュメント・ベンチマーク

- [ドキュメントサイト](https://aakash1552005.github.io/rerunner/)
- [ベンチマーク結果](../benchmarks.md)
- [オンボーディング](../ONBOARDING.md) · [チュートリアル](../TUTORIAL.md)

