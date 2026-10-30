"""Tests verifying the rerunner doctor and rerunner scrub CLI commands."""

from __future__ import annotations

from pathlib import Path
from typer.testing import CliRunner

from rerunner.cassette import Cassette
from rerunner.cli import app
from rerunner.integrity import verify_cassette_integrity
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse

runner = CliRunner(env={"COLUMNS": "200"})


def test_cli_doctor() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Rerunner System Diagnostic" in result.output
    assert "Runtime" in result.output
    assert "Python" in result.output
    assert "Core" in result.output
    assert "typer" in result.output
    assert "rich" in result.output
    assert "pydantic" in result.output
    assert "RERUNNER_RECORD_MODE" in result.output


def test_cli_scrub_removes_secrets_and_rechains_integrity(tmp_path: Path) -> None:
    leaky_file = tmp_path / "leaky_test.jsonl"
    scrubbed_file = tmp_path / "scrubbed_test.jsonl"

    c = Cassette(leaky_file)
    c.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat?key=AIzaSyTestApiKey12345678901234567890",
                headers={
                    "authorization": "Bearer sk-proj-1234567890abcdef1234567890abcdef12345",
                    "x-api-key": "secret-super-key-9999",
                },
                body='{"user": "alice@example.com", "phone": "123-456-7890"}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body='{"reply": "Contact me at bob@corp.com or 987-654-3210"}',
            ),
        )
    )
    c.append(
        CassetteEntry(
            step=2,
            entry_type="side_effect",
            side_effect_name="database_sync",
            side_effect_args=["user@domain.com"],
            side_effect_result={"owner_email": "admin@domain.com"},
        )
    )
    c.save()

    # 1. Verify fails due to leaks
    res_verify_fail = runner.invoke(app, ["verify", str(leaky_file), "--strict"])
    assert res_verify_fail.exit_code == 1
    assert "SECURITY WARNING" in res_verify_fail.output

    # 2. Dry run does not write out changes
    res_dry = runner.invoke(
        app, ["scrub", str(leaky_file), "--output", str(scrubbed_file), "--dry-run"]
    )
    assert res_dry.exit_code == 0
    assert "DRY RUN" in res_dry.output
    assert not scrubbed_file.exists()

    # 3. Perform actual scrub to new file
    res_scrub = runner.invoke(app, ["scrub", str(leaky_file), "--output", str(scrubbed_file)])
    assert res_scrub.exit_code == 0
    assert "Successfully scrubbed and re-signed cassette" in res_scrub.output
    assert scrubbed_file.exists()

    # 4. Verify scrubbed cassette passes verification with strict security
    res_verify_clean = runner.invoke(app, ["verify", str(scrubbed_file), "--strict"])
    assert res_verify_clean.exit_code == 0
    assert "Cryptographic integrity verified successfully" in res_verify_clean.output
    assert "Security scan passed" in res_verify_clean.output

    # 5. Load and confirm content scrubbing & valid hash chaining
    scrubbed = Cassette.load(scrubbed_file)
    assert len(scrubbed.entries) == 2
    assert scrubbed.entries[0].request is not None
    assert scrubbed.entries[0].response is not None
    assert scrubbed.entries[0].request.headers["authorization"] == "[REDACTED]"
    assert scrubbed.entries[0].request.headers["x-api-key"] == "[REDACTED]"
    assert "[REDACTED_EMAIL]" in scrubbed.entries[0].request.body
    assert "[REDACTED_PHONE]" in scrubbed.entries[0].request.body
    assert "[REDACTED_EMAIL]" in scrubbed.entries[0].response.body
    assert "[REDACTED_PHONE]" in scrubbed.entries[0].response.body

    # Check side effect scrubbing
    assert scrubbed.entries[1].side_effect_args == ["[REDACTED_EMAIL]"]
    assert scrubbed.entries[1].side_effect_result == {"owner_email": "[REDACTED_EMAIL]"}

    # Cryptographic integrity
    is_valid, err = verify_cassette_integrity(scrubbed.entries)
    assert is_valid, err
