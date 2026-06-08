from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.errors import RetrievalContractError
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit

RetrievalSignalKind = Literal["keyword", "vector", "graph"]
RetrievalSeverity = Literal["info", "warning", "error"]
RelationshipStatus = Literal["not_applicable", "stated", "inferred", "contested", "deprecated"]


@dataclass(frozen=True)
class StoreRevision:
    kind: str
    revision: str

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.revision, "revision")


@dataclass(frozen=True)
class RetrievalSignal:
    kind: RetrievalSignalKind
    source_id: str
    rank: int
    score: float
    backend: str
    index_revision: str
    explanation: str

    def __post_init__(self) -> None:
        _require_non_empty(self.source_id, "source_id")
        _require_non_empty(self.backend, "backend")
        _require_non_empty(self.index_revision, "index_revision")
        _require_non_empty(self.explanation, "explanation")
        if self.rank <= 0:
            raise RetrievalContractError("signal rank must be positive")


@dataclass(frozen=True)
class RetrievalWarning:
    code: str
    message: str
    severity: RetrievalSeverity

    def __post_init__(self) -> None:
        _require_non_empty(self.code, "code")
        _require_non_empty(self.message, "message")


@dataclass(frozen=True)
class RetrievalResult:
    result_id: str
    vault_id: str
    kind: str
    title: str
    summary: str
    rank: int
    evidence: tuple[EvidenceReference, ...]
    signals: tuple[RetrievalSignal, ...]
    relationship_status: RelationshipStatus
    warnings: tuple[RetrievalWarning, ...]
    store_revisions: tuple[StoreRevision, ...]

    def __post_init__(self) -> None:
        _require_non_empty(self.result_id, "result_id")
        _require_non_empty(self.vault_id, "vault_id")
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.title, "title")
        if self.rank <= 0:
            raise RetrievalContractError("result rank must be positive")
        if not self.evidence:
            raise RetrievalContractError("evidence is required for retrieval results")
        if not isinstance(self.store_revisions, tuple):
            raise RetrievalContractError("store_revisions must be an immutable tuple")
        if any(not isinstance(store_revision, StoreRevision) for store_revision in self.store_revisions):
            raise RetrievalContractError("store_revisions must contain StoreRevision records")


def require_vector_hit_evidence_match(*, hit: VectorHit, evidence: EvidenceReference) -> None:
    if (
        hit.vault_id != evidence.vault_id
        or hit.document_id != evidence.document_id
        or hit.chunk_id != evidence.chunk_id
    ):
        raise RetrievalContractError("vector hit ids must match evidence before rendering")


def warning_for_missing_vector_evidence(hit: VectorHit) -> RetrievalWarning:
    return RetrievalWarning(
        code="missing_evidence",
        message=f"Metadata evidence could not be resolved for vector hit: {hit.vector_id}",
        severity="warning",
    )


def warning_for_stale_vector(*, hit: VectorHit, evidence: EvidenceReference) -> RetrievalWarning | None:
    if hit.metadata_index_revision == evidence.metadata_index_revision:
        return None
    return RetrievalWarning(
        code="stale_vector",
        message=f"Vector hit metadata revision is stale for evidence: {hit.vector_id}",
        severity="warning",
    )


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise RetrievalContractError(f"{field_name} is required")
