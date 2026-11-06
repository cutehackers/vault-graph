"""Vector failures per Vault, kept so the session-start catch-up stops repeating one error.

Spec 2026-11-05 §4.3.1 단기 수정 (결정21). ``<graph home>/logs/vector-index-failures.json`` holds
one entry per Vault: ``{vault_id, error_digest, error_head, first_failed_at, last_failed_at, count}``.
``vg index`` records a vector failure and clears the entry when vectors succeed. The background
catch-up of ``vg hook session-start`` skips vectors of a Vault (metadata and graph still run) until
``min(2^(count-1), 24)`` hours after its last failure. A person running ``vg index`` is never held
back. The file is rebuildable: a missing or broken file means no recorded failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

VECTOR_FAILURE_LOG = Path("logs") / "vector-index-failures.json"
MAX_RETRY_INTERVAL_HOURS = 24
_ERROR_HEAD_CHARS = 200
_DIGITS = re.compile(r"\d+")


@dataclass(frozen=True)
class VectorFailure:
    vault_id: str
    error_digest: str
    error_head: str
    first_failed_at: datetime
    last_failed_at: datetime
    count: int

    @property
    def retry_interval(self) -> timedelta:
        return timedelta(hours=min(2 ** (self.count - 1), MAX_RETRY_INTERVAL_HOURS))

    @property
    def retry_at(self) -> datetime:
        return self.last_failed_at + self.retry_interval


def read_vector_failures(graph_home: Path) -> dict[str, VectorFailure]:
    try:
        payload = json.loads((graph_home / VECTOR_FAILURE_LOG).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = payload.get("failures") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return {}
    failures: dict[str, VectorFailure] = {}
    for entry in entries:
        failure = _failure_from_entry(entry)
        if failure is not None:
            failures[failure.vault_id] = failure
    return failures


def record_vector_failure(graph_home: Path, vault_id: str, error: str, *, now: datetime) -> VectorFailure:
    """Add one failure. The same error (digits ignored) counts up; another error starts at 1."""

    failures = read_vector_failures(graph_home)
    head = _error_head(error)
    digest = hashlib.sha256(_DIGITS.sub("#", head).encode("utf-8")).hexdigest()[:16]
    previous = failures.get(vault_id)
    if previous is not None and previous.error_digest == digest:
        failure = VectorFailure(vault_id, digest, head, previous.first_failed_at, now, previous.count + 1)
    else:
        failure = VectorFailure(vault_id, digest, head, now, now, 1)
    failures[vault_id] = failure
    _write(graph_home, failures)
    return failure


def clear_vector_failure(graph_home: Path, vault_id: str) -> None:
    failures = read_vector_failures(graph_home)
    if failures.pop(vault_id, None) is not None:
        _write(graph_home, failures)


def vector_retry_pending(graph_home: Path, vault_id: str, *, now: datetime) -> bool:
    failure = read_vector_failures(graph_home).get(vault_id)
    return failure is not None and now < failure.retry_at


def failure_warning(failure: VectorFailure, *, now: datetime) -> str:
    hours = max(0, int((now - failure.first_failed_at).total_seconds() // 3600))
    return f"벡터 색인이 {failure.vault_id}에서 {hours}시간째 실패 중: {failure.error_head}"


def _error_head(error: str) -> str:
    first_line = next((line.strip() for line in error.splitlines() if line.strip()), "unknown error")
    return first_line[:_ERROR_HEAD_CHARS]


def _failure_from_entry(entry: object) -> VectorFailure | None:
    if not isinstance(entry, dict):
        return None
    try:
        count = int(entry["count"])
        failure = VectorFailure(
            vault_id=str(entry["vault_id"]),
            error_digest=str(entry["error_digest"]),
            error_head=str(entry["error_head"]),
            first_failed_at=datetime.fromisoformat(str(entry["first_failed_at"])),
            last_failed_at=datetime.fromisoformat(str(entry["last_failed_at"])),
            count=count,
        )
    except (KeyError, TypeError, ValueError):
        return None
    return failure if count >= 1 and failure.last_failed_at.tzinfo is not None else None


def _write(graph_home: Path, failures: dict[str, VectorFailure]) -> None:
    path = graph_home / VECTOR_FAILURE_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "failures": [
            {
                "vault_id": failure.vault_id,
                "error_digest": failure.error_digest,
                "error_head": failure.error_head,
                "first_failed_at": failure.first_failed_at.isoformat(),
                "last_failed_at": failure.last_failed_at.isoformat(),
                "count": failure.count,
            }
            for failure in sorted(failures.values(), key=lambda item: item.vault_id)
        ]
    }
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".vector-index-failures-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


__all__ = [
    "MAX_RETRY_INTERVAL_HOURS",
    "VECTOR_FAILURE_LOG",
    "VectorFailure",
    "clear_vector_failure",
    "failure_warning",
    "read_vector_failures",
    "record_vector_failure",
    "vector_retry_pending",
]
