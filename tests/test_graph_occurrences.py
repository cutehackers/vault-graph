import pytest

from vault_graph.errors import GraphExtractionError
from vault_graph.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)


def test_entity_occurrence_key_is_vault_scoped() -> None:
    first = EntityOccurrence(
        vault_id="first",
        entity_type="Concept",
        name="GraphRAG",
        normalized_name="graphrag",
        aliases=(),
        canonical_path=None,
        evidence_vault_id="first",
        document_id="doc",
        chunk_id="chunk",
        content_hash="hash",
        section="GraphRAG",
        anchor="graphrag",
        path="wiki/page.md",
        excerpt="GraphRAG",
        confidence=0.85,
        extraction_method="heading-concept-v1",
    )
    second = EntityOccurrence(**{**first.__dict__, "vault_id": "second", "evidence_vault_id": "second"})

    assert entity_occurrence_key(first) != entity_occurrence_key(second)


def test_entity_occurrence_rejects_missing_evidence() -> None:
    with pytest.raises(GraphExtractionError, match="chunk_id is required"):
        EntityOccurrence(
            vault_id="default",
            entity_type="Concept",
            name="GraphRAG",
            normalized_name="graphrag",
            aliases=(),
            canonical_path=None,
            evidence_vault_id="default",
            document_id="doc",
            chunk_id="",
            content_hash="hash",
            section=None,
            anchor=None,
            path="wiki/page.md",
            excerpt=None,
            confidence=0.8,
            extraction_method="test",
        )


def test_relationship_occurrence_status_is_limited() -> None:
    with pytest.raises(GraphExtractionError, match="unsupported relationship status"):
        RelationshipOccurrence(
            relationship_type="depends_on",
            source_vault_id="default",
            source_entity_key=("default", "Document", "source", "wiki/source.md"),
            target_vault_id="default",
            target_entity_key=("default", "Document", "target", "wiki/target.md"),
            evidence_vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            content_hash="hash",
            section=None,
            anchor=None,
            path="wiki/source.md",
            excerpt=None,
            status="confirmed",
            confidence=0.9,
            extraction_method="test",
        )


def test_relationship_occurrence_rejects_invalid_entity_key_shape() -> None:
    with pytest.raises(GraphExtractionError, match="source_entity_key must be"):
        RelationshipOccurrence(
            relationship_type="depends_on",
            source_vault_id="default",
            source_entity_key=("default", "Document", "source"),  # type: ignore[arg-type]
            target_vault_id="default",
            target_entity_key=("default", "Document", "target", "wiki/target.md"),
            evidence_vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            content_hash="hash",
            section=None,
            anchor=None,
            path="wiki/source.md",
            excerpt=None,
            status="stated",
            confidence=0.9,
            extraction_method="test",
        )
