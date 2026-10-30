"""Append-only usage records in the Graph Home ``usage/`` folder (spec 4.2.3, S11).

One JSON object per line, one file per month (``usage/YYYY-MM.jsonl``). Appending creates
only the ``usage/`` folder and never the Graph Home itself. Reading skips broken lines and
reads only the newest month files so session start stays fast. The record shape belongs to
the caller; this module stores plain JSON objects.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path

USAGE_DIRECTORY = "usage"
DEFAULT_USAGE_READ_FILES = 3


class JsonlUsageLog:
    def __init__(
        self,
        graph_home: Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_files: int = DEFAULT_USAGE_READ_FILES,
    ) -> None:
        self._graph_home = graph_home
        self.directory = graph_home / USAGE_DIRECTORY
        self._clock = clock or (lambda: datetime.now(UTC))
        self._max_files = max_files

    def append_events(self, events: Sequence[Mapping[str, object]]) -> None:
        """Append events as one write. Raises ``OSError`` when the Graph Home or folder is unusable."""
        if not events:
            return
        if not self._graph_home.is_dir():
            raise FileNotFoundError(f"Graph Home does not exist: {self._graph_home}")
        self.directory.mkdir(exist_ok=True)
        payload = "".join(json.dumps(dict(event), ensure_ascii=False, sort_keys=True) + "\n" for event in events)
        target = self.directory / f"{self._clock().strftime('%Y-%m')}.jsonl"
        with target.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def read_events(self) -> tuple[dict[str, object], ...]:
        """Return events from the newest month files, oldest first. Raises ``OSError`` when unreadable."""
        if not self.directory.is_dir():
            return ()
        files = sorted(path for path in self.directory.glob("*.jsonl") if path.is_file())
        events: list[dict[str, object]] = []
        for path in files[-self._max_files :] if self._max_files > 0 else ():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    events.append(value)
        return tuple(events)


__all__ = ["DEFAULT_USAGE_READ_FILES", "USAGE_DIRECTORY", "JsonlUsageLog"]
