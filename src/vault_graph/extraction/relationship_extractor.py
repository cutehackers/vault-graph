from __future__ import annotations

from typing import Protocol

from vault_graph.extraction.graph_occurrences import EntityOccurrence, RelationshipOccurrence, entity_occurrence_key
from vault_graph.extraction.graph_source_store import GraphExtractionContext
from vault_graph.graph.graph_contracts import GraphExtractionSpec
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope

MENTION_METHOD_CONFIDENCE = {
    "heading-concept-v1": 0.85,
    "frontmatter-tag-concept-v1": 0.8,
    "unresolved-local-link-concept-v1": 0.7,
}
RELATIONSHIP_METHOD_RULES = {
    "local-link-target-document-v1": ("links_to", 0.95),
    "frontmatter-related-target-v1": ("related_to", 0.9),
    "frontmatter-depends-on-target-v1": ("depends_on", 0.9),
    "frontmatter-blocks-target-v1": ("blocks", 0.9),
    "frontmatter-implements-target-v1": ("implements", 0.9),
    "frontmatter-supersedes-target-v1": ("supersedes", 0.9),
    "frontmatter-revisit-when-concept-v1": ("revisit_when", 0.8),
}


class RelationshipExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        entities: tuple[EntityOccurrence, ...],
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[RelationshipOccurrence, ...]: ...


class DeterministicRelationshipExtractor:
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        entities: tuple[EntityOccurrence, ...],
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[RelationshipOccurrence, ...]:
        if document is None:
            return ()
        document_entity = _document_entity(document=document, entities=entities)
        if document_entity is None:
            return ()
        relationships: list[RelationshipOccurrence] = []
        relationships.extend(_mention_relationships(chunk=chunk, source=document_entity, entities=entities))
        relationships.extend(_typed_relationships(chunk=chunk, source=document_entity, entities=entities))
        return tuple(_dedupe_relationships(relationships))


def _document_entity(
    *,
    document: DocumentSnapshot,
    entities: tuple[EntityOccurrence, ...],
) -> EntityOccurrence | None:
    for entity in entities:
        if entity.extraction_method == "document-identity-v1" and entity.canonical_path == document.path:
            return entity
    return None


def _mention_relationships(
    *,
    chunk: ChunkSnapshot,
    source: EntityOccurrence,
    entities: tuple[EntityOccurrence, ...],
) -> tuple[RelationshipOccurrence, ...]:
    return tuple(
        _relationship(
            chunk=chunk,
            source=source,
            target=target,
            relationship_type="mentions",
            confidence=MENTION_METHOD_CONFIDENCE[target.extraction_method],
            extraction_method=f"{target.extraction_method}-relationship-v1",
        )
        for target in entities
        if target.entity_type == "Concept" and target.extraction_method in MENTION_METHOD_CONFIDENCE
    )


def _typed_relationships(
    *,
    chunk: ChunkSnapshot,
    source: EntityOccurrence,
    entities: tuple[EntityOccurrence, ...],
) -> tuple[RelationshipOccurrence, ...]:
    relationships: list[RelationshipOccurrence] = []
    for target in entities:
        rule = RELATIONSHIP_METHOD_RULES.get(target.extraction_method)
        if rule is None:
            continue
        relationship_type, confidence = rule
        relationships.append(
            _relationship(
                chunk=chunk,
                source=source,
                target=target,
                relationship_type=relationship_type,
                confidence=confidence,
                extraction_method=f"{target.extraction_method}-relationship-v1",
            )
        )
    return tuple(relationships)


def _relationship(
    *,
    chunk: ChunkSnapshot,
    source: EntityOccurrence,
    target: EntityOccurrence,
    relationship_type: str,
    confidence: float,
    extraction_method: str,
) -> RelationshipOccurrence:
    return RelationshipOccurrence(
        relationship_type=relationship_type,
        source_vault_id=source.vault_id,
        source_entity_key=entity_occurrence_key(source),
        target_vault_id=target.vault_id,
        target_entity_key=entity_occurrence_key(target),
        evidence_vault_id=chunk.vault_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        content_hash=chunk.content_hash,
        section=chunk.section,
        anchor=chunk.anchor,
        path=chunk.path,
        excerpt=_excerpt(chunk.text),
        status="stated",
        confidence=confidence,
        extraction_method=extraction_method,
    )


def _dedupe_relationships(relationships: list[RelationshipOccurrence]) -> tuple[RelationshipOccurrence, ...]:
    deduped: dict[
        tuple[str, tuple[str, str, str, str], tuple[str, str, str, str], str],
        RelationshipOccurrence,
    ] = {}
    for relationship in relationships:
        key = (
            relationship.relationship_type,
            relationship.source_entity_key,
            relationship.target_entity_key,
            relationship.chunk_id,
        )
        deduped.setdefault(key, relationship)
    return tuple(
        sorted(
            deduped.values(),
            key=lambda item: (
                item.source_vault_id,
                item.relationship_type,
                item.source_entity_key,
                item.target_entity_key,
            ),
        )
    )


def _excerpt(text: str) -> str | None:
    stripped = " ".join(text.split())
    return stripped[:240] if stripped else None
