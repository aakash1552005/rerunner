<div align="center">

# 📼 Rerunner

**AI 에이전트를 위한 결정론적 비행 기록 장치, 리플레이 엔진 및 CI 테스트 러너.**

[English](../../README.md) · [中文](README_zh.md) · [日本語](README_ja.md) · **한국어** · [Español](README_es.md) · [Deutsch](README_de.md)

*AI 에이전트를 한 번만 녹화하세요. CI에서 0ms 지연 시간과 $0 토큰 비용으로 영원히 재현합니다.*

</div>

## ⚡ 한 줄 빠른 시작

```bash
pip install rerunner && rerunner setup --clients claude,cursor,codex
```

## 🚀 핵심 기능

- **$0 CI 리플레이**: OpenAI, Anthropic, Google GenAI, Cohere, Bedrock, LangGraph, AutoGen 및 MCP 트래픽을 JSONL/Zstd 카세트에 기록하고 CI에서 네트워크 호출 없이 리플레이합니다.
- **AI 코딩 에이전트 네이티브 (`rerunner mcp`)**: Claude Code, Cursor, Codex가 카세트 검사, 비교(diff), PII 마스킹 및 스텝 포크를 직접 수행할 수 있는 stdio MCP 서버를 제공합니다.
- **다국어 범용 프록시 (`rerunner serve`)**: `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL`을 통해 TypeScript/Node, Go, Rust 및 Docker 환경에서도 SSE 스트리밍을 포함한 결정론적 리플레이를 지원합니다.
- **보안 및 무결성 검증**: Fail-closed `@side_effect` 가드, JSON 안전 PII/시크릿 마스킹, SHA-256 해시 체인 및 선택적 HMAC-SHA256 서명을 제공합니다.
- **타임 트래블 디버깅 (`rerunner fork`)**: 1~N단계를 무료로 리플레이하고 N+1단계만 실제 모델에 실행하여 수정 사항을 즉시 검증합니다.
- **CI 비용 추정 및 PR 코멘트 봇**: `rerunner cost --json`과 `action.yml`로 PR에 절감된 토큰과 비용 요약을 자동 게시합니다.

## 📚 문서 및 벤치마크

- [공식 문서 사이트](https://aakash1552005.github.io/rerunner/)
- [벤치마크 결과](../benchmarks.md)
- [온보딩 가이드](../ONBOARDING.md) · [튜토리얼](../TUTORIAL.md)

