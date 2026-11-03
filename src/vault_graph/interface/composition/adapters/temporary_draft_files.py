"""``DraftFiles`` that writes each Vault draft to the operating system's temporary folder (정리 발견3).

The Vault tool reads the draft from a path, so the draft must be a file. It lives in a new folder
under the OS temporary directory, never in a Vault, and the folder is removed when the write ends.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path


class TemporaryDraftFiles:
    def __init__(self, *, temp_root: Path | None = None) -> None:
        self._temp_root = temp_root

    @contextmanager
    def stage(self, draft: Mapping[str, object]) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix="vault-graph-memory-", dir=self._temp_root) as folder:
            draft_path = Path(folder) / "draft.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            yield draft_path


__all__ = ["TemporaryDraftFiles"]
