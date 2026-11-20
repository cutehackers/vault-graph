"""``ProposalCounter`` that counts pending ``memory-proposal`` items in a Vault review queue (F11).

The queue is ``scratch/review/<review_id>.md`` (Vault ``tools/wiki/lib/review.py``). It is never
indexed, so session start recall reads the item frontmatter from disk. Nothing is written.

``review_item_state`` tells a published accept from a ``status`` a person set to ``accepted`` by hand
(spec 2026-11-20 D7): the Vault's accept publishes the draft and then writes
``resolution: "<reason> Published: <paths>."`` (Vault ``tools/wiki/lib/memory_proposal.py`` ``accept``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

REVIEW_QUEUE = Path("scratch") / "review"
MEMORY_PROPOSAL_TYPE = "memory-proposal"
PUBLISHED_MARK = "Published:"
# What a person does with an unpublished accept. vault-graph never edits the item itself (I1).
UNPUBLISHED_FIX = (
    "set `status` to `pending` and `resolution` to an empty value in the item file, then accept it with `vg review`"
)

ReviewItemState = Literal["pending", "accepted", "unpublished", "rejected", "resolved", "missing"]


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


def review_item_state(vault_root: Path, review_path: str) -> ReviewItemState:
    """Review state of one review item, read from its frontmatter.

    ``accepted`` means the Vault published the draft: ``status`` is ``accepted`` and ``resolution`` holds
    "Published:". ``unpublished`` is ``status: accepted`` without that mark, which is what a hand edit of the
    file leaves. ``pending``, ``rejected`` and ``resolved`` are the item's own status. ``missing`` is an item
    that is gone, unreadable, outside the review queue or without one of the four Vault statuses.
    """
    queue = (vault_root / REVIEW_QUEUE).resolve()
    item = (vault_root / review_path).resolve()
    if not item.is_relative_to(queue) or not item.is_file():
        return "missing"
    try:
        block = split_frontmatter(item.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return "missing"
    if block is None:
        return "missing"
    fields = parse_vault_frontmatter(block[0])
    status = fields.get("status")
    if status == "accepted":
        resolution = fields.get("resolution")
        return "accepted" if isinstance(resolution, str) and PUBLISHED_MARK in resolution else "unpublished"
    if status == "pending":
        return "pending"
    if status == "rejected":
        return "rejected"
    if status == "resolved":
        return "resolved"
    return "missing"


def _is_pending_proposal(text: str) -> bool:
    block = split_frontmatter(text)
    if block is None:
        return False
    fields = parse_vault_frontmatter(block[0])
    return fields.get("type") == MEMORY_PROPOSAL_TYPE and fields.get("status") == "pending"


__all__ = [
    "PUBLISHED_MARK",
    "UNPUBLISHED_FIX",
    "ReviewItemState",
    "VaultReviewQueue",
    "pending_proposals",
    "review_item_state",
]
