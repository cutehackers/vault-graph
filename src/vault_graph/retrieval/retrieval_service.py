from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.embeddings.text_embeddings import EmbeddingInput, TextEmbeddings
from vault_graph.errors import KeywordIndexError, SearchError, TextEmbeddingsError, VectorStoreError
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph_candidates import GraphCandidateProvider, GraphCandidateResult
from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.retrieval_result import (
    RetrievalResult,
    RetrievalSignal,
    RetrievalSignalKind,
    StoreRevision,
)
from vault_graph.retrieval.search_readiness import SearchReadiness, SearchReadinessReport
from vault_graph.retrieval.search_response import (
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchWarning,
)
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorQuery, VectorStore

RANK_CONSTANT = 60.0
SIGNAL_WEIGHTS: dict[RetrievalSignalKind, float] = {"keyword": 1.0, "vector": 1.0, "graph": 0.5}


class RetrievalService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        readiness: SearchReadiness,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        graph_candidate_provider: GraphCandidateProvider | None = None,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._keyword_index = keyword_index
        self._readiness = readiness
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._graph_candidate_provider = graph_candidate_provider

    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> SearchResponse:
        normalized_query = query_text.strip()
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
        request = SearchRequest(
            query_text=normalized_query,
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            limit=limit,
            output_format=output_format,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
        )
        return self._search_request(request)

    def _search_request(self, request: SearchRequest) -> SearchResponse:
        candidate_limit = max(request.limit * 4, 20)
        readiness = self._readiness.check(actual_scopes=request.actual_scopes)
        fatal = _fatal_readiness_error(readiness)
        if fatal is not None:
            raise fatal
        warnings = list(_warnings_for_readiness(readiness, request.actual_scopes))
        keyword_candidates = self._keyword_candidates(request=request, candidate_limit=candidate_limit)
        vector_candidates = self._vector_candidates(
            request=request,
            candidate_limit=candidate_limit,
            readiness=readiness,
            warnings=warnings,
        )
        graph_result = self._graph_candidates(request=request, candidate_limit=candidate_limit)
        warnings.extend(graph_result.warnings)
        signal_candidates = keyword_candidates + vector_candidates + graph_result.candidates
        candidates = _fuse_candidates(candidates=signal_candidates)
        results, dropped, missing_warnings = self._resolve_results(candidates=candidates)
        warnings.extend(missing_warnings)
        limited_results = tuple(results[: request.limit])
        return SearchResponse(
            query_text=request.query_text,
            requested_scope=request.requested_scope,
            actual_scopes=request.actual_scopes,
            limit=request.limit,
            result_count=len(limited_results),
            candidate_count=sum(len(candidate.signals) for candidate in signal_candidates),
            dropped_candidate_count=dropped,
            results=limited_results,
            warnings=tuple(warnings),
            degraded=bool(warnings),
            store_revisions=readiness.store_revisions + graph_result.store_revisions,
            generated_at=datetime.now(UTC).isoformat(),
        )

    def _keyword_candidates(self, *, request: SearchRequest, candidate_limit: int) -> tuple[RetrievalCandidate, ...]:
        hits: list[KeywordHit] = []
        try:
            for scope in request.actual_scopes:
                hits.extend(
                    self._keyword_index.search(
                        KeywordQuery(query_text=request.query_text, scope=scope, limit=candidate_limit)
                    )
                )
        except KeywordIndexError as exc:
            raise SearchError(f"keyword_index_unavailable: {exc}. Run `vg index`.") from exc
        return tuple(_candidate_from_keyword_hit(hit) for hit in hits)

    def _vector_candidates(
        self,
        *,
        request: SearchRequest,
        candidate_limit: int,
        readiness: SearchReadinessReport,
        warnings: list[SearchWarning],
    ) -> tuple[RetrievalCandidate, ...]:
        if self._vector_store is None or self._text_embeddings is None:
            return ()
        if not _can_run_vector_search_globally(readiness):
            return ()
        try:
            query_vector = self._text_embeddings.embed((EmbeddingInput(input_id="query", text=request.query_text),))[0]
            hits: list[VectorHit] = []
            for scope in request.actual_scopes:
                if _vector_stale_count_for_scope(readiness=readiness, scope=scope) not in (None, 0):
                    continue
                hits.extend(
                    self._vector_store.search(
                        VectorQuery(
                            query_vector=query_vector,
                            scope=scope,
                            limit=candidate_limit,
                            embedding_spec=self._text_embeddings.model_spec(),
                        )
                    )
                )
        except (TextEmbeddingsError, VectorStoreError) as exc:
            warnings.append(
                SearchWarning(
                    code="vector_query_failed",
                    message=f"Vector query failed; keyword-only results returned: {exc}",
                    severity="warning",
                    affected_vault_ids=_affected_vault_ids(request.actual_scopes),
                )
            )
            return ()
        return tuple(_candidate_from_vector_hit(hit) for hit in hits)

    def _graph_candidates(self, *, request: SearchRequest, candidate_limit: int) -> GraphCandidateResult:
        if not request.include_graph or self._graph_candidate_provider is None:
            return GraphCandidateResult(candidates=(), warnings=(), store_revisions=())
        return self._graph_candidate_provider.candidates(
            query_text=request.query_text,
            requested_scope=request.requested_scope,
            actual_scopes=request.actual_scopes,
            limit=candidate_limit,
            include_cross_vault=request.include_cross_vault,
        )

    def _resolve_results(
        self,
        *,
        candidates: tuple[_FusedCandidate, ...],
    ) -> tuple[tuple[RetrievalResult, ...], int, tuple[SearchWarning, ...]]:
        dropped = 0
        warnings: list[SearchWarning] = []
        resolved: list[tuple[_FusedCandidate, EvidenceReference, str]] = []
        for candidate in candidates:
            evidence = self._metadata_store.resolve_chunk_evidence(
                vault_id=candidate.vault_id,
                document_id=candidate.document_id,
                chunk_id=candidate.chunk_id,
            )
            chunk = self._metadata_store.resolve_chunk(vault_id=candidate.vault_id, chunk_id=candidate.chunk_id)
            if evidence is None or chunk is None:
                dropped += 1
                warnings.append(
                    SearchWarning(
                        code="missing_evidence",
                        message=f"Metadata evidence could not be resolved for search candidate: {candidate.chunk_id}",
                        severity="warning",
                        affected_vault_ids=(candidate.vault_id,),
                        document_id=candidate.document_id,
                        chunk_id=candidate.chunk_id,
                    )
                )
                continue
            resolved.append((candidate, evidence, _excerpt(chunk.text)))

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
        results = tuple(
            _retrieval_result_for_candidate(candidate=candidate, evidence=evidence, summary=summary, rank=rank)
            for rank, (candidate, evidence, summary) in enumerate(sorted_resolved, start=1)
        )
        return results, dropped, tuple(warnings)


