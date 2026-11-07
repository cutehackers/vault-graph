from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalResult, RetrievalSignal, RetrievalSignalKind
from vault_graph.retrieval.search.search_response import SearchMode
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit

RANK_CONSTANT = 60.0
SIGNAL_WEIGHTS: dict[RetrievalSignalKind, float] = {"keyword": 1.0, "vector": 1.0, "graph": 0.75}

# Spec 2026-11-05 §10.2 원인3. A document's score is its best chunk's fused score (MaxP, Dai and Callan
# SIGIR 2019) plus DOCUMENT_TAIL_WEIGHT times the sum of its next DOCUMENT_TAIL_CHUNKS chunk scores. The
# small tail share breaks near-ties toward a document that matched in several places without letting a
# long document win on chunk count alone.
DOCUMENT_TAIL_WEIGHT = 0.1
DOCUMENT_TAIL_CHUNKS = 2

# Spec 2026-11-05 §10.2 원인1. In knowledge mode, source pages are candidates next to canonical pages and
# their document score is multiplied by this weight, so a canonical page comes first at equal relevance.
# Roles that are not listed weigh 1.0. Explicit modes have no weights.
SEARCH_MODE_ROLE_WEIGHTS: dict[SearchMode, dict[DocumentRole, float]] = {
    "knowledge": {"canonical_knowledge": 1.0, "source_manifest": 0.8},
}


@dataclass(frozen=True)
class FusedCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    fused_score: float
    best_signal_rank: int
    signals: tuple[RetrievalSignal, ...]


def fuse_candidates(*, candidates: tuple[RetrievalCandidate, ...]) -> tuple[FusedCandidate, ...]:
    grouped: dict[tuple[str, str], list[RetrievalSignal]] = {}
    document_by_key: dict[tuple[str, str], str] = {}
    for candidate in candidates:
        key = (candidate.vault_id, candidate.chunk_id)
        document_by_key.setdefault(key, candidate.document_id)
        grouped.setdefault(key, []).extend(candidate.signals)

    fused_candidates: list[FusedCandidate] = []
    for (vault_id, chunk_id), signals in grouped.items():
        fused_candidates.append(
            FusedCandidate(
                vault_id=vault_id,
                document_id=document_by_key[(vault_id, chunk_id)],
                chunk_id=chunk_id,
                fused_score=sum(SIGNAL_WEIGHTS[signal.kind] / (RANK_CONSTANT + signal.rank) for signal in signals),
                best_signal_rank=min(signal.rank for signal in signals),
                signals=tuple(sorted(signals, key=lambda signal: (_signal_kind_order(signal.kind), signal.rank))),
            )
        )
    return tuple(
        sorted(
            fused_candidates,
            key=lambda candidate: (
                -candidate.fused_score,
                candidate.best_signal_rank,
                candidate.vault_id,
                candidate.chunk_id,
            ),
        )
    )


def sort_resolved_candidates(
    resolved: list[tuple[FusedCandidate, EvidenceReference, str]],
) -> list[tuple[FusedCandidate, EvidenceReference, str]]:
    return sorted(
        resolved,
        key=lambda item: (
            -item[0].fused_score,
            item[0].best_signal_rank,
            item[0].vault_id,
            item[1].path,
            item[0].chunk_id,
        ),
    )


def document_score(chunk_scores: Sequence[float]) -> float:
    """Best chunk score plus ``DOCUMENT_TAIL_WEIGHT`` times the next ``DOCUMENT_TAIL_CHUNKS`` chunk scores."""
    ordered = sorted(chunk_scores, reverse=True)
    if not ordered:
        return 0.0
    return ordered[0] + DOCUMENT_TAIL_WEIGHT * sum(ordered[1 : 1 + DOCUMENT_TAIL_CHUNKS])


def role_weight(mode: SearchMode, role: DocumentRole) -> float:
    return SEARCH_MODE_ROLE_WEIGHTS.get(mode, {}).get(role, 1.0)


def family_duplication(results: tuple[RetrievalResult, ...]) -> float:
    if not results:
        return 0.0
    distinct = {(result.vault_id, result.provenance_family_id) for result in results}
    return (len(results) - len(distinct)) / len(results)


def candidate_from_keyword_hit(hit: KeywordHit) -> RetrievalCandidate:
    return RetrievalCandidate(
        vault_id=hit.vault_id,
        document_id=hit.document_id,
        chunk_id=hit.chunk_id,
        signals=(
            RetrievalSignal(
                kind="keyword",
                rank=hit.rank,
                score=hit.score,
                backend=hit.backend,
                index_revision=hit.index_revision,
                source_id=f"keyword:{hit.vault_id}:{hit.chunk_id}",
                explanation="keyword candidate matched the query",
            ),
        ),
    )


def candidate_from_vector_hit(hit: VectorHit) -> RetrievalCandidate:
    return RetrievalCandidate(
        vault_id=hit.vault_id,
        document_id=hit.document_id,
        chunk_id=hit.chunk_id,
        signals=(
            RetrievalSignal(
                kind="vector",
                rank=hit.rank,
                score=hit.score,
                backend=hit.backend,
                index_revision=hit.vector_index_revision,
                source_id=f"vector:{hit.vault_id}:{hit.chunk_id}",
                explanation="vector candidate matched the query",
            ),
        ),
    )


def _signal_kind_order(kind: RetrievalSignalKind) -> int:
    return {"keyword": 0, "vector": 1, "graph": 2}[kind]
