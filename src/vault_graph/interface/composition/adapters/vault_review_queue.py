"""``ProposalCounter`` that counts pending ``memory-proposal`` items in a Vault review queue (F11).

The queue is ``scratch/review/<review_id>.md`` (Vault ``tools/wiki/lib/review.py``). It is never
indexed, so session start recall reads the item frontmatter from disk. Nothing is written.
"""

from __future__ import annotations

from pathlib import Path

from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

REVIEW_QUEUE = Path("scratch") / "review"
MEMORY_PROPOSAL_TYPE = "memory-proposal"


class VaultReviewQueue:
    def __init__(self, *, catalog: VaultCatalog) -> None:
        self._catalog = catalog

    def pending_count(self, vault_id: str) -> int:
        queue = self._catalog.resolve(vault_id).root_path / REVIEW_QUEUE
        if not queue.is_dir():
            return 0
        return sum(
            1
            for item in sorted(queue.glob("*.md"))
            if _is_pending_proposal(item.read_text(encoding="utf-8", errors="replace"))
        )


def _is_pending_proposal(text: str) -> bool:
    block = split_frontmatter(text)
    if block is None:
        return False
    fields = parse_vault_frontmatter(block[0])
    return fields.get("type") == MEMORY_PROPOSAL_TYPE and fields.get("status") == "pending"


__all__ = ["VaultReviewQueue"]
