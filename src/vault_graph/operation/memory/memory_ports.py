"""Port that hands a Vault draft to the Vault tool, implemented in composition (spec V1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vault_graph.operation.memory.memory_requests import RememberStatus


@dataclass(frozen=True)
class PublishOutcome:
    """What the Vault publish-draft run reported."""

    status: RememberStatus
    written_paths: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


class VaultPublisher(Protocol):
    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome: ...


__all__ = ["PublishOutcome", "VaultPublisher"]
