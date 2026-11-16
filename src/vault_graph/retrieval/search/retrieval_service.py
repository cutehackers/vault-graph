from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from vault_graph.errors import (
    KeywordIndexError,
    MetadataStoreError,
    RetrievalContractError,
    SearchError,
    TextEmbeddingsError,
    VectorStoreError,
)
from vault_graph.indexing.ingestion.document_authority import DocumentRole
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.indexing.ingestion.session_group import session_group_key
from vault_graph.operation.readiness.search_readiness import SearchReadiness, SearchReadinessReport
from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.search.candidate_ranking import (
    FusedCandidate,
    candidate_from_keyword_hit,
    candidate_from_vector_hit,
    document_rank_trace,
    family_duplication,
    fuse_candidates,
    fused_rank_trace,
    is_fact_key,
    signal_rank_trace,
)
from vault_graph.retrieval.search.context_expansion import ContextExpander
from vault_graph.retrieval.search.evidence_result_assembly import EvidenceResultAssembly
from vault_graph.retrieval.search.graph_candidates import GraphCandidateProvider, GraphCandidateResult
from vault_graph.retrieval.search.reranker import (
    Reranker,
    RerankError,
    RerankerUnavailableError,
    RerankTrace,
    renumber_results,
    rerank_results,
)
from vault_graph.retrieval.search.retrieval_candidate import RetrievalCandidate
from vault_graph.retrieval.search.retrieval_result import RetrievalResult
from vault_graph.retrieval.search.search_response import (
    SearchMode,
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchStageTrace,
    SearchStoreRevision,
    SearchWarning,
)
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordIndex, KeywordQuery
from vault_graph.storage.interfaces.metadata_store import (
    ChunkKey,
    DatedChunkKeys,
    DateRangeChunkLookup,
    MetadataStore,
)
from vault_graph.storage.interfaces.text_embeddings import EmbeddingVector, TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorHit, VectorQuery, VectorStore