@dataclass(frozen=True)
class _FusedCandidate:
    vault_id: str
    document_id: str
    chunk_id: str
    fused_score: float
    best_signal_rank: int
    signals: tuple[RetrievalSignal, ...]


def _fatal_readiness_error(readiness: SearchReadinessReport) -> SearchError | None:
    if not readiness.metadata_health.ok or not readiness.metadata_health.schema_compatible:
        return SearchError(f"metadata_unavailable: {readiness.metadata_health.message}. Run `vg index`.")
    if not readiness.keyword_health.ok or not readiness.keyword_health.schema_compatible:
        return SearchError(f"keyword_index_unavailable: {readiness.keyword_health.message}. Run `vg index`.")
    return None


def _warnings_for_readiness(
    readiness: SearchReadinessReport,
    actual_scopes: tuple[QueryScope, ...],
) -> tuple[SearchWarning, ...]:
    affected_vault_ids = _affected_vault_ids(actual_scopes)
    warnings: list[SearchWarning] = []
    vector_unavailable = readiness.vector_health is None or not (
        readiness.vector_health.ok and readiness.vector_health.schema_compatible
    )
    if vector_unavailable:
        message = readiness.vector_health.message if readiness.vector_health is not None else "not configured"
        warnings.append(
            SearchWarning(
                code="vector_unavailable",
                message=f"Vector search is unavailable; keyword-only results returned: {message}",
                severity="warning",
                affected_vault_ids=affected_vault_ids,
            )
        )
    warnings.extend(_vector_stale_warnings(readiness=readiness, affected_vault_ids=affected_vault_ids))
    if not readiness.can_embed_without_download:
        warnings.append(
            SearchWarning(
                code="embedding_model_unavailable",
                message="Embedding model is not available locally; keyword-only results returned.",
                severity="warning",
                affected_vault_ids=affected_vault_ids,
            )
        )
    if warnings:
        degraded_vault_ids = tuple(
            dict.fromkeys(vault_id for warning in warnings for vault_id in warning.affected_vault_ids)
        )
        warnings.append(
            SearchWarning(
                code="degraded_keyword_only",
                message="Search completed with keyword-only retrieval.",
                severity="warning",
                affected_vault_ids=degraded_vault_ids,
            )
        )
    return tuple(warnings)


