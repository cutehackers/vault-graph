"""Ports that composition implements for Vault memory writes (spec 2026-11-02 V1).

``VaultWriter`` hands a draft to the Vault tool: ``publish`` for ``stated`` memories (계약1) and
``propose`` for ``inferred`` memories, which wait in the Vault review queue (계약4). ``VaultPageReader``
reads a current page and never writes. ``DraftFiles`` turns a draft into the file the Vault tool reads,
outside every Vault, and removes it afterwards, so the M18 service writes no file itself.
``VaultImporter`` runs Vault ``import-source`` to keep a copy of an auto-memory note (path 4, spec
2026-11-05 §4.4.5). ``ReviewedLog`` records processed cleanup candidates in the Graph Home (§4.4.4).
``SimilarPagesLookup`` searches the index for existing pages like a new memory (backlog MEMORY-01).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from vault_graph.operation.memory.memory_requests import SimilarMemoryPage

WriteStatus = Literal["published", "proposed", "rejected", "error"]


@dataclass(frozen=True)
class WriteOutcome:
    """What the Vault tool reported.

    ``reason`` is the 계약1 ``reason`` when the Vault rejected the draft. ``review_path`` is the
    Vault-relative review item when the status is ``proposed``.
    """

    status: WriteStatus
    written_paths: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    reason: str | None = None
    review_path: str | None = None
    # Set by ``VaultImporter``: the copy under ``raw/imports/`` and its source page, also when it already existed.
    raw_path: str | None = None
    source_page: str | None = None


@dataclass(frozen=True)
class PageText:
    """One Vault page as read now, and the sha256 of its bytes."""

    text: str
    sha256: str


class VaultWriter(Protocol):
    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome: ...

    def propose(self, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float) -> WriteOutcome: ...


class VaultPageReader(Protocol):
    def read(self, vault_root: Path, path: str) -> PageText | None:
        """Return the page at the Vault-relative ``path``, or None when no such file is in the Vault."""
        ...


class DraftFiles(Protocol):
    def stage(self, draft: Mapping[str, object]) -> AbstractContextManager[Path]:
        """Write ``draft`` as JSON outside every Vault and yield its path. The file is gone on exit."""
        ...


class VaultImporter(Protocol):
    def import_source(self, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
        """Have the Vault copy ``note_path`` under ``raw/imports/claude-memory/`` and make its source page.

        ``published`` means the copy exists now, made by this call or found by its sha256.
        """
        ...


class ReviewedLog(Protocol):
    def append(self, candidate_keys: Sequence[str], *, outcome: str) -> None:
        """Record the keys as processed with ``outcome``. Raises ``OSError`` when the record cannot be written."""
        ...


class SimilarPagesLookup(Protocol):
    def find(self, cwd: Path | None, query: str, *, limit: int) -> Sequence[SimilarMemoryPage]:
        """Existing pages of the ``cwd`` project like ``query``, best first, retired pages included.

        Reads the index only. Returns nothing when there is no index or no project.
        """
        ...


__all__ = [
    "DraftFiles",
    "PageText",
    "ReviewedLog",
    "SimilarPagesLookup",
    "VaultImporter",
    "VaultPageReader",
    "VaultWriter",
    "WriteOutcome",
    "WriteStatus",
]
