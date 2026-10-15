from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from vault_graph.embeddings.text_embeddings import EmbeddingInput, TextEmbeddings
from vault_graph.errors import (
    KeywordIndexError,
    MetadataStoreError,
    RetrievalContractError,
    SearchError,
    TextEmbeddingsError,
    VectorStoreError,
)
from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.projection_readiness.search_readiness import SearchReadiness, SearchReadinessReport
from vault_graph.retrieval.candidate_ranking import (
    candidate_from_keyword_hit,
    candidate_from_vector_hit,
    family_duplication,
    fuse_candidates,
)
from vault_graph.retrieval.context_expansion import ContextExpander
from vault_graph.retrieval.evidence_result_assembly import EvidenceResultAssembly
from vault_graph.retrieval.graph_candidates import GraphCandidateProvider, GraphCandidateResult
from vault_graph.retrieval.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.retrieval_result import RetrievalResult
from vault_graph.retrieval.search_response import (
    SearchMode,
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchWarning,
)
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorQuery, VectorStore

DEFAULT_CONTEXT_EXPANSION_MAX_TOKENS = 256
DEFAULT_CONTEXT_NEIGHBOR_RADIUS = 1
SEARCH_MODE_ROLES: dict[SearchMode, tuple[DocumentRole, ...]] = {
    "knowledge": ("canonical_knowledge",),
    "evidence": ("source_manifest", "raw_evidence"),
    "operating": ("operating_contract",),
    "audit": ("generated_view", "operation_log", "audit_record"),
    "all": (
        "raw_evidence",
        "canonical_knowledge",
        "source_manifest",
        "operating_contract",
        "generated_view",
        "operation_log",
        "audit_record",
    ),
}


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
        context_expander: ContextExpander | None = None,
        context_max_tokens: int = DEFAULT_CONTEXT_EXPANSION_MAX_TOKENS,
        context_neighbor_radius: int = DEFAULT_CONTEXT_NEIGHBOR_RADIUS,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._evidence_results = EvidenceResultAssembly(metadata_store)
        self._keyword_index = keyword_index
        self._readiness = readiness
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._graph_candidate_provider = graph_candidate_provider
        if context_max_tokens <= 0:
            raise SearchError("context_max_tokens must be positive")
        if context_neighbor_radius < 0:
            raise SearchError("context_neighbor_radius must not be negative")
        self._context_expander = context_expander
        self._context_max_tokens = context_max_tokens
        self._context_neighbor_radius = context_neighbor_radius

    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        include_graph: bool = False,
        include_cross_vault: bool = False,
        mode: SearchMode = "knowledge",
    ) -> SearchResponse:
        normalized_query = query_text.strip()
        graph_requested_scope = _requested_scope_for_search(
            requested_scope=requested_scope,
            include_cross_vault=include_cross_vault,
        )
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=graph_requested_scope)
        request = SearchRequest(
            query_text=normalized_query,
            requested_scope=graph_requested_scope,
            actual_scopes=actual_scopes,
            limit=limit,
            output_format=output_format,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
            mode=mode,
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
        candidates = fuse_candidates(candidates=signal_candidates)
        results, dropped, missing_warnings = self._evidence_results.resolve_results(
            candidates=candidates, mode=request.mode, allowed_roles=SEARCH_MODE_ROLES[request.mode]
        )
        warnings.extend(missing_warnings)
        limited_results = self._expand_context(
            results=tuple(results[: request.limit]),
            request=request,
            warnings=warnings,
        )
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
            result_family_duplication=family_duplication(results),
        )

    def _expand_context(
        self,
        *,
        results: tuple[RetrievalResult, ...],
        request: SearchRequest,
        warnings: list[SearchWarning],
    ) -> tuple[RetrievalResult, ...]:
        if self._context_expander is None:
            return results
        expanded: list[RetrievalResult] = []
        for result in results:
            evidence = result.evidence[0]
            chunk = self._metadata_store.resolve_chunk(vault_id=evidence.vault_id, chunk_id=evidence.chunk_id)
            if chunk is None:
                warnings.append(
                    SearchWarning(
                        code="context_missing_chunk",
                        message=f"Context expansion could not resolve matched chunk: {evidence.chunk_id}",
                        severity="warning",
                        affected_vault_ids=(result.vault_id,),
                        document_id=evidence.document_id,
                        chunk_id=evidence.chunk_id,
                    )
                )
                expanded.append(replace(result, matched_chunk_id=evidence.chunk_id))
                continue
            try:
                expansion = self._context_expander.expand(
                    matched_chunk=chunk,
                    scope=request.requested_scope,
                    max_tokens=self._context_max_tokens,
                    neighbor_radius=self._context_neighbor_radius,
                )
            except (MetadataStoreError, RetrievalContractError) as exc:
                warnings.append(
                    SearchWarning(
                        code="context_expansion_failed",
                        message=f"Context expansion was omitted for matched chunk {chunk.chunk_id}: {exc}",
                        severity="warning",
                        affected_vault_ids=(result.vault_id,),
                        document_id=evidence.document_id,
                        chunk_id=evidence.chunk_id,
                    )
                )
                expanded.append(replace(result, matched_chunk_id=chunk.chunk_id))
                continue
            warnings.extend(
                SearchWarning(
                    code=f"context_{warning.code}",
                    message=warning.message,
                    severity=warning.severity,
                    affected_vault_ids=(result.vault_id,),
                    document_id=evidence.document_id,
                    chunk_id=evidence.chunk_id,
                )
                for warning in expansion.warnings
            )
            expanded.append(
                replace(
                    result,
                    matched_chunk_id=expansion.matched_chunk_id,
                    context_chunk_ids=expansion.context_chunk_ids,
                    context_policy_version=expansion.policy_version,
                )
            )
        return tuple(expanded)

    def _keyword_candidates(self, *, request: SearchRequest, candidate_limit: int) -> tuple[RetrievalCandidate, ...]:
        hits: list[KeywordHit] = []
        try:
            for scope in request.actual_scopes:
                hits.extend(
                    self._keyword_index.search(
                        KeywordQuery(
                            query_text=request.query_text,
                            scope=scope,
                            limit=candidate_limit,
                            source_roles=SEARCH_MODE_ROLES[request.mode],
                        )
                    )
                )
        except KeywordIndexError as exc:
            raise SearchError(f"keyword_index_unavailable: {exc}. Run `vg index`.") from exc
        return tuple(candidate_from_keyword_hit(hit) for hit in hits)

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
                            source_roles=SEARCH_MODE_ROLES[request.mode],
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
        return tuple(candidate_from_vector_hit(hit) for hit in hits)

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


def _requested_scope_for_search(*, requested_scope: QueryScope, include_cross_vault: bool) -> QueryScope:
    if not include_cross_vault or requested_scope.include_cross_vault:
        return requested_scope
    return QueryScope(
        vault_ids=requested_scope.vault_ids,
        content_scopes=requested_scope.content_scopes,
        include_cross_vault=True,
    )


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


def _affected_vault_ids(actual_scopes: tuple[QueryScope, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(vault_id for scope in actual_scopes for vault_id in scope.vault_ids)) or ("unknown",)
