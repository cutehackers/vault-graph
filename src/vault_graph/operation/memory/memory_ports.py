"""Ports that composition implements for Vault memory writes (spec 2026-11-02 V1).

``VaultWriter`` hands a draft to the Vault tool: ``publish`` for ``stated`` memories (계약1) and
``propose`` for ``inferred`` memories, which wait in the Vault review queue (계약4). ``VaultPageReader``
reads a current page and never writes. ``DraftFiles`` turns a draft into the file the Vault tool reads,
outside every Vault, and removes it afterwards, so the M18 service writes no file itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

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


__all__ = ["DraftFiles", "PageText", "VaultPageReader", "VaultWriter", "WriteOutcome", "WriteStatus"]
