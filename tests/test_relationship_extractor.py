import pytest

from vault_graph.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.extraction.graph_occurrences import EntityOccurrence
from vault_graph.extraction.graph_source_store import GraphExtractionContext, PreviewGraphSourceStore
from vault_graph.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


def document(
    path: str,
    *,
    document_id: str | None = None,
    frontmatter: dict[str, object] | None = None,
) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id="default",
        document_id=document_id or f"doc-{path}",
        path=path,
        kind=path.split("/", 1)[0],
        frontmatter=frontmatter or {},
        frontmatter_hash="frontmatter",
        content_hash="content",
        raw_sha256="raw",
        parser_version="markdown-frontmatter-v1",
        last_seen_at="2026-06-11T00:00:00+00:00",
        last_indexed_at=None,
        vault_revision=None,
        index_revision="metadata-1",
    )


def chunk(
    doc: DocumentSnapshot,
    *,
    text: str = "Body",
    section: str | None = "Project Graph",
    anchor: str | None = "project-graph",
) -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=doc.vault_id,
        chunk_id=f"chunk-{doc.document_id}",
        document_id=doc.document_id,
        path=doc.path,
        section=section,
        anchor=anchor,
        text=text,
        token_count=len(text.split()),
        content_hash=f"hash-{doc.document_id}",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


def context_for(documents: tuple[DocumentSnapshot, ...], chunks: tuple[ChunkSnapshot, ...]) -> GraphExtractionContext:
    return GraphExtractionContext(
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "docs")),
        current_documents=documents,
        source_store=PreviewGraphSourceStore(chunks=chunks, documents=documents),
    )


def entities_for(
    doc: DocumentSnapshot,
    source_chunk: ChunkSnapshot,
    *documents: DocumentSnapshot,
) -> tuple[EntityOccurrence, ...]:
    all_documents = (doc, *documents)
    return DeterministicEntityExtractor().extract(
        chunk=source_chunk,
        document=doc,
        context=context_for(all_documents, (source_chunk,)),
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "docs")),
        spec=current_graph_extraction_spec(),
    )


def relationships_for(
    doc: DocumentSnapshot,
    source_chunk: ChunkSnapshot,
    entities: tuple[EntityOccurrence, ...],
    *documents: DocumentSnapshot,
) -> tuple[str, ...]:
    relationships = DeterministicRelationshipExtractor().extract(
        chunk=source_chunk,
        document=doc,
        entities=entities,
        context=context_for((doc, *documents), (source_chunk,)),
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "docs")),
        spec=current_graph_extraction_spec(),
    )
    return tuple(
        f"{relationship.relationship_type}:{relationship.source_entity_key[3]}:{relationship.target_entity_key[3]}"
        for relationship in relationships
    )


def test_heading_tag_and_unresolved_link_concepts_produce_mentions() -> None:
    doc = document("wiki/source.md", frontmatter={"tags": ["GraphRAG"]})
    source_chunk = chunk(doc, text="See [[Missing]].", section="Architecture")
    entities = entities_for(doc, source_chunk)

    relationships = relationships_for(doc, source_chunk, entities)

    assert any(relationship.startswith("mentions:wiki/source.md:") for relationship in relationships)
    assert sum(relationship.startswith("mentions:wiki/source.md:") for relationship in relationships) == 3


def test_resolvable_local_link_produces_links_to() -> None:
    source = document("wiki/source.md")
    target = document("wiki/target.md", frontmatter={"title": "Target Page"})
    source_chunk = chunk(source, text="See [Target](target.md).")
    entities = entities_for(source, source_chunk, target)

    relationships = relationships_for(source, source_chunk, entities, target)

    assert "links_to:wiki/source.md:wiki/target.md" in relationships


@pytest.mark.parametrize(
    ("field_name", "expected_type", "target_value"),
    (
        ("related", "related_to", "target"),
        ("depends_on", "depends_on", "target"),
        ("blocks", "blocks", "target"),
        ("implements", "implements", "target"),
        ("supersedes", "supersedes", "target"),
        ("revisit_when", "revisit_when", "Search ranking changes"),
    ),
)
def test_frontmatter_relationship_fields_use_actual_entity_extractor_output(
    field_name: str,
    expected_type: str,
    target_value: str,
) -> None:
    source = document("wiki/source.md", frontmatter={field_name: target_value})
    target = document("wiki/target.md", frontmatter={"title": "Target Page"})
    source_chunk = chunk(source)
    documents = (target,) if field_name != "revisit_when" else ()
    entities = entities_for(source, source_chunk, *documents)

    relationships = relationships_for(source, source_chunk, entities, *documents)

    expected_target_key = "wiki/target.md" if field_name != "revisit_when" else ""
    assert any(
        relationship.startswith(f"{expected_type}:wiki/source.md:{expected_target_key}")
        for relationship in relationships
    )


def test_duplicate_relationships_for_same_type_target_and_evidence_are_removed() -> None:
    doc = document("wiki/source.md")
    source_chunk = chunk(doc, section="Architecture")
    entities = entities_for(doc, source_chunk)

    relationships = DeterministicRelationshipExtractor().extract(
        chunk=source_chunk,
        document=doc,
        entities=entities + entities,
        context=context_for((doc,), (source_chunk,)),
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        spec=current_graph_extraction_spec(),
    )

    assert len(relationships) == len(
        {
            (
                relationship.relationship_type,
                relationship.source_entity_key,
                relationship.target_entity_key,
                relationship.chunk_id,
            )
            for relationship in relationships
        }
    )
