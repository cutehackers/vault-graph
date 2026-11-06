"""vg-redact/1 rules mirror the Vault capture redaction (spec 2026-11-05 §4.2.2, 위험A8, A-1).

The expected values in _CASES come from vault-builder tools/wiki/lib/session_capture.py redact().
Secret-like test values are split with "+" so secret scanners do not flag the source.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from vault_graph.operation.sessions.redact import REDACTION_RULES_VERSION, RedactedText, redact

_PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
_GITHUB = "gh" + "p_" + "A1b2C3d4" * 5
_ANTHROPIC = "sk-" + "ant-" + "api03-AbCdEf0123456789xyz"

# (name, input, expected text, expected count). One table for vg and the Vault rules.
_CASES: tuple[tuple[str, str, str, int], ...] = (
    (
        "pem",
        "key:\n-----BEGIN RSA PRIVATE" + " KEY-----\n" + _PEM_BODY + "\nabc\n-----END RSA PRIVATE" + " KEY-----\nafter",
        "key:\n[REDACTED:private-key]\nafter",
        1,
    ),
    ("pem-unterminated", "-----BEGIN PRIVATE" + " KEY-----\n" + _PEM_BODY, "[REDACTED:private-key]", 1),
    (
        "authorization",
        "curl -H 'Authorization: Basic dXNlcjpwYXNzd29yZDEyMw==' https://x",
        "curl -H 'Authorization: [REDACTED:authorization]' https://x",
        1,
    ),
    ("bearer", "use Bearer abcDEF123456ghi789 for the call", "use Bearer [REDACTED:bearer] for the call", 1),
    ("bearer-prose", "Bearer authentication is used", "Bearer authentication is used", 0),
    ("anthropic", "key sk-" + "ant-api03-AbCdEf0123456789xyz here", "key [REDACTED:anthropic-key] here", 1),
    ("openai", "key sk-" + "proj-AbCdEf0123456789xyzXYZ here", "key [REDACTED:openai-key] here", 1),
    (
        "github",
        "gh" + "p_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789 and github" + "_pat_11ABCDEFG0123456789_abcdefghij",
        "[REDACTED:github-token] and [REDACTED:github-token]",
        2,
    ),
    ("slack", "xo" + "xb-1234567890-abcdefghij", "[REDACTED:slack-token]", 1),
    ("aws", "AK" + "IAABCDEFGHIJKLMNOP", "[REDACTED:aws-access-key]", 1),
    ("google", "AIza" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r", "[REDACTED:google-api-key]", 1),
    ("jwt", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl", "[REDACTED:jwt]", 1),
    (
        "key-value",
        'password=hunter2xyz, API-KEY: plainvalue99, "client_secret": "s3cr3t value"',
        'password=[REDACTED:secret], API-KEY: [REDACTED:secret], "client_secret": "[REDACTED:secret]"',
        3,
    ),
    (
        "url",
        "postgres://admin:pa55word@db.example.com:5432/app",
        "postgres://admin:[REDACTED:url-password]@db.example.com:5432/app",
        1,
    ),
    (
        "overlap",
        "api_key=" + _ANTHROPIC + " and Authorization: Bearer abc123def456ghi",
        "api_key=[REDACTED:anthropic-key] and Authorization: [REDACTED:authorization]",
        2,
    ),
    ("quoted-github", f'export GITHUB_TOKEN="{_GITHUB}"', 'export GITHUB_TOKEN="[REDACTED:github-token]"', 1),
    ("quoted-anthropic", f'"token": "{_ANTHROPIC}"', '"token": "[REDACTED:anthropic-key]"', 1),
    ("single-quoted", f"password='{_GITHUB}'", "password='[REDACTED:github-token]'", 1),
    (
        "prefixed-key",
        "db-password: s3cretvalue and GITHUB_TOKEN=abc",
        "db-password: [REDACTED:secret] and GITHUB_TOKEN=[REDACTED:secret]",
        2,
    ),
    (
        "plain",
        "The token count is high. max_tokens=4096 and ask-me later. https://example.com/a:b@c",
        "The token count is high. max_tokens=4096 and ask-me later. https://example.com/a:b@c",
        0,
    ),
    ("korean", "비밀번호는 password=한글값123 이다", "비밀번호는 password=[REDACTED:secret] 이다", 1),
    ("already-redacted", "password=[REDACTED:secret]", "password=[REDACTED:secret]", 0),
)

_VAULT_BUILDER = Path(os.environ.get("VAULT_BUILDER_ROOT", Path.home() / "workspace" / "vault-builder"))
_VAULT_REDACT = _VAULT_BUILDER / "tools" / "wiki" / "lib" / "session_capture.py"


def test_rules_version_is_vg_redact_1() -> None:
    assert REDACTION_RULES_VERSION == "vg-redact/1"


@pytest.mark.parametrize(("name", "text", "expected", "count"), _CASES, ids=[case[0] for case in _CASES])
def test_redact_matches_table(name: str, text: str, expected: str, count: int) -> None:
    assert redact(text) == RedactedText(text=expected, count=count)


@pytest.mark.parametrize(("name", "text", "expected", "count"), _CASES, ids=[case[0] for case in _CASES])
def test_redact_is_idempotent(name: str, text: str, expected: str, count: int) -> None:
    assert redact(expected) == RedactedText(text=expected, count=0)


@pytest.mark.skipif(not _VAULT_REDACT.is_file(), reason="vault-builder checkout not found; set VAULT_BUILDER_ROOT")
def test_vault_rules_give_the_same_table() -> None:
    # Runs the Vault function in a separate isolated interpreter so its package never enters this process.
    script = (
        "import json, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from tools.wiki.lib.session_capture import redact\n"
        "print(json.dumps([list(redact(text)) for text in json.load(sys.stdin)]))\n"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", script, str(_VAULT_BUILDER)],
        input=json.dumps([case[1] for case in _CASES]),
        capture_output=True,
        text=True,
        check=True,
        cwd=_VAULT_BUILDER,
    )
    vault_results = json.loads(completed.stdout)

    assert vault_results == [[expected, count] for _, _, expected, count in _CASES]
