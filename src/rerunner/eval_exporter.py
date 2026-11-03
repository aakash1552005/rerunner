"""Dataset and benchmark evaluation exporter for Rerunner cassettes.

Extracts recorded agent conversations and transforms them into standard
LLM fine-tuning and evaluation formats:
- OpenAI ChatCompletion JSONL (`messages`: `[{role, content}, ...]`)
- ShareGPT JSONL (`conversations`: `[{from, value}, ...]`)
- HuggingFace Alpaca JSONL (`instruction`, `input`, `output`)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry


def _extract_messages_from_entry(entry: CassetteEntry) -> tuple[list[dict[str, str]], str | None]:
    """Extract input message history and assistant output from a recorded HTTP cassette entry."""
    if entry.entry_type != "http" or not entry.request or not entry.response:
        return [], None

    messages: list[dict[str, str]] = []
    assistant_output: str | None = None

    # 1. Parse Request Body
    try:
        req_data = json.loads(entry.request.body)
        if isinstance(req_data, dict):
            # OpenAI / Anthropic / Standard chat format
            if "messages" in req_data and isinstance(req_data["messages"], list):
                for msg in req_data["messages"]:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        # Multi-modal / block contents: extract text parts
                        text_parts = [
                            p.get("text", "")
                            for p in content
                            if isinstance(p, dict) and "text" in p
                        ]
                        content = " ".join(text_parts) if text_parts else str(content)
                    messages.append({"role": role, "content": str(content)})
            elif "contents" in req_data and isinstance(req_data["contents"], list):
                # Google Gemini / GenAI format
                for item in req_data["contents"]:
                    role = "assistant" if item.get("role") == "model" else "user"
                    parts = item.get("parts", [])
                    text = " ".join(
                        p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p
                    )
                    messages.append({"role": role, "content": text})
            elif "prompt" in req_data and isinstance(req_data["prompt"], str):
                messages.append({"role": "user", "content": req_data["prompt"]})
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):  # nosec B110
        # If not JSON, ignore request body
        pass

    # 2. Parse Response Body
    try:
        resp_data = json.loads(entry.response.body)
        if isinstance(resp_data, dict):
            # OpenAI format
            if (
                "choices" in resp_data
                and isinstance(resp_data["choices"], list)
                and resp_data["choices"]
            ):
                choice = resp_data["choices"][0]
                if isinstance(choice, dict):
                    msg = choice.get("message", {})
                    if isinstance(msg, dict):
                        assistant_output = msg.get("content")
            # Anthropic Claude format
            elif "content" in resp_data and isinstance(resp_data["content"], list):
                text_blocks = [
                    block.get("text", "")
                    for block in resp_data["content"]
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                if text_blocks:
                    assistant_output = "".join(text_blocks)
            # Google Gemini format
            elif "candidates" in resp_data and isinstance(resp_data["candidates"], list):
                candidate = resp_data["candidates"][0]
                content_obj = candidate.get("content", {})
                parts = content_obj.get("parts", [])
                assistant_output = "".join(
                    p.get("text", "") for p in parts if isinstance(p, dict) and "text" in p
                )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):  # nosec B110
        # If not JSON or raw string
        pass

    return messages, assistant_output


def export_cassette_to_eval_format(
    cassette_path: Path | str,
    output_path: Path | str,
    format_type: Literal["openai", "sharegpt", "huggingface"] = "openai",
) -> dict[str, Any]:
    """Convert recorded cassette conversations into standard dataset formats.

    Args:
        cassette_path: Source cassette path (.jsonl, .zst, .gz)
        output_path: Destination JSONL file path
        format_type: One of 'openai', 'sharegpt', or 'huggingface'

    Returns:
        Summary dict containing counts and export metadata.
    """
    cassette = Cassette.load(Path(cassette_path), verify_integrity=False)
    output_records: list[dict[str, Any]] = []

    for entry in cassette.entries:
        input_messages, assistant_output = _extract_messages_from_entry(entry)
        if not input_messages or assistant_output is None:
            continue

        if format_type == "openai":
            record_messages = list(input_messages)
            record_messages.append({"role": "assistant", "content": assistant_output})
            output_records.append({"messages": record_messages})

        elif format_type == "sharegpt":
            conversations = []
            for msg in input_messages:
                sender = "human" if msg["role"] == "user" else msg["role"]
                conversations.append({"from": sender, "value": msg["content"]})
            conversations.append({"from": "gpt", "value": assistant_output})
            output_records.append({"conversations": conversations})

        elif format_type == "huggingface":
            # Extract last user query as instruction
            last_user_msg = next(
                (m["content"] for m in reversed(input_messages) if m["role"] == "user"), ""
            )
            # Context before last user message
            context_msgs = [m for m in input_messages if m["content"] != last_user_msg]
            context = "\n".join(f"{m['role']}: {m['content']}" for m in context_msgs)

            output_records.append(
                {
                    "instruction": last_user_msg,
                    "input": context,
                    "output": assistant_output,
                }
            )

    target_file = Path(output_path)
    target_file.parent.mkdir(parents=True, exist_ok=True)

    with target_file.open("w", encoding="utf-8") as f:
        for rec in output_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    return {
        "format": format_type,
        "exported_records": len(output_records),
        "source": str(cassette_path),
        "destination": str(target_file),
    }
