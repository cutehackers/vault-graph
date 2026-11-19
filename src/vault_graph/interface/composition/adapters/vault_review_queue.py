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
        return pending_proposals(self._catalog.resolve(vault_id).root_path)


def pending_proposals(vault_root: Path) -> int:
    """Number of memory proposals waiting for review in the Vault at ``vault_root``."""
    queue = vault_root / REVIEW_QUEUE
    if not queue.is_dir():
        return 0
    return sum(
        1
        for item in sorted(queue.glob("*.md"))
        if _is_pending_proposal(item.read_text(encoding="utf-8", errors="replace"))
    )


def review_item_status(vault_root: Path, review_path: str) -> str | None:
    """Frontmatter ``status`` of one review item (``pending``, ``accepted``, ``rejected``, ``resolved``).

    None when the item is gone, unreadable, outside the review queue or has no status.
    """
    queue = (vault_root / REVIEW_QUEUE).resolve()
    item = (vault_root / review_path).resolve()
    if not item.is_relative_to(queue) or not item.is_file():
        return None
    try:
        block = split_frontmatter(item.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if block is None:
        return None
    status = parse_vault_frontmatter(block[0]).get("status")
    return status if isinstance(status, str) and status else None


def _is_pending_proposal(text: str) -> bool:
    block = split_frontmatter(text)
    if block is None:
        return False
    fields = parse_vault_frontmatter(block[0])
    return fields.get("type") == MEMORY_PROPOSAL_TYPE and fields.get("status") == "pending"


__all__ = ["VaultReviewQueue", "pending_proposals", "review_item_status"]
