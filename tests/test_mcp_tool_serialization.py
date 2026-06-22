from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

from tests.test_context_pack_contract import make_pack
from tests.test_graph_retrieval_contract import make_metadata_evidence_from_graph_ref
from tests.test_graph_store_contract import make_entity, make_relationship
from tests.test_retrieval_result_contract import make_evidence, make_signal, make_store_revisions
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPack,
    ContextPackItem,
    ContextPackSignal,
    ContextPackWarning,
)
from vault_graph.context.context_pack_serialization import context_pack_to_dict
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_tool_serialization import (
    context_pack_to_payload,
    decision_trace_response_to_payload,
    explanation_payload_to_resource_links,
    explanation_records_for_context_pack,
    explanation_records_for_decision_trace,
    explanation_records_for_related,
    explanation_records_for_search,
    query_scope_to_dict,
    related_response_to_payload,
    resource_links_for_search,
    status_report_to_payload,
)
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval import RetrievalResult
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    DecisionTraceStep,
    GraphRetrievalRevision,
    RelatedItem,
    RelatedResponse,
)
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


def make_pack_with_item() -> ContextPack:
    evidence_ref = ContextEvidenceRef(vault_id="main", document_id="doc-1", chunk_id="chunk-1")
    evidence = ContextEvidence(
        ref=evidence_ref,
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="chunk-hash",
        raw_sha256="raw-hash",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
        excerpt="Evidence excerpt",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("keyword",),
        warnings=(),
    )
    item = ContextPackItem(
        item_id="item-1",
        item_type="current_state",
        title="Current state",
        summary="Project is ready",
        evidence_refs=(evidence_ref,),
        retrieval_signals=(
            ContextPackSignal(
                kind="keyword",
                rank=1,
                score=0.7,
                explanation="matched goal terms",
            ),
        ),
        relationship_status="not_applicable",
        rank=1,
        warnings=(),
    )
    return replace(make_pack(), current_state=(item,), evidence=(evidence,))


def make_multi_vault_pack_with_warning() -> ContextPack:
    main_ref = ContextEvidenceRef(vault_id="main", document_id="doc-1", chunk_id="chunk-1")
    other_ref = ContextEvidenceRef(vault_id="other", document_id="doc-2", chunk_id="chunk-2")
    main_evidence = ContextEvidence(
        ref=main_ref,
        path="wiki/main.md",
        section=None,
        anchor=None,
        content_hash="main-hash",
        raw_sha256=None,
        metadata_index_revision="metadata-1",
        vault_revision=None,
        excerpt="Main evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("keyword",),
        warnings=(),
    )
    other_evidence = ContextEvidence(
        ref=other_ref,
        path="wiki/other.md",
        section=None,
        anchor=None,
        content_hash="other-hash",
        raw_sha256=None,
        metadata_index_revision="metadata-1",
        vault_revision=None,
        excerpt="Other evidence",
        excerpt_token_count=2,
        truncated=False,
        retrieval_reasons=("keyword",),
        warnings=(),
    )
    item = ContextPackItem(
        item_id="item-1",
        item_type="current_state",
        title="Cross vault item",
        summary="Uses two vaults",
        evidence_refs=(main_ref, other_ref),
        retrieval_signals=(),
        relationship_status=None,
        rank=1,
        warnings=(),
    )
    return replace(
        make_pack(),
        current_state=(item,),
        evidence=(main_evidence, other_evidence),
        warnings=(
            ContextPackWarning(
                code="other_vault_stale",
                severity="warning",
                message="Other vault evidence is stale",
                affected_vault_ids=("other",),
                evidence_refs=(other_ref,),
            ),
        ),
    )