DEFAULT_CONTEXT_EXPANSION_MAX_TOKENS = 256
DEFAULT_CONTEXT_NEIGHBOR_RADIUS = 1
# Candidates per signal: max(limit * CANDIDATES_PER_RESULT, MIN_CANDIDATES). Chunks fold into one result per
# document, so when a full candidate list gives fewer results than the limit, the search runs again once
# with CANDIDATE_REFILL_FACTOR times as many candidates.
CANDIDATES_PER_RESULT = 4
MIN_CANDIDATES = 20
CANDIDATE_REFILL_FACTOR = 4
# Spec 2026-11-16 longmemeval-session-memory D11, F6: notes about a date range, not a degraded search.
DATE_RANGE_WARNING_CODES = ("date_unknown_excluded", "date_range_empty")
# Spec 2026-11-05 §10.2 원인1: knowledge mode reads source pages too and ranks them with a role weight
# (candidate_ranking.SEARCH_MODE_ROLE_WEIGHTS). Raw evidence, sessions included, stays in evidence mode.
SEARCH_MODE_ROLES: dict[SearchMode, tuple[DocumentRole, ...]] = {
    "knowledge": ("canonical_knowledge", "source_manifest"),
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
        reranker: Reranker | None = None,
        reranker_config_error: str | None = None,
    ) -> None:
        """``reranker`` reorders the top results after the candidate rounds (spec 2026-11-13 D6). Without it
        the search order stays as ranked. ``reranker_config_error`` is why the settings turned reranking off;
        each search then carries a ``reranker_config_invalid`` warning (D11)."""
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
        self._reranker = reranker
        self._reranker_config_error = reranker_config_error

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
        include_retired: bool = False,
        trace: bool = False,
        since: date | None = None,
        until: date | None = None,
        include_fact_keys: bool = True,
        date_strict: bool = False,
    ) -> SearchResponse:
        """Search the scope. ``trace`` adds ``SearchResponse.stage_trace`` for the evaluation tool (spec
        2026-11-11 §4.1.2). It only records ranks the search computes anyway, so results and their order do
        not change.

        ``since``·``until`` (inclusive, this computer's time zone) build the in-range results from chunks whose
        time range overlaps them or whose exchange has a session fact dated inside them, before keyword and vector
        candidates are ranked (spec 2026-11-16 D9, D10, D30). The in-range results come first and the remaining
        slots take the results of the same search without the range that are not already there (D31). With
        ``date_strict`` only the in-range results stay, undated chunks are counted in a ``date_unknown_excluded``
        warning and an empty result gets ``date_range_empty`` (D11). Without a range the search is as before (I5).

        Session fact chunks are keys that lead to their original exchange (spec 2026-11-16 D21). With
        ``include_fact_keys`` False they are left out of the keyword and vector lists before ranking, so the
        search is as before fact attachments (I6)."""
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
            include_retired=include_retired,
            trace=trace,
            since=since,
            until=until,
            include_fact_keys=include_fact_keys,
            date_strict=date_strict,
        )
        return self._search_request(request)

    def _search_request(self, request: SearchRequest) -> SearchResponse:
        readiness = self._readiness.check(actual_scopes=request.actual_scopes)
        fatal = _fatal_readiness_error(readiness)
        if fatal is not None:
            raise fatal
        warnings = list(_warnings_for_readiness(readiness, request.actual_scopes))
        query_vector = self._query_vector(request=request, readiness=readiness, warnings=warnings)
        dated = self._dated_chunk_keys(request)
        ranked = self._ranked_pass(
            request=request,
            readiness=readiness,
            query_vector=query_vector,
            chunk_keys=None if dated is None else dated.chunk_keys,
        )
        results = ranked.results
        signal_count = ranked.signal_count
        dropped = ranked.dropped
        rerank_warnings = ranked.rerank_warnings
        pass_warnings = ranked.pass_warnings
        store_revisions = ranked.graph_store_revisions
        if dated is not None and not request.date_strict and len(results) < request.limit:
            # Spec 2026-11-16 D31: the remaining slots take the same search without the range, in its order.
            fill = self._ranked_pass(request=request, readiness=readiness, query_vector=query_vector, chunk_keys=None)
            results = renumber_results((*results, *self._results_not_present(results, fill.results)))
            signal_count += fill.signal_count
            dropped += fill.dropped
            rerank_warnings = _unique_warnings((*rerank_warnings, *fill.rerank_warnings))
            pass_warnings = _unique_warnings((*pass_warnings, *fill.pass_warnings))
            store_revisions = tuple(dict.fromkeys((*store_revisions, *fill.graph_store_revisions)))
        if self._reranker_config_error is not None:
            warnings.append(_reranker_warning(request, "reranker_config_invalid", self._reranker_config_error))
        warnings.extend(rerank_warnings)
        warnings.extend(pass_warnings)
        limited_results = self._expand_context(
            results=tuple(results[: request.limit]),
            request=request,
            warnings=warnings,
        )
        if dated is not None and request.date_strict:
            warnings.extend(_date_range_warnings(request, dated, result_count=len(limited_results)))
        return SearchResponse(
            query_text=request.query_text,
            requested_scope=request.requested_scope,
            actual_scopes=request.actual_scopes,
            limit=request.limit,
            result_count=len(limited_results),
            candidate_count=signal_count,
            dropped_candidate_count=dropped,
            results=limited_results,
            warnings=tuple(warnings),
            degraded=any(warning.code not in DATE_RANGE_WARNING_CODES for warning in warnings),
            store_revisions=readiness.store_revisions + store_revisions,
            generated_at=datetime.now(UTC).isoformat(),
            result_family_duplication=family_duplication(results),
            stage_trace=(
                SearchStageTrace(
                    signal_ranks=signal_rank_trace(ranked.signal_candidates),
                    fused_ranks=fused_rank_trace(ranked.candidates),
                    document_ranks=document_rank_trace(tuple(results)),
                    candidate_limit=ranked.candidate_limit,
                    refilled=ranked.refilled,
                    rerank=ranked.rerank_trace,
                )
                if request.trace
                else None
            ),
        )

    def _ranked_pass(
        self,
        *,
        request: SearchRequest,
        readiness: SearchReadinessReport,
        query_vector: EmbeddingVector | None,
        chunk_keys: frozenset[ChunkKey] | None,
    ) -> _RankedPass:
        """One search over the candidates inside ``chunk_keys`` (None: all), ranked and reranked, before the limit."""
        candidate_limit = max(request.limit * CANDIDATES_PER_RESULT, MIN_CANDIDATES)
        refilled = False
        for refill in (False, True):
            refilled = refill
            round_warnings: list[SearchWarning] = []
            keyword_candidates = self._keyword_candidates(
                request=request, candidate_limit=candidate_limit, chunk_keys=chunk_keys
            )
            vector_candidates = self._vector_candidates(
                request=request,
                candidate_limit=candidate_limit,
                readiness=readiness,
                query_vector=query_vector,
                warnings=round_warnings,
                chunk_keys=chunk_keys,
            )
            graph_result = self._graph_candidates(request=request, candidate_limit=candidate_limit)
            if chunk_keys is not None:
                graph_result = replace(graph_result, candidates=_inside(graph_result.candidates, chunk_keys))
            signal_candidates = keyword_candidates + vector_candidates + graph_result.candidates
            candidates = fuse_candidates(candidates=signal_candidates)
            results, passages, dropped, missing_warnings = self._evidence_results.resolve_results(
                candidates=candidates,
                mode=request.mode,
                allowed_roles=SEARCH_MODE_ROLES[request.mode],
                include_retired=request.include_retired,
                vault_order=_affected_vault_ids(request.actual_scopes),
                query_text=request.query_text,
                include_fact_keys=request.include_fact_keys,
            )
            saturated = candidate_limit in (len(keyword_candidates), len(vector_candidates))
            if refill or len(results) >= request.limit or not saturated:
                break
            candidate_limit *= CANDIDATE_REFILL_FACTOR
        rerank_trace = None
        rerank_warnings: list[SearchWarning] = []
        if self._reranker is not None:
            # After the refill decision and before the limit, so the candidate rounds stay as they are.
            # A failure keeps the search order for this query only; the next query asks the model again.
            try:
                reranked = rerank_results(
                    query_text=request.query_text, results=results, passages=passages, reranker=self._reranker
                )
            except RerankerUnavailableError as exc:
                rerank_warnings.append(
                    _reranker_warning(
                        request,
                        "reranker_unavailable",
                        f"{exc}. Run `vg reranker use {self._reranker.preset}` to download it, or `vg reranker off`",
                    )
                )
            except RerankError as exc:
                rerank_warnings.append(_reranker_warning(request, "rerank_failed", str(exc)))
            else:
                results = reranked.results
                rerank_trace = reranked.trace
        return _RankedPass(
            results=tuple(results),
            signal_candidates=signal_candidates,
            candidates=candidates,
            signal_count=sum(len(candidate.signals) for candidate in signal_candidates),
            dropped=dropped,
            rerank_warnings=tuple(rerank_warnings),
            pass_warnings=(*round_warnings, *graph_result.warnings, *missing_warnings),
            graph_store_revisions=graph_result.store_revisions,
            candidate_limit=candidate_limit,
            refilled=refilled,
            rerank_trace=rerank_trace,
        )

    def _results_not_present(
        self, present: tuple[RetrievalResult, ...], fill: tuple[RetrievalResult, ...]
    ) -> tuple[RetrievalResult, ...]:
        """Results of ``fill`` whose unit is not already in ``present``, in order (spec 2026-11-16 D31, I4).

        A result's unit is every document of its evidence, plus its session (`<agent>:<session_id>`) when it is a
        session file, so another exchange of a session already in the list is not added again."""
        documents: dict[str, DocumentSnapshot | None] = {}

        def unit(result: RetrievalResult) -> set[tuple[str, str]]:
            keys = {(evidence.vault_id, evidence.document_id) for evidence in result.evidence}
            document_id = result.evidence[0].document_id
            if document_id not in documents:
                documents[document_id] = self._metadata_store.resolve_document(document_id)
            document = documents[document_id]
            session = session_group_key(document.frontmatter) if document is not None else None
            if session is not None:
                keys.add((result.vault_id, f"session:{session}"))
            return keys

        seen: set[tuple[str, str]] = set()
        for result in present:
            seen |= unit(result)
        kept: list[RetrievalResult] = []
        for result in fill:
            keys = unit(result)
            if keys & seen:
                continue
            seen |= keys
            kept.append(result)
        return tuple(kept)

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

    def _dated_chunk_keys(self, request: SearchRequest) -> DatedChunkKeys | None:
        """Chunks in the request's date range across its scopes. None when the request has no range."""
        if request.since is None and request.until is None:
            return None
        if not isinstance(self._metadata_store, DateRangeChunkLookup):
            raise SearchError("date_filter_unavailable: the metadata store cannot look up chunk times")
        keys: set[ChunkKey] = set()
        undated = 0
        try:
            for scope in request.actual_scopes:
                found = self._metadata_store.chunk_keys_in_date_range(
                    scope,
                    since=request.since,
                    until=request.until,
                    source_roles=SEARCH_MODE_ROLES[request.mode],
                )
                keys.update(found.chunk_keys)
                undated += found.undated_count
        except MetadataStoreError as exc:
            raise SearchError(f"metadata_unavailable: {exc}. Run `vg index`.") from exc
        return DatedChunkKeys(chunk_keys=frozenset(keys), undated_count=undated)

    def _keyword_candidates(
        self, *, request: SearchRequest, candidate_limit: int, chunk_keys: frozenset[ChunkKey] | None
    ) -> tuple[RetrievalCandidate, ...]:

        def fetch(limit: int) -> tuple[KeywordHit, ...]:
            per_scope = [
                self._keyword_index.search(
                    KeywordQuery(
                        query_text=request.query_text,
                        scope=scope,
                        limit=limit,
                        source_roles=SEARCH_MODE_ROLES[request.mode],
                        with_matched_fields=False,
                        chunk_keys=chunk_keys,
                    )
                )
                for scope in request.actual_scopes
            ]
            return _merge_scope_hits(per_scope, limit=limit, score_sign=1.0)

        try:
            hits = self._hits(fetch, limit=candidate_limit, include_fact_keys=request.include_fact_keys)
        except KeywordIndexError as exc:
            raise SearchError(f"keyword_index_unavailable: {exc}. Run `vg index`.") from exc
        # Spec 2026-11-05 §10.2 원인4: one keyword table holds every Vault, so bm25 scores (lower is better)
        # compare across scopes and give one ranking for the whole scope (`_merge_scope_hits`).
        return _inside(tuple(candidate_from_keyword_hit(hit) for hit in hits), chunk_keys)

    def _vector_candidates(
        self,
        *,
        request: SearchRequest,
        candidate_limit: int,
        readiness: SearchReadinessReport,
        query_vector: EmbeddingVector | None,
        warnings: list[SearchWarning],
        chunk_keys: frozenset[ChunkKey] | None = None,
    ) -> tuple[RetrievalCandidate, ...]:
        if self._vector_store is None or self._text_embeddings is None or query_vector is None:
            return ()
        vector_store = self._vector_store
        text_embeddings = self._text_embeddings

        def fetch(limit: int) -> tuple[VectorHit, ...]:
            per_scope = [
                vector_store.search(
                    VectorQuery(
                        query_vector=query_vector,
                        scope=scope,
                        limit=limit,
                        embedding_spec=text_embeddings.model_spec(),
                        source_roles=SEARCH_MODE_ROLES[request.mode],
                        chunk_keys=chunk_keys,
                    )
                )
                for scope in request.actual_scopes
                if _vector_stale_count_for_scope(readiness=readiness, scope=scope) in (None, 0)
            ]
            # Spec 2026-11-05 §10.2 원인4: cosine similarity (higher is better) compares across Vaults.
            return _merge_scope_hits(per_scope, limit=limit, score_sign=-1.0)

        try:
            hits = self._hits(fetch, limit=candidate_limit, include_fact_keys=request.include_fact_keys)
        except VectorStoreError as exc:
            warnings.append(_vector_query_failed(request, exc))
            return ()
        return _inside(tuple(candidate_from_vector_hit(hit) for hit in hits), chunk_keys)

    def _hits[Hit: (KeywordHit, VectorHit)](
        self, fetch: Callable[[int], tuple[Hit, ...]], *, limit: int, include_fact_keys: bool
    ) -> tuple[Hit, ...]:
        """One signal's ranked hits. Without fact keys, session fact chunks are dropped and the list is filled up
        to ``limit`` from further hits and ranked 1..n again, as if the facts were not indexed (spec 2026-11-16
        I6). Each hit's chunk is read once, only in that mode."""
        if include_fact_keys:
            return fetch(limit)
        facts: dict[tuple[str, str], bool] = {}

        def is_fact(hit: Hit) -> bool:
            key = (hit.vault_id, hit.chunk_id)
            if key not in facts:
                chunk = self._metadata_store.resolve_chunk(vault_id=hit.vault_id, chunk_id=hit.chunk_id)
                facts[key] = chunk is not None and is_fact_key(chunk)
            return facts[key]

        asked = limit
        while True:
            hits = fetch(asked)
            kept = tuple(hit for hit in hits if not is_fact(hit))
            if len(kept) >= limit or len(hits) < asked:
                break
            asked += limit - len(kept)
        return tuple(replace(hit, rank=rank) for rank, hit in enumerate(kept[:limit], start=1))

    def _query_vector(
        self,
        *,
        request: SearchRequest,
        readiness: SearchReadinessReport,
        warnings: list[SearchWarning],
    ) -> EmbeddingVector | None:
        if self._vector_store is None or self._text_embeddings is None:
            return None
        if not _can_run_vector_search_globally(readiness):
            return None
        try:
            return self._text_embeddings.embed_query(request.query_text)
        except TextEmbeddingsError as exc:
            warnings.append(_vector_query_failed(request, exc))
            return None

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