def _vector_stale_warnings(
    *,
    readiness: SearchReadinessReport,
    affected_vault_ids: tuple[str, ...],
) -> tuple[SearchWarning, ...]:
    if readiness.scope_readiness:
        return tuple(
            SearchWarning(
                code="vector_stale",
                message=f"Vector index has {scope.vector_stale_count} stale records; keyword-only results returned.",
                severity="warning",
                affected_vault_ids=scope.vault_ids,
                scope_key=scope.scope_key,
            )
            for scope in readiness.scope_readiness
            if scope.vector_stale_count is not None and scope.vector_stale_count > 0
        )
    if readiness.vector_stale_count is not None and readiness.vector_stale_count > 0:
        return (
            SearchWarning(
                code="vector_stale",
                message=(
                    f"Vector index has {readiness.vector_stale_count} stale records; keyword-only results returned."
                ),
                severity="warning",
                affected_vault_ids=affected_vault_ids,
            ),
        )
    return ()


def _can_run_vector_search_globally(readiness: SearchReadinessReport) -> bool:
    return (
        readiness.vector_health is not None
        and readiness.vector_health.ok
        and readiness.vector_health.schema_compatible
        and readiness.can_embed_without_download
    )


def _vector_stale_count_for_scope(*, readiness: SearchReadinessReport, scope: QueryScope) -> int | None:
    scope_key = f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"
    for scope_readiness in readiness.scope_readiness:
        if scope_readiness.scope_key == scope_key:
            return scope_readiness.vector_stale_count
    return readiness.vector_stale_count


def _fuse_candidates(*, candidates: tuple[RetrievalCandidate, ...]) -> tuple[_FusedCandidate, ...]:
    grouped: dict[tuple[str, str], list[RetrievalSignal]] = {}
    document_by_key: dict[tuple[str, str], str] = {}
    for candidate in candidates:
        key = (candidate.vault_id, candidate.chunk_id)
        document_by_key.setdefault(key, candidate.document_id)
        grouped.setdefault(key, []).extend(candidate.signals)

    fused_candidates: list[_FusedCandidate] = []
    for (vault_id, chunk_id), signals in grouped.items():
        fused_candidates.append(
            _FusedCandidate(
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


def _candidate_from_keyword_hit(hit: KeywordHit) -> RetrievalCandidate:
    return RetrievalCandidate(
        vault_id=hit.vault_id,
        document_id=hit.document_id,
        chunk_id=hit.chunk_id,
        signals=(_keyword_signal(hit),),
    )


def _candidate_from_vector_hit(hit: VectorHit) -> RetrievalCandidate:
    return RetrievalCandidate(
        vault_id=hit.vault_id,
        document_id=hit.document_id,
        chunk_id=hit.chunk_id,
        signals=(_vector_signal(hit),),
    )


def _keyword_signal(hit: KeywordHit) -> RetrievalSignal:
    return RetrievalSignal(
        kind="keyword",
        rank=hit.rank,
        score=hit.score,
        backend=hit.backend,
        index_revision=hit.index_revision,
        source_id=f"keyword:{hit.vault_id}:{hit.chunk_id}",
        explanation="keyword candidate matched the query",
    )


def _vector_signal(hit: VectorHit) -> RetrievalSignal:
    return RetrievalSignal(
        kind="vector",
        rank=hit.rank,
        score=hit.score,
        backend=hit.backend,
        index_revision=hit.vector_index_revision,
        source_id=f"vector:{hit.vault_id}:{hit.chunk_id}",
        explanation="vector candidate matched the query",
    )


def _retrieval_result_for_candidate(
    *,
    candidate: _FusedCandidate,
    evidence: EvidenceReference,
    summary: str,
    rank: int,
) -> RetrievalResult:
    return RetrievalResult(
        result_id=f"{candidate.vault_id}:{candidate.chunk_id}:rank-{rank}",
        vault_id=candidate.vault_id,
        kind="evidence_chunk",
        title=_title_for_evidence(evidence),
        summary=summary,
        rank=rank,
        evidence=(evidence,),
        signals=candidate.signals,
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=_result_store_revisions(candidate=candidate, evidence=evidence),
    )


def _result_store_revisions(*, candidate: _FusedCandidate, evidence: EvidenceReference) -> tuple[StoreRevision, ...]:
    revisions = []
    if evidence.metadata_index_revision:
        revisions.append(StoreRevision(kind="metadata", revision=evidence.metadata_index_revision))
    for signal in candidate.signals:
        revisions.append(StoreRevision(kind=signal.kind, revision=signal.index_revision))
    return tuple(dict.fromkeys(revisions))


def _title_for_evidence(evidence: EvidenceReference) -> str:
    if evidence.anchor:
        return f"{evidence.path}#{evidence.anchor}"
    if evidence.section:
        return f"{evidence.path}#{evidence.section}"
    return evidence.path


def _excerpt(text: str, *, max_length: int = 240) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3].rstrip()}..."


def _affected_vault_ids(actual_scopes: tuple[QueryScope, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids)) or ("unknown",)


def _signal_kind_order(kind: RetrievalSignalKind) -> int:
    return {"keyword": 0, "vector": 1, "graph": 2}[kind]
