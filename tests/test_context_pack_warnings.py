from __future__ import annotations

import pytest

from vault_graph.context import (
    GRAPH_WARNING_CODE_MAP,
    SEARCH_WARNING_CODE_MAP,
    budget_warning,
    builder_warning,
    context_warning_from_graph,
    context_warning_from_retrieval,
    context_warning_from_search,
)
from vault_graph.retrieval.graph_retrieval import GraphRetrievalWarning
from vault_graph.retrieval.retrieval_result import RetrievalWarning
from vault_graph.retrieval.search_response import SearchWarning


def test_vector_query_failed_becomes_search_degraded_with_source_code() -> None:
    warning = context_warning_from_search(
        SearchWarning(
            code="vector_query_failed",
            message="Vector failed",
            severity="warning",
            affected_vault_ids=("main",),
        )
    )

    assert warning.code == "search_degraded"
    assert warning.source_code == "vector_query_failed"
    assert warning.source_kind == "retrieval"
    assert warning.affected_vault_ids == ("main",)


def test_unknown_graph_warning_preserves_identity() -> None:
    warning = context_warning_from_graph(
        GraphRetrievalWarning(
            code="new_graph_warning",
            message="New warning",
            severity="warning",
            affected_vault_ids=("main",),
        )
    )

    assert warning.code == "new_graph_warning"
    assert warning.source_code == "new_graph_warning"
    assert warning.source_kind == "graph"


@pytest.mark.parametrize(("source_code", "context_code"), sorted(GRAPH_WARNING_CODE_MAP.items()))
def test_graph_warning_mapping_preserves_source_identity(source_code: str, context_code: str) -> None:
    warning = context_warning_from_graph(
        GraphRetrievalWarning(
            code=source_code,
            message="Graph warning",
            severity="warning",
            affected_vault_ids=("main",),
            scope_key="main:wiki:cross",
            entity_id="entity-1",
            relationship_id="relationship-1",
            evidence_ref_id="evidence-1",
        )
    )

    assert warning.code == context_code
    assert warning.source_code == source_code
    assert warning.source_kind == "graph"
    assert warning.scope_key == "main:wiki:cross"
    assert warning.entity_id == "entity-1"
    assert warning.relationship_id == "relationship-1"
    assert warning.evidence_ref_id == "evidence-1"


@pytest.mark.parametrize(("source_code", "context_code"), sorted(SEARCH_WARNING_CODE_MAP.items()))
def test_search_warning_mapping_preserves_source_identity(source_code: str, context_code: str) -> None:
    warning = context_warning_from_search(
        SearchWarning(
            code=source_code,
            message="Search warning",
            severity="warning",
            affected_vault_ids=("main",),
            scope_key="main:wiki:local",
        )
    )

    assert warning.code == context_code
    assert warning.source_code == source_code
    assert warning.source_kind == "retrieval"
    assert warning.scope_key == "main:wiki:local"
    assert warning.affected_vault_ids == ("main",)


def test_single_vault_search_warning_with_document_and_chunk_gets_evidence_ref() -> None:
    warning = context_warning_from_search(
        SearchWarning(
            code="missing_evidence",
            message="Missing",
            severity="warning",
            affected_vault_ids=("main",),
            document_id="doc-1",
            chunk_id="chunk-1",
        )
    )

    assert [(ref.vault_id, ref.document_id, ref.chunk_id) for ref in warning.evidence_refs] == [
        ("main", "doc-1", "chunk-1")
    ]


def test_multi_vault_search_warning_does_not_guess_evidence_ref() -> None:
    warning = context_warning_from_search(
        SearchWarning(
            code="missing_evidence",
            message="Missing",
            severity="warning",
            affected_vault_ids=("first", "second"),
            document_id="doc-1",
            chunk_id="chunk-1",
        )
    )

    assert warning.affected_vault_ids == ("first", "second")
    assert warning.evidence_refs == ()


def test_retrieval_warning_uses_fallback_vault_id_and_item_evidence() -> None:
    warning = context_warning_from_retrieval(
        RetrievalWarning(code="stale_vector", message="Stale", severity="warning"),
        fallback_vault_id="main",
    )

    assert warning.code == "stale_projection"
    assert warning.source_code == "stale_vector"
    assert warning.affected_vault_ids == ("main",)
    assert warning.source_kind == "retrieval"


def test_budget_and_builder_warnings_set_source_kinds() -> None:
    budget = budget_warning(code="budget_omitted", message="omitted", affected_vault_ids=("main",))
    builder = builder_warning(
        code="missing_evidence",
        message="missing",
        affected_vault_ids=("main",),
        recovery_hint="Run `vg index`.",
    )

    assert budget.source_kind == "budget"
    assert builder.source_kind == "builder"
    assert builder.recovery_hint == "Run `vg index`."
