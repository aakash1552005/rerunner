"""Tests verifying the rerunner doctor and rerunner scrub CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
import re

import pytest
import httpx
from pydantic import BaseModel, EmailStr, UUID4, PaymentCardNumber, Field
from typer.main import get_command
from typer.testing import CliRunner

from rerunner.cassette import Cassette
from rerunner.cli import app
from rerunner.integrity import verify_cassette_integrity
from rerunner.models import CassetteEntry, RecordedRequest, RecordedResponse
from rerunner.matcher import compute_request_key
from rerunner.transport import CassetteTransport
from rerunner.sanitizer import Pseudonymizer, sanitize_string

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


@pytest.mark.parametrize("extension", [".jsonl", ".zst", ".gz"])
def test_cli_doctor_audits_clean_cassette_formats(tmp_path: Path, extension: str) -> None:
    path = tmp_path / f"clean{extension}"
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200, body='{"ok":true}'),
        )
    )
    cassette.save()

    result = runner.invoke(app, ["doctor", str(path)])
    assert result.exit_code == 0, result.output
    assert "Cryptographic integrity verified successfully" in result.output
    assert "Security scan passed" in result.output
    assert "Cassette audit passed for 1 file(s)" in result.output


def test_cli_doctor_rejects_secret_leaks_in_url_chunks_and_tools(tmp_path: Path) -> None:
    path = tmp_path / "leaky.jsonl"
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="GET", url="https://example.org/?contact=alice@example.org"
            ),
            response=RecordedResponse(status_code=200, chunks=["bob@example.org"]),
        )
    )
    cassette.append(
        CassetteEntry(
            step=2,
            entry_type="tool",
            side_effect_name="lookup",
            side_effect_kwargs={"recipient": "charlie@example.org"},
        )
    )
    cassette.save()

    result = runner.invoke(app, ["doctor", str(path)])
    assert result.exit_code == 1
    assert "SECURITY WARNING" in result.output
    assert "REDACTED_EMAIL" in result.output


def test_cli_doctor_rejects_tampered_and_missing_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid.jsonl"
    tampered = tmp_path / "tampered.jsonl"
    cassette = Cassette(valid)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200, body="before"),
        )
    )
    cassette.save()
    lines = valid.read_text().splitlines()
    entry = json.loads(lines[1])
    entry["response"]["body"] = "after"
    tampered.write_text(lines[0] + "\n" + json.dumps(entry) + "\n")

    result = runner.invoke(app, ["doctor", str(valid), str(tampered), str(tmp_path / "absent.zst")])
    assert result.exit_code == 1
    assert "Cryptographic integrity verified successfully" in result.output
    assert "INTEGRITY FAILURE" in result.output
    assert "Error loading cassette" in result.output
    assert "Cassette audit failed for 2 file(s)" in result.output


def test_cli_doctor_verifies_hmac_when_key_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "signed.jsonl"
    monkeypatch.setenv("RERUNNER_HMAC_KEY", "signing-key-for-test")
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200),
        )
    )
    cassette.save()

    assert runner.invoke(app, ["doctor", str(path)]).exit_code == 0
    monkeypatch.setenv("RERUNNER_HMAC_KEY", "wrong-signing-key")
    result = runner.invoke(app, ["doctor", str(path)])
    assert result.exit_code == 1
    assert "INTEGRITY FAILURE" in result.output


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


def test_cli_scrub_redacts_values_split_across_stream_chunks(tmp_path: Path) -> None:
    leaky_file = tmp_path / "leaky_stream.jsonl"
    scrubbed_file = tmp_path / "scrubbed_stream.jsonl"

    c = Cassette(leaky_file)
    c.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="POST",
                url="https://api.openai.com/v1/chat/completions",
                body='{"stream": true}',
            ),
            response=RecordedResponse(
                status_code=200,
                headers={"content-type": "text/event-stream"},
                body='data: {"token":"mail alice.smith@example.org done"}\n\ndata: [DONE]\n\n',
                chunks=[
                    'data: {"token":"mail alice.smith@exam',
                    'ple.org done"}\n\n',
                    "data: [DONE]\n\n",
                ],
                chunk_delays_ms=[0.0, 1.0, 1.0],
                is_streaming=True,
            ),
        )
    )
    c.save()

    res_scrub = runner.invoke(app, ["scrub", str(leaky_file), "--output", str(scrubbed_file)])
    assert res_scrub.exit_code == 0

    assert "alice.smith" not in scrubbed_file.read_text()
    response = Cassette.load(scrubbed_file).entries[0].response
    assert response is not None
    assert response.chunks == [
        'data: {"token":"mail ',
        '[REDACTED_EMAIL] done"}\n\n',
        "data: [DONE]\n\n",
    ]
    assert response.chunk_delays_ms == [0.0, 1.0, 1.0]


def _assert_summary_counts(
    output: str, total: int, passed: int, failed: int, compromised: int
) -> None:
    for label, expected in (
        ("Total Cassettes", total),
        ("Passed", passed),
        ("Failed", failed),
        ("Compromised", compromised),
    ):
        rows = [line for line in output.splitlines() if label in line]
        assert len(rows) == 1, output
        assert rows[0].split("│")[-2].strip() == str(expected), output


@pytest.mark.parametrize("suffix", [".jsonl", ".gz", ".zst"])
def test_doctor_summary_clean_formats(tmp_path: Path, suffix: str) -> None:
    path = tmp_path / ("good" + suffix)
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200, body="ok"),
        )
    )
    cassette.save()
    result = runner.invoke(app, ["doctor", str(path), "--summary-only"])
    assert result.exit_code == 0, result.output
    _assert_summary_counts(result.output, 1, 1, 0, 0)
    assert "Cassette Audit Summary" in result.output
    assert "Auditing cassette:" not in result.output
    assert "Cryptographic integrity" not in result.output


def test_doctor_summary_mixed_tampered_missing(tmp_path: Path) -> None:
    good = tmp_path / "good.jsonl"
    bad = tmp_path / "bad.jsonl"
    missing = tmp_path / "missing.jsonl"
    cassette = Cassette(good)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200, body="before"),
        )
    )
    cassette.save()
    records = good.read_text().splitlines()
    entry = json.loads(records[1])
    entry["response"]["body"] = "after"
    bad.write_text("\n".join([records[0], json.dumps(entry), ""]))
    result = runner.invoke(app, ["doctor", "-s", str(good), str(bad), str(missing)])
    assert result.exit_code == 1, result.output
    _assert_summary_counts(result.output, 3, 1, 2, 1)
    assert str(good) not in result.output
    assert str(bad) not in result.output
    assert str(missing) not in result.output
    assert "INTEGRITY FAILURE" not in result.output


def test_doctor_summary_sensitive_content(tmp_path: Path) -> None:
    path = tmp_path / "leaky.jsonl"
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(
                method="GET", url="https://example.org/?email=alice@example.org"
            ),
            response=RecordedResponse(status_code=200),
        )
    )
    cassette.save()
    result = runner.invoke(app, ["doctor", "--summary-only", str(path)])
    assert result.exit_code == 1, result.output
    _assert_summary_counts(result.output, 1, 0, 1, 1)
    assert "alice@example.org" not in result.output
    assert "SECURITY WARNING" not in result.output


def test_doctor_summary_hmac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "signed.jsonl"
    monkeypatch.setenv("RERUNNER_HMAC_KEY", "correct-test-key")
    cassette = Cassette(path)
    cassette.append(
        CassetteEntry(
            step=1,
            entry_type="http",
            request=RecordedRequest(method="GET", url="https://example.org/health"),
            response=RecordedResponse(status_code=200),
        )
    )
    cassette.save()
    good = runner.invoke(app, ["doctor", str(path), "-s"])
    assert good.exit_code == 0, good.output
    _assert_summary_counts(good.output, 1, 1, 0, 0)
    monkeypatch.setenv("RERUNNER_HMAC_KEY", "incorrect-test-key")
    bad = runner.invoke(app, ["doctor", str(path), "-s"])
    assert bad.exit_code == 1, bad.output
    _assert_summary_counts(bad.output, 1, 0, 1, 1)


def test_doctor_summary_preserves_existing_modes(tmp_path: Path) -> None:
    help_result = runner.invoke(app, ["doctor", "--help"], color=False)
    assert help_result.exit_code == 0, help_result.output
    clean_output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", help_result.output)
    doctor_cmd = get_command(app).commands.get("doctor")
    has_summary_param = doctor_cmd is not None and any(
        getattr(p, "name", "") == "summary_only" for p in getattr(doctor_cmd, "params", [])
    )
    assert "--summary-only" in clean_output or "-s" in clean_output or has_summary_param
    default = runner.invoke(app, ["doctor"])
    flagged = runner.invoke(app, ["doctor", "-s"])
    assert default.exit_code == flagged.exit_code == 0
    assert flagged.output == default.output
    absent = tmp_path / "absent.jsonl"
    original = runner.invoke(app, ["doctor", str(absent)])
    assert original.exit_code == 1
    assert "Auditing cassette:" in original.output
    assert "Cassette Audit Summary" not in original.output


class _SyntheticIdentity(BaseModel):
    email: EmailStr
    identifier: UUID4
    ssn: str = Field(pattern=r"^900-\d{2}-\d{4}$")
    card: PaymentCardNumber


@pytest.mark.parametrize("suffix", [".jsonl", ".gz", ".zst"])
def test_scrub_pseudonymize_formats_replay_and_integrity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    source = tmp_path / ("source" + suffix)
    first = tmp_path / ("first" + suffix)
    second = tmp_path / ("second" + suffix)
    other = tmp_path / ("other" + suffix)
    identity = {
        "email": "fixture.person@example.net",
        "identifier": "550e8400-e29b-41d4-a716-446655440000",
        "ssn": "000-12-3456",
        "card": "4111-1111-1111-1111",
    }
    fake_key = "sk-" + "A" * 40
    custom = "fixture_private_marker"
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", json.dumps([custom]))
    body = json.dumps(
        {
            **identity,
            "secret": fake_key,
            "marker": custom,
            "message": "test " + fake_key,
            "count": 42,
        }
    )
    url = "https://example.net/api?token=fixture-token"
    request_key = compute_request_key("POST", url, body)
    cassette = Cassette(source)
    cassette.append(
        CassetteEntry(
            step=1,
            request=RecordedRequest(
                method="POST",
                url=url,
                request_key=request_key,
                body=body,
                headers={
                    "authorization": "Bearer " + identity["identifier"],
                    "x-api-key": "opaque",
                },
            ),
            response=RecordedResponse(status_code=200, body=body),
        )
    )
    cassette.append(
        CassetteEntry(
            step=2,
            entry_type="tool",
            side_effect_name="lookup",
            side_effect_args=[identity["email"]],
            side_effect_kwargs={"nested": [identity, True, 42]},
            side_effect_result=identity,
            side_effect_exception=identity["email"] + " " + fake_key,
        )
    )
    cassette.save()
    original = source.read_bytes()

    def scrub_to(path: Path, seed: str) -> None:
        result = runner.invoke(
            app, ["scrub", str(source), "--output", str(path), "--pseudonymize", "--seed", seed]
        )
        assert result.exit_code == 0, result.output
        assert "review before sharing" in result.output
        assert seed not in result.output

    scrub_to(first, "fixture-seed-a")
    scrub_to(second, "fixture-seed-a")
    scrub_to(other, "fixture-seed-b")
    assert source.read_bytes() == original
    a, b, c = (Cassette.load(path) for path in (first, second, other))
    assert [e.model_dump() for e in a.entries] == [e.model_dump() for e in b.entries]
    assert a.entries[0].entry_hash != c.entries[0].entry_hash
    assert a.entries[0].request is not None
    assert a.entries[0].response is not None
    request, response = a.entries[0].request, a.entries[0].response
    clean = json.loads(response.body)
    _SyntheticIdentity.model_validate(clean)
    for field, original_value in identity.items():
        assert clean[field] != original_value
    assert clean["count"] == 42
    assert clean["secret"] == "[REDACTED]"
    assert clean["message"] == "test [REDACTED_OPENAI_KEY]"
    assert clean["marker"] == "[REDACTED]"
    assert request.headers["authorization"] == request.headers["x-api-key"] == "[REDACTED]"
    assert "fixture-token" not in request.url
    assert request.request_key == request_key
    assert json.loads(request.body) == clean
    assert a.entries[1].side_effect_args == [clean["email"]]
    assert a.entries[1].side_effect_result == {k: clean[k] for k in identity}
    assert a.entries[1].side_effect_kwargs == {
        "nested": [{k: clean[k] for k in identity}, True, 42]
    }
    assert a.entries[1].side_effect_exception == clean["email"] + " [REDACTED_OPENAI_KEY]"
    assert verify_cassette_integrity(a.entries)[0]
    # The existing leak scanner stays conservative about PII-shaped synthetic data.
    assert runner.invoke(app, ["verify", str(first), "--strict"]).exit_code == 1
    a.entries[0].response.body = "tampered"
    assert not verify_cassette_integrity(a.entries)[0]

    def forbidden_network(request: httpx.Request) -> httpx.Response:
        pytest.fail("replay must not use the live transport")

    transport = CassetteTransport(
        first, mode="replay", real_transport=httpx.MockTransport(forbidden_network)
    )
    with httpx.Client(transport=transport) as client:
        replayed = client.post(url, content=body)
        assert replayed.json() == clean


def test_scrub_pseudonymize_dry_run_and_seed_validation(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    target = tmp_path / "target.jsonl"
    cassette = Cassette(source)
    cassette.append(
        CassetteEntry(
            step=1,
            request=RecordedRequest(method="GET", url="https://example.net"),
            response=RecordedResponse(status_code=200, body="fixture@example.net"),
        )
    )
    cassette.save()
    before = source.read_bytes()
    target.write_bytes(b"unchanged")
    result = runner.invoke(
        app,
        [
            "scrub",
            str(source),
            "--pseudonymize",
            "--seed",
            "fixture",
            "--dry-run",
            "--output",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    assert source.read_bytes() == before and target.read_bytes() == b"unchanged"
    result = runner.invoke(app, ["scrub", str(source), "--seed", "fixture"])
    assert result.exit_code != 0 and source.read_bytes() == before


def test_scrub_pseudonymize_stream_boundaries_and_seed_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "stream.jsonl"
    target = tmp_path / "synthetic.jsonl"
    monkeypatch.setenv("RERUNNER_PSEUDONYM_SEED", "fixture-env")
    parts = ["data: fixture.person@exam", "ple.net sk-" + "A" * 20, "A" * 20 + " done\n\n"]
    cassette = Cassette(source)
    cassette.append(
        CassetteEntry(
            step=1,
            request=RecordedRequest(method="GET", url="https://example.net"),
            response=RecordedResponse(
                status_code=200,
                body="".join(parts),
                chunks=parts,
                chunk_delays_ms=[0.0, 1.0, 2.0],
                is_streaming=True,
            ),
        )
    )
    cassette.save()
    result = runner.invoke(app, ["scrub", str(source), "--pseudonymize", "--output", str(target)])
    assert result.exit_code == 0, result.output
    response = Cassette.load(target).entries[0].response
    assert response is not None
    expected = Pseudonymizer("fixture-env", email_domain="example.org").pseudonymize_email(
        "fixture.person@example.net"
    )
    assert response.body == "".join(response.chunks)
    assert response.body == f"data: {expected} [REDACTED_OPENAI_KEY] done\n\n"
    assert len(response.chunks) == 3
    assert response.chunk_delays_ms == [0.0, 1.0, 2.0]


def test_pseudonymization_retains_other_redaction_and_legacy_domain() -> None:
    p = Pseudonymizer("fixture", email_domain="example.org")
    text = "123-456-7890 192.168.0.1 4111-1111-1111-1112"
    assert (
        sanitize_string(text, pseudonymizer=p)
        == "[REDACTED_PHONE] [REDACTED_IP_ADDRESS] [REDACTED_CREDIT_CARD]"
    )
    assert (
        Pseudonymizer("fixture").pseudonymize_email("fixture@example.net").endswith("@example.test")
    )


def test_pseudonymized_payload_keeps_credential_redaction_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rerunner.sanitizer import sanitize_payload

    p = Pseudonymizer("fixture", email_domain="example.org")
    identifier = "550e8400-e29b-41d4-a716-446655440000"
    secret_email = "private.fixture@example.net"
    monkeypatch.setenv("RERUNNER_REDACT_PATTERNS", json.dumps([re.escape(secret_email)]))
    result = sanitize_payload(
        {
            "authorization": identifier,
            "api_key": identifier,
            "password": "opaque-fixture",
            "contact": secret_email,
            "identifier": identifier,
        },
        pseudonymizer=p,
    )
    assert result == {
        "authorization": "[REDACTED]",
        "api_key": "[REDACTED]",
        "password": "[REDACTED]",
        "contact": "[REDACTED]",
        "identifier": p.pseudonymize_uuid(identifier),
    }
