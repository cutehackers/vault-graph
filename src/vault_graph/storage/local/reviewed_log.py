"""Cleanup review records in the Graph Home ``memory/reviewed.jsonl`` (spec 2026-11-05 §4.4.4, 결정44).

One JSON object per line: ``{"candidate_key", "at", "outcome"}``. A candidate key in this file
is not offered again by the cleanup bundle. The file lives only in the Graph Home and never in a
Vault. Deleting it makes every recorded candidate come back once. Appending creates only the
``memory/`` folder and never the Graph Home itself. Reading skips broken lines.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

REVIEWED_LOG_PATH = "memory/reviewed.jsonl"


class JsonlReviewedLog:
    def __init__(self, graph_home: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self._graph_home = graph_home
        self.path = graph_home / REVIEWED_LOG_PATH
        self._clock = clock or (lambda: datetime.now(UTC))

    def append(self, candidate_keys: Sequence[str], *, outcome: str) -> None:
        """Append one record per key as one write. Raises ``ValueError`` for blank values, ``OSError`` on I/O."""
        if not outcome.strip():
            raise ValueError("review outcome must not be blank")
        if any(not key.strip() for key in candidate_keys):
            raise ValueError("candidate key must not be blank")
        if not candidate_keys:
            return
        if not self._graph_home.is_dir():
            raise FileNotFoundError(f"Graph Home does not exist: {self._graph_home}")
        self.path.parent.mkdir(exist_ok=True)
        at = self._clock().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        payload = "".join(
            json.dumps({"candidate_key": key, "at": at, "outcome": outcome}, ensure_ascii=False, sort_keys=True) + "\n"
            for key in candidate_keys
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def reviewed_keys(self) -> frozenset[str]:
        """Every recorded candidate key. A missing file means none. Raises ``OSError`` when unreadable."""
        if not self.path.is_file():
            return frozenset()
        keys: set[str] = set()
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                continue
            if isinstance(value, dict):
                key = value.get("candidate_key")
                if isinstance(key, str) and key.strip():
                    keys.add(key)
        return frozenset(keys)


__all__ = ["REVIEWED_LOG_PATH", "JsonlReviewedLog"]