@dataclass(frozen=True)
class _RankedPass:
    """One candidate search, ranked and reranked, before the limit and context expansion."""

    results: tuple[RetrievalResult, ...]
    signal_candidates: tuple[RetrievalCandidate, ...]
    candidates: tuple[FusedCandidate, ...]
    signal_count: int
    dropped: int
    rerank_warnings: tuple[SearchWarning, ...]
    pass_warnings: tuple[SearchWarning, ...]
    graph_store_revisions: tuple[SearchStoreRevision, ...]
    candidate_limit: int
    refilled: bool
    rerank_trace: RerankTrace | None


def _unique_warnings(warnings: tuple[SearchWarning, ...]) -> tuple[SearchWarning, ...]:
    """The warnings of two searches of one request, each once, in order."""
    return tuple(dict.fromkeys(warnings))


def _merge_scope_hits[Hit: (KeywordHit, VectorHit)](
    per_scope: list[tuple[Hit, ...]], *, limit: int, score_sign: float
) -> tuple[Hit, ...]:
    """Merge per-scope hit lists into one list ranked 1..n by score. A single list keeps its own order.

    ``score_sign`` 1.0 sorts ascending (bm25), -1.0 descending (cosine similarity). Ties keep scope order,
    then each scope's own rank.
    """
    if len(per_scope) <= 1:
        return per_scope[0] if per_scope else ()
    ordered = sorted(
        (
            (score_sign * hit.score, scope_index, hit.rank, hit.vault_id, hit.chunk_id, hit)
            for scope_index, hits in enumerate(per_scope)
            for hit in hits
        ),
        key=lambda entry: entry[:5],
    )
    return tuple(replace(entry[5], rank=rank) for rank, entry in enumerate(ordered[:limit], start=1))


