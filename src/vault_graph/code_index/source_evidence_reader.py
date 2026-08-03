"""Bounded, live source evidence reads for already-selected code symbols."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from vault_graph.code_index.code_models import CodeRepositoryEntry, CodeSymbolRecord

MAX_SOURCE_LINES = 200


@dataclass(frozen=True)
class SourceEvidence:
    """Live source lines and a stable non-executable evidence reference."""

    source_uri: str | None
    relative_path: str | None = None
    lines: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class SourceEvidenceReader:
    """Read current, bounded repository lines without retaining source bodies."""

    def __init__(self, entries: tuple[CodeRepositoryEntry, ...]) -> None:
        self._entries = {entry.repository_id: entry for entry in entries}

    def read(self, symbol: CodeSymbolRecord, *, relative_path: str, max_lines: int) -> SourceEvidence:
        entry = self._entries.get(symbol.repository_id)
        if entry is None:
            return SourceEvidence(None, warnings=("source_unavailable",))
        relative = _validated_relative_path(relative_path)
        if relative is None:
            return SourceEvidence(None, warnings=("source_unavailable",))
        path = _repository_path(entry.root_path, relative)
        if path is None:
            return SourceEvidence(None, relative, warnings=("source_unavailable",))
        try:
            before = path.read_bytes()
        except OSError:
            return SourceEvidence(None, relative, warnings=("source_unavailable",))
        if hashlib.sha256(before).hexdigest() != symbol.content_hash:
            return SourceEvidence(None, relative, warnings=("source_changed_since_index",))
        try:
            lines = before.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            return SourceEvidence(None, relative, warnings=("source_unavailable",))
        count = min(max(1, max_lines), MAX_SOURCE_LINES, symbol.end_line - symbol.start_line + 1)
        selected = tuple(lines[symbol.start_line - 1 : symbol.start_line - 1 + count])
        try:
            after = path.read_bytes()
        except OSError:
            return SourceEvidence(None, relative, warnings=("source_unavailable",))
        if hashlib.sha256(after).hexdigest() != symbol.content_hash or after != before:
            return SourceEvidence(None, relative, warnings=("source_changed_since_index",))
        end_line = symbol.start_line + len(selected) - 1
        return SourceEvidence(
            _source_uri(symbol.repository_id, relative, symbol.start_line, end_line),
            relative,
            selected,
        )


def _validated_relative_path(relative_path: str) -> str | None:
    if not isinstance(relative_path, str) or "\x00" in relative_path:
        return None
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        return None
    return path.as_posix()


def _repository_path(root: Path, relative_path: str) -> Path | None:
    try:
        resolved_root = root.expanduser().resolve(strict=True)
        candidate = (resolved_root / relative_path).resolve(strict=True)
    except OSError:
        return None
    if candidate != resolved_root and resolved_root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _source_uri(repository_id: str, relative_path: str, start_line: int, end_line: int) -> str:
    return f"vg-source://{quote(repository_id, safe='')}/{quote(relative_path, safe='/')}#L{start_line}-L{end_line}"


__all__ = ["MAX_SOURCE_LINES", "SourceEvidence", "SourceEvidenceReader"]
