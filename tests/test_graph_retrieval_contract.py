import pytest

from tests.test_graph_store_contract import make_entity, make_relationship
from vault_graph.errors import SearchError
from vault_graph.graph.graph_contracts import GraphEvidenceRef
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceStep,
    GraphRetrievalWarning,
    RelatedItem,
    RelatedResponse,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


def make_metadata_evidence_from_graph_ref(ref: GraphEvidenceRef) -> EvidenceReference:
    return EvidenceReference(
        vault_id=ref.evidence_vault_id,
        document_id=ref.document_id,
        chunk_id=ref.chunk_id,
        path=ref.path or "wiki/page.md",
        section=ref.section,
        anchor=ref.anchor,
        content_hash=ref.content_hash,
        raw_sha256=f"{ref.content_hash}-raw",
        metadata_index_revision="metadata-1",
        vault_revision=None,
    )


def test_graph_warning_requires_vault_attribution() -> None:
    with pytest.raises(SearchError, match="affected_vault_ids"):
        GraphRetrievalWarning(code="graph_stale", message="stale", severity="warning", affected_vault_ids=())


def test_related_item_requires_rank_relationship_path_and_evidence() -> None:
    source = make_entity("default")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    evidence = make_metadata_evidence_from_graph_ref(relationship.evidence_refs[0])

    with pytest.raises(SearchError, match="related item rank must be positive"):
        RelatedItem(
            rank=0,
            entity=target,
            relationship_path=(relationship,),
            evidence=(evidence,),
            score=0.9,
            explanation="GraphRAG related_to Search",
        )
    with pytest.raises(SearchError, match="relationship_path is required"):
        RelatedItem(
            rank=1,
            entity=target,
            relationship_path=(),
            evidence=(evidence,),
            score=0.9,
            explanation="GraphRAG related_to Search",
        )
    with pytest.raises(SearchError, match="relationship evidence is required"):
        RelatedItem(
            rank=1,
            entity=target,
            relationship_path=(relationship,),
            evidence=(),
            score=0.9,
            explanation="GraphRAG related_to Search",
        )


def test_related_response_counts_items() -> None:
    source = make_entity("default")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    evidence = relationship.evidence_refs[0]
    item = RelatedItem(
        rank=1,
        entity=target,
        relationship_path=(relationship,),
        evidence=(make_metadata_evidence_from_graph_ref(evidence),),
        score=0.9,
        explanation="GraphRAG related_to Search",
    )
    response = RelatedResponse(
        target="GraphRAG",
        resolved_target=source,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
        projection_build_id="projection-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=1,
        items=(item,),
        warnings=(),
        store_revisions=(),
        generated_at="2026-06-11T00:00:00+00:00",
    )

    assert response.result_count == 1


def test_related_response_rejects_mismatched_result_count() -> None:
    with pytest.raises(SearchError, match="result_count must match items"):
        RelatedResponse(
            target="GraphRAG",
            resolved_target=None,
            target_candidates=(),
            requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
            projection_build_id=None,
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            result_count=1,
            items=(),
            warnings=(),
            store_revisions=(),
            generated_at="2026-06-11T00:00:00+00:00",
        )


def test_decision_trace_step_allows_initial_step_with_entity_evidence() -> None:
    entity = make_entity("default")
    step = DecisionTraceStep(
        rank=1,
        role="decision",
        entity=entity,
        relationship_path=(),
        evidence=(make_metadata_evidence_from_graph_ref(entity.evidence_refs[0]),),
        relationship_status="not_applicable",
        explanation="resolved decision",
    )

    assert step.role == "decision"


def test_decision_trace_step_requires_relationship_evidence_for_non_initial_steps() -> None:
    source = make_entity("default")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)

    with pytest.raises(SearchError, match="relationship evidence is required"):
        DecisionTraceStep(
            rank=1,
            role="depends_on",
            entity=target,
            relationship_path=(relationship,),
            evidence=(),
            relationship_status="stated",
            explanation="dependency",
        )
