"""Unit tests for Rerunner dataset evaluation exporter and `rerunner export-eval` CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typer.testing import CliRunner

from rerunner.cli import app
from rerunner.eval_exporter import export_cassette_to_eval_format
from rerunner.cassette import Cassette
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

runner = CliRunner()


def _create_dummy_chat_cassette(cassette_path: Path) -> None:
    cassette = Cassette(path=cassette_path)

    req_body = json.dumps(
        {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain deterministic testing in one sentence."},
            ],
        }
    )
    resp_body = json.dumps(
        {
            "id": "chatcmpl-test",
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Deterministic testing guarantees that the exact same inputs yield identical outputs every single time.",
                    }
                }
            ],
        }
    )

    entry = CassetteEntry(
        step=1,
        entry_type="http",
        timestamp=1700000000.0,
        request=RecordedRequest(
            method="POST",
            url="https://api.openai.com/v1/chat/completions",
            headers={"content-type": "application/json"},
            body=req_body,
        ),
        response=RecordedResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=resp_body,
        ),
    )
    cassette.append(entry)
    cassette.save()


def test_export_openai_chat_format(tmp_path):
    cassette_file = tmp_path / "chat_cassette.jsonl"
    _create_dummy_chat_cassette(cassette_file)

    eval_output = tmp_path / "eval_openai.jsonl"
    summary = export_cassette_to_eval_format(cassette_file, eval_output, format_type="openai")

    assert summary["exported_records"] == 1
    assert eval_output.exists()

    lines = [
        json.loads(line) for line in eval_output.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(lines) == 1
    assert "messages" in lines[0]
    messages = lines[0]["messages"]
    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert "Deterministic testing guarantees" in messages[2]["content"]


def test_export_sharegpt_format(tmp_path):
    cassette_file = tmp_path / "chat_cassette.jsonl"
    _create_dummy_chat_cassette(cassette_file)

    eval_output = tmp_path / "eval_sharegpt.jsonl"
    summary = export_cassette_to_eval_format(cassette_file, eval_output, format_type="sharegpt")

    assert summary["exported_records"] == 1
    lines = [
        json.loads(line) for line in eval_output.read_text(encoding="utf-8").splitlines() if line
    ]
    assert "conversations" in lines[0]
    convs = lines[0]["conversations"]
    assert convs[0]["from"] == "system"
    assert convs[1]["from"] == "human"
    assert convs[2]["from"] == "gpt"


def test_export_huggingface_format(tmp_path):
    cassette_file = tmp_path / "chat_cassette.jsonl"
    _create_dummy_chat_cassette(cassette_file)

    eval_output = tmp_path / "eval_hf.jsonl"
    summary = export_cassette_to_eval_format(cassette_file, eval_output, format_type="huggingface")

    assert summary["exported_records"] == 1
    lines = [
        json.loads(line) for line in eval_output.read_text(encoding="utf-8").splitlines() if line
    ]
    assert "instruction" in lines[0]
    assert "input" in lines[0]
    assert "output" in lines[0]
    assert lines[0]["instruction"] == "Explain deterministic testing in one sentence."
    assert "Deterministic testing guarantees" in lines[0]["output"]


def test_cli_export_eval_command(tmp_path):
    cassette_file = tmp_path / "cli_cassette.jsonl"
    _create_dummy_chat_cassette(cassette_file)

    out_file = tmp_path / "out_eval.jsonl"
    res = runner.invoke(
        app, ["export-eval", str(cassette_file), "-o", str(out_file), "--format", "openai"]
    )
    assert res.exit_code == 0
    assert out_file.exists()
    assert "Successfully exported cassette to OPENAI eval format" in res.stdout
