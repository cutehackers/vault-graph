"""Secret redaction rules ``vg-redact/1`` for normalized session text (spec 2026-11-05 §4.2.2, 위험A8).

The rules copy the Vault capture rules in vault-builder ``tools/wiki/lib/session_capture.py`` redact().
The Vault tool applies its own copy again when it renders, so both copies must stay identical.
tests/test_session_redact.py runs one table against both. Change both or neither.
Order matters: earlier patterns replace whole values so later patterns do not count the same secret
twice, and no value pattern matches an existing placeholder.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

REDACTION_RULES_VERSION = "vg-redact/1"

_PLACEHOLDER = "[REDACTED:"
_NOT_PLACEHOLDER = r"(?!\[REDACTED:)"

_PEM_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----.*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
_URL_PASSWORD_RE = re.compile(
    r"(?P<pre>\b[A-Za-z][A-Za-z0-9+.\-]*://[^\s:/@]+:)" + _NOT_PLACEHOLDER + r"(?P<value>[^\s/@]+)(?=@)"
)
_AUTHORIZATION_RE = re.compile(
    r"(?P<pre>(?<![A-Za-z0-9_-])authorization[\"']?\s*:\s*[\"']?)"
    + _NOT_PLACEHOLDER
    + r"(?P<value>[^\"'\s](?:[^\"'\r\n]*[^\"'\s])?)",
    re.IGNORECASE,
)
# A bearer token must contain a digit so prose such as "Bearer authentication" stays.
_BEARER_RE = re.compile(r"(?P<pre>\bBearer\s+)(?P<value>(?=[A-Za-z0-9\-._~+/]*[0-9])[A-Za-z0-9\-._~+/]{8,}=*)")
_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}")),
    ("openai-key", re.compile(r"\bsk-(?!ant-)[A-Za-z0-9_\-]{20,}")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}(?![0-9A-Za-z])")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
)
_SECRET_KEYS = ("password", "passwd", "secret", "token", "apikey", "accesskey", "privatekey", "clientsecret")


def _key_pattern(name: str) -> str:
    # Case and "-"/"_" do not matter, so api_key, API-KEY and apikey all match.
    return "[-_]?".join(re.escape(char) for char in name)


# The key may carry a prefix such as GITHUB_ or db- (GITHUB_TOKEN, db-password).
_KEY_VALUE_RE = re.compile(
    r"(?P<pre>(?<![A-Za-z0-9])[\"']?(?:[A-Za-z0-9]+[-_])*(?:"
    + "|".join(_key_pattern(name) for name in _SECRET_KEYS)
    + r")[\"']?\s*[:=](?!=)\s*)"
    + _NOT_PLACEHOLDER
    + r"(?P<value>\""
    + _NOT_PLACEHOLDER
    + r"(?:[^\"\\\n]|\\.)+\"|'"
    + _NOT_PLACEHOLDER
    + r"[^'\n]+'|[^\s\"',;(){}\[\]<>]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RedactedText:
    """Text with known secret shapes replaced by ``[REDACTED:<kind>]``, and how many were replaced."""

    text: str
    count: int


def redact(text: str) -> RedactedText:
    """Replace known secret shapes with ``[REDACTED:<kind>]``. Redacting the result again changes nothing."""
    count = 0

    def whole(kind: str) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            nonlocal count
            count += 1
            return f"{_PLACEHOLDER}{kind}]"

        return replace

    def value_only(kind: str) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            nonlocal count
            value = match.group("value")
            quote = value[0] if value[:1] in ("'", '"') and len(value) >= 2 and value[-1] == value[0] else ""
            count += 1
            return f"{match.group('pre')}{quote}{_PLACEHOLDER}{kind}]{quote}"

        return replace

    text = _PEM_RE.sub(whole("private-key"), text)
    text = _URL_PASSWORD_RE.sub(value_only("url-password"), text)
    text = _AUTHORIZATION_RE.sub(value_only("authorization"), text)
    text = _BEARER_RE.sub(value_only("bearer"), text)
    for kind, pattern in _TOKEN_PATTERNS:
        text = pattern.sub(whole(kind), text)
    text = _KEY_VALUE_RE.sub(value_only("secret"), text)
    return RedactedText(text=text, count=count)
