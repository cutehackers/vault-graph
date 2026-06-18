from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tests.test_context_pack_contract import make_pack
from tests.test_retrieval_result_contract import make_evidence, make_signal, make_store_revisions
from vault_graph.context.context_pack_serialization import context_pack_to_dict
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_tool_serialization import (
    context_pack_to_payload,
    query_scope_to_dict,
    resource_links_for_search,
)
from vault_graph.retrieval import RetrievalResult
from vault_graph.retrieval.search_response import SearchResponse, SearchStoreRevision


def make_search_response(*, path: str = "wiki/page.md") -> SearchResponse:
    evidence = replace(make_evidence(vault_id="main"), path=path)
    result = RetrievalResult(
        result_id="main:chunk-1",
        vault_id="main",
        kind="evidence_chunk",
        title=f"{path}#section",
        summary="Body",
        rank=1,
        evidence=(evidence,),
        signals=(make_signal(kind="keyword"),),
        relationship_status="not_applicable",
        warnings=(),
        store_revisions=make_store_revisions(),
    )
    return SearchResponse(
        query_text="GraphRAG",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        limit=10,
        result_count=1,
        candidate_count=1,
        dropped_candidate_count=0,
        results=(result,),
        warnings=(),
        degraded=False,
        store_revisions=(
            SearchStoreRevision(
                kind="metadata",
                revision="metadata-1",
                scope_key="main:wiki",
                vault_id="main",
            ),
        ),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def test_query_scope_to_dict_preserves_cross_vault_state() -> None:
    scope = QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",), include_cross_vault=True)

    assert query_scope_to_dict(scope) == {
        "vault_ids": ["main", "work"],
        "content_scopes": ["wiki"],
        "include_cross_vault": True,
    }


def test_context_pack_payload_matches_canonical_context_pack_dict() -> None:
    pack = replace(make_pack(), pack_id="pack-1")

    assert context_pack_to_payload(pack) == context_pack_to_dict(pack)


def test_search_resource_links_use_phase_5b_uri_encoding() -> None:
    response = make_search_response(path="wiki/decisions/phase 5.md")

    links = resource_links_for_search(response)

    assert ("evidence", "vault://main/documents/wiki%2Fdecisions%2Fphase%205.md") in {
        (link.rel, link.uri) for link in links
    }
    assert ("page", "vault://main/pages/wiki%2Fdecisions%2Fphase%205.md") in {
        (link.rel, link.uri) for link in links
    }


def test_tool_serialization_does_not_import_cli_helpers() -> None:
    source = Path("src/vault_graph/mcp/mcp_tool_serialization.py").read_text(encoding="utf-8")

    assert "vault_graph.cli" not in source
