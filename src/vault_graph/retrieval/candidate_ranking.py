from __future__ import annotations

from dataclasses import dataclass

from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.retrieval_result import RetrievalResult, RetrievalSignal, RetrievalSignalKind
from vault_graph.retrieval.search_response import SearchMode
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.interfaces.metadata_store import EvidenceReference
from vault_graph.storage.interfaces.vector_store import VectorHit

RANK_CONSTANT = 60.0
SIGNAL_WEIGHTS: dict[RetrievalSignalKind, float] = {"keyword": 1.0, "vector": 1.0, "graph": 0.75}


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


def rank_resolved_candidates(
    resolved: list[tuple[FusedCandidate, EvidenceReference, str]], *, mode: SearchMode
) -> list[tuple[FusedCandidate, EvidenceReference, str]]:
    sorted_resolved = sorted(
        resolved,
        key=lambda item: (
            -item[0].fused_score,
            item[0].best_signal_rank,
            item[0].vault_id,
            item[1].path,
            item[0].chunk_id,
        ),
    )
    if mode == "knowledge":
        seen_families: set[tuple[str, str]] = set()
        sorted_resolved = [
            item
            for item in sorted_resolved
            if _take_family_once(
                seen_families,
                vault_id=item[1].vault_id,
                family_id=item[1].provenance_family_id or item[1].document_id,
            )
        ]
    return sorted_resolved


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


def _take_family_once(seen: set[tuple[str, str]], *, vault_id: str, family_id: str) -> bool:
    key = (vault_id, family_id)
    if key in seen:
        return False
    seen.add(key)
    return True


def _signal_kind_order(kind: RetrievalSignalKind) -> int:
    return {"keyword": 0, "vector": 1, "graph": 2}[kind]