def _inside(
    candidates: tuple[RetrievalCandidate, ...], chunk_keys: frozenset[ChunkKey] | None
) -> tuple[RetrievalCandidate, ...]:
    """Drop candidates outside the date range. The stores already search inside it; this also covers graph
    candidates and a store that ignores the key set."""
    if chunk_keys is None:
        return candidates
    return tuple(candidate for candidate in candidates if (candidate.vault_id, candidate.chunk_id) in chunk_keys)


def _date_range_warnings(request: SearchRequest, dated: DatedChunkKeys, *, result_count: int) -> list[SearchWarning]:
    """Spec 2026-11-16 D11, F6: one note for the undated chunks left out, one for an empty result."""
    affected = _affected_vault_ids(request.actual_scopes)
    span = f"{request.since or '…'}..{request.until or '…'}"
    warnings: list[SearchWarning] = []
    if dated.undated_count:
        warnings.append(
            SearchWarning(
                code="date_unknown_excluded",
                message=(
                    f"{dated.undated_count} chunks without a date (wiki pages and other undated files) were left out "
                    f"of the date range {span}"
                ),
                severity="info",
                affected_vault_ids=affected,
            )
        )
    if result_count == 0:
        warnings.append(
            SearchWarning(
                code="date_range_empty",
                message=f"No dated results in {span}",
                severity="info",
                affected_vault_ids=affected,
            )
        )
    return warnings


def _reranker_warning(request: SearchRequest, code: str, detail: str) -> SearchWarning:
    return SearchWarning(
        code=code,
        message=f"Reranking skipped; results keep the search order: {detail}",
        severity="warning",
        affected_vault_ids=_affected_vault_ids(request.actual_scopes),
    )


def _vector_query_failed(request: SearchRequest, exc: Exception) -> SearchWarning:
    return SearchWarning(
        code="vector_query_failed",
        message=f"Vector query failed; keyword-only results returned: {exc}",
        severity="warning",
        affected_vault_ids=_affected_vault_ids(request.actual_scopes),
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
