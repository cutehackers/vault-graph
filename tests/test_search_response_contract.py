import pytest

from tests.test_retrieval_result_contract import make_evidence, make_signal, make_store_revisions
from vault_graph.errors import SearchError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval import RetrievalResult
from vault_graph.retrieval.search_response import (
    SearchOutputFormat,
    SearchRequest,
    SearchResponse,
    SearchStoreRevision,
    SearchWarning,
)


def _result() -> RetrievalResult:
    return RetrievalResult(
        result_id="default:chunk:rank-1",
        vault_id="default",
        kind="evidence_chunk",
        title="wiki/page.md#section",
        summary="Body",
        rank=1,
        evidence=(make_evidence(),),
        signals=(make_signal(kind="keyword"),),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )


def test_search_request_rejects_empty_query() -> None:
    with pytest.raises(SearchError, match="query_text is required"):
        SearchRequest(
            query_text=" ",
            requested_scope=QueryScope(vault_ids=("default",)),
            effective_scopes=(QueryScope(vault_ids=("default",)),),
            limit=10,
            output_format="text",
        )


def test_search_response_records_query_wide_degraded_state() -> None:
    warning = SearchWarning(
        code="vector_unavailable",
        message="Vector search is unavailable",
        severity="warning",
        affected_vault_ids=("default",),
    )
    response = SearchResponse(
        query_text="GraphRAG",
        requested_scope=QueryScope(vault_ids=("default",)),
        effective_scopes=(QueryScope(vault_ids=("default",)),),
        limit=10,
        result_count=1,
        candidate_count=2,
        dropped_candidate_count=1,
        results=(_result(),),
        warnings=(warning,),
        degraded=True,
        store_revisions=(
            SearchStoreRevision(
                kind="metadata",
                revision="metadata-1",
                scope_key="default:wiki",
                vault_id="default",
            ),
        ),
        generated_at="2026-06-09T00:00:00+00:00",
    )

    assert response.degraded is True
    assert response.warnings[0].affected_vault_ids == ("default",)
    assert response.result_count == len(response.results)


def test_search_response_rejects_result_count_mismatch() -> None:
    with pytest.raises(SearchError, match="result_count must match results"):
        SearchResponse(
            query_text="GraphRAG",
            requested_scope=QueryScope(vault_ids=("default",)),
            effective_scopes=(QueryScope(vault_ids=("default",)),),
            limit=10,
            result_count=2,
            candidate_count=1,
            dropped_candidate_count=0,
            results=(_result(),),
            warnings=(),
            degraded=False,
            store_revisions=(
                SearchStoreRevision(
                    kind="metadata",
                    revision="metadata-1",
                    scope_key="default:wiki",
                    vault_id="default",
                ),
            ),
            generated_at="2026-06-09T00:00:00+00:00",
        )


def test_search_warning_requires_vault_attribution() -> None:
    with pytest.raises(SearchError, match="affected_vault_ids is required"):
        SearchWarning(
            code="vector_unavailable",
            message="Vector search is unavailable",
            severity="warning",
            affected_vault_ids=(),
        )


def test_store_revision_requires_scope_attribution() -> None:
    with pytest.raises(SearchError, match="scope_key is required"):
        SearchStoreRevision(kind="metadata", revision="metadata-1", scope_key="")


def test_search_output_format_type_allows_text_and_json() -> None:
    text_format: SearchOutputFormat = "text"
    json_format: SearchOutputFormat = "json"

    assert text_format == "text"
    assert json_format == "json"