def make_related_response() -> RelatedResponse:
    source = make_entity("main")
    target = make_entity("main", name="Search")
    relationship = make_relationship(source, target)
    item = RelatedItem(
        rank=1,
        entity=target,
        relationship_path=(relationship,),
        evidence=(make_metadata_evidence_from_graph_ref(relationship.evidence_refs[0]),),
        score=0.9,
        explanation="GraphRAG depends_on Search",
    )
    return RelatedResponse(
        target="GraphRAG",
        resolved_target=source,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        projection_build_id="projection-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=1,
        items=(item,),
        warnings=(),
        store_revisions=(
            GraphRetrievalRevision(kind="graph", revision="graph-1", scope_key="main:wiki:local", vault_id="main"),
        ),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def make_decision_trace_response() -> DecisionTraceResponse:
    entity = make_entity("main", name="Phase 5")
    step = DecisionTraceStep(
        rank=1,
        role="decision",
        entity=entity,
        relationship_path=(),
        evidence=(make_metadata_evidence_from_graph_ref(entity.evidence_refs[0]),),
        relationship_status="not_applicable",
        explanation="resolved decision",
    )
    return DecisionTraceResponse(
        topic="Phase 5",
        trace_kind="decision",
        resolved_target=entity,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        projection_build_id=None,
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        steps=(step,),
        warnings=(),
        store_revisions=(
            GraphRetrievalRevision(kind="graph", revision="graph-1", scope_key="main:wiki:local", vault_id="main"),
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


def test_status_report_payload_includes_vector_and_graph_run_timestamps() -> None:
    from tests.test_mcp_tools import make_status_report

    payload = status_report_to_payload(
        make_status_report(),
        selected_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
    )
    vector = cast(dict[str, object], payload["vector"])
    graph = cast(dict[str, object], payload["graph"])

    assert vector["last_success_at"] == "2026-06-18T01:00:00+00:00"
    assert vector["last_error_at"] is None
    assert graph["last_success_revision"] == "graph-1"
    assert graph["last_success_at"] == "2026-06-18T02:00:00+00:00"
    assert graph["last_error_at"] is None


def test_status_payload_accepts_compact_health_explorer_section() -> None:
    from tests.test_mcp_tools import make_status_report

    payload = status_report_to_payload(
        make_status_report(),
        selected_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        health_explorer={
            "backends": [],
            "runtime_caches": [],
            "scale_up_adapters": [],
            "warnings": [],
            "generated_at": "now",
        },
    )

    health = cast(dict[str, object], payload["health_explorer"])
    assert health["backends"] == []


def test_context_pack_payload_matches_canonical_context_pack_dict() -> None:
    pack = replace(make_pack(), pack_id="pack-1")

    assert context_pack_to_payload(pack) == context_pack_to_dict(pack)


def test_search_resource_links_use_phase_5b_uri_encoding() -> None:
    response = make_search_response(path="wiki/decisions/phase 5.md")

    links = resource_links_for_search(response)

    assert ("evidence", "vault://main/documents/wiki%2Fdecisions%2Fphase%205.md") in {
        (link.rel, link.uri) for link in links
    }
    assert ("page", "vault://main/pages/wiki%2Fdecisions%2Fphase%205.md") in {(link.rel, link.uri) for link in links}


def test_search_explanation_records_preserve_result_evidence_signals_and_revisions() -> None:
    record = explanation_records_for_search(make_search_response())[0]

    assert record.result_id == "main:chunk-1"
    assert record.source_kind == "search_result"
    assert record.evidence[0].document_id == "main:document"
    assert record.signals[0].kind == "keyword"
    assert {revision["kind"] for revision in record.store_revisions} == {"metadata", "vector"}
    assert any(link["uri"] == "vault://main/documents/wiki%2Fpage.md" for link in record.resource_links)


def test_context_pack_explanation_records_use_item_id_as_result_id() -> None:
    record = explanation_records_for_context_pack(make_pack_with_item())[0]

    assert record.result_id == "item-1"
    assert record.source_kind == "context_pack_item"
    assert record.title == "Current state"
    assert record.evidence[0].chunk_id == "chunk-1"
    assert record.signals[0].kind == "keyword"
    assert record.relationship_status == "not_applicable"


def test_related_payload_includes_result_id() -> None:
    response = make_related_response()
    payload = related_response_to_payload(response)
    item = cast(list[dict[str, object]], payload["items"])[0]

    result_id = cast(str, item["result_id"])
    assert result_id.startswith("related:")
    assert result_id.count(":") == 1
    assert len(result_id) <= 40


def test_related_explanation_records_preserve_graph_evidence_and_relationship_status() -> None:
    response = make_related_response()
    record = explanation_records_for_related(response)[0]

    assert record.result_id.startswith("related:")
    assert record.source_kind == "related_item"
    assert record.summary == "GraphRAG depends_on Search"
    assert record.relationship_status == "stated"
    assert record.signals[0].kind == "graph"
    assert record.store_revisions[0]["revision"] == "graph-1"


def test_decision_trace_payload_includes_result_id() -> None:
    response = make_decision_trace_response()
    payload = decision_trace_response_to_payload(response)
    step = cast(list[dict[str, object]], payload["steps"])[0]

    result_id = cast(str, step["result_id"])
    assert result_id.startswith("decision_trace:")
    assert result_id.count(":") == 1
    assert len(result_id) <= 48


def test_graph_result_ids_are_fixed_length_for_unbounded_user_input() -> None:
    related = replace(make_related_response(), target="GraphRAG:" + ("x" * 512))
    decision_trace = replace(make_decision_trace_response(), topic="Phase 5:" + ("x" * 512))

    related_id = cast(str, cast(list[dict[str, object]], related_response_to_payload(related)["items"])[0]["result_id"])
    trace_id = cast(
        str,
        cast(list[dict[str, object]], decision_trace_response_to_payload(decision_trace)["steps"])[0]["result_id"],
    )

    assert related_id.startswith("related:")
    assert trace_id.startswith("decision_trace:")
    assert related_id.count(":") == 1
    assert trace_id.count(":") == 1
    assert len(related_id) <= 40
    assert len(trace_id) <= 48


def test_context_pack_explanation_records_preserve_warnings_for_later_vault_evidence() -> None:
    record = explanation_records_for_context_pack(make_multi_vault_pack_with_warning())[0]

    assert tuple(warning.code for warning in record.warnings) == ("other_vault_stale",)


def test_decision_trace_explanation_records_preserve_step_evidence() -> None:
    response = make_decision_trace_response()
    record = explanation_records_for_decision_trace(response)[0]

    assert record.source_kind == "decision_trace_step"
    assert record.title == "decision: Phase 5"
    assert record.relationship_status == "not_applicable"
    assert record.evidence[0].vault_id == "main"
    assert record.signals[0].explanation == "resolved decision"


def test_explanation_payload_resource_links_round_trip() -> None:
    record = explanation_records_for_search(make_search_response())[0]
    payload: dict[str, object] = {
        "resource_links": list(record.resource_links),
    }

    links = explanation_payload_to_resource_links(payload)

    assert [(link.rel, link.uri) for link in links] == [
        ("evidence", "vault://main/documents/wiki%2Fpage.md"),
        ("page", "vault://main/pages/wiki%2Fpage.md"),
    ]


def test_tool_serialization_does_not_import_cli_helpers() -> None:
    source = Path("src/vault_graph/mcp/mcp_tool_serialization.py").read_text(encoding="utf-8")

    assert "vault_graph.cli" not in source
