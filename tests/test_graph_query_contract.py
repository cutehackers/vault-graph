import pytest

from tests.test_graph_store_contract import make_entity, make_relationship
from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_query import (
    GraphEntityIdentity,
    GraphEntityMatch,
    GraphEntityQuery,
    GraphRelationshipQuery,
    GraphRelationshipQueryResult,
)
from vault_graph.ingestion.vault_catalog import QueryScope


def test_graph_entity_query_requires_text() -> None:
    with pytest.raises(GraphStoreError, match="graph entity query text is required"):
        GraphEntityQuery(text=" ", actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))


def test_graph_entity_query_requires_actual_scopes() -> None:
    with pytest.raises(GraphStoreError, match="actual_scopes are required"):
        GraphEntityQuery(text="GraphRAG", actual_scopes=())


def test_graph_entity_query_requires_per_vault_actual_scopes() -> None:
    with pytest.raises(GraphStoreError, match="per-Vault actual scopes"):
        GraphEntityQuery(text="GraphRAG", actual_scopes=(QueryScope(vault_ids=("a", "b"), content_scopes=("wiki",)),))


def test_graph_relationship_query_requires_seed() -> None:
    with pytest.raises(GraphStoreError, match="seeds are required"):
        GraphRelationshipQuery(
            seeds=(),
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
        )


def test_graph_entity_match_keeps_match_metadata() -> None:
    entity = make_entity("default", name="GraphRAG")
    match = GraphEntityMatch(entity=entity, match_kind="normalized_name", match_rank=1, matched_value="graphrag")

    assert match.entity == entity
    assert match.match_kind == "normalized_name"
    assert match.match_rank == 1


def test_graph_relationship_query_accepts_cross_vault_flag() -> None:
    query = GraphRelationshipQuery(
        seeds=(GraphEntityIdentity("default", "entity-1"),),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",), include_cross_vault=True),),
        include_cross_vault=True,
    )

    assert query.direction == "both"
    assert query.statuses == ("stated", "inferred", "contested")


def test_graph_entity_query_rejects_unbounded_scan_limit() -> None:
    with pytest.raises(GraphStoreError, match="scan_limit is out of range"):
        GraphEntityQuery(
            text="GraphRAG",
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
            scan_limit=5001,
        )


def test_graph_relationship_query_rejects_unbounded_read_limit() -> None:
    with pytest.raises(GraphStoreError, match="limit is out of range"):
        GraphRelationshipQuery(
            seeds=(GraphEntityIdentity("default", "entity-1"),),
            actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
            limit=201,
        )


def test_graph_relationship_query_result_rejects_negative_cross_vault_count() -> None:
    with pytest.raises(GraphStoreError, match="omitted_cross_vault_count must not be negative"):
        GraphRelationshipQueryResult(
            relationships=(),
            truncated=False,
            omitted_cross_vault_count=-1,
            affected_vault_ids=(),
        )


def test_graph_relationship_query_result_requires_immutable_relationships() -> None:
    source = make_entity("default", name="GraphRAG")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)

    with pytest.raises(GraphStoreError, match="relationships must be an immutable tuple"):
        GraphRelationshipQueryResult(
            relationships=[relationship],  # type: ignore[arg-type]
            truncated=False,
            omitted_cross_vault_count=0,
            affected_vault_ids=("default",),
        )
