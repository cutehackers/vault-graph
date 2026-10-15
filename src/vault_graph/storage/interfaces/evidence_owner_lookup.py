from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.graph.graph_contracts import GraphEvidenceRef
from vault_graph.ingestion.vault_catalog import QueryScope


@dataclass(frozen=True)
class EvidenceOwnerRecord:
    """One matching reference with the verified owner's minimal identity."""

    owner_kind: str
    owner_vault_id: str
    owner_id: str
    evidence_ref: GraphEvidenceRef
    graph_revision: str
    source_vault_id: str | None = None
    target_vault_id: str | None = None
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    scope_key: str = ""
    scope_revision: str = ""


class EvidenceOwnerLookup(Protocol):
    def lookup_evidence_owners(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
        scopes: tuple[QueryScope, ...],
        include_cross_vault: bool,
        limit: int,
    ) -> tuple[EvidenceOwnerRecord, ...]:
        """Return at most limit minimal rows, ordered by owner and reference identity."""
        raise NotImplementedError
