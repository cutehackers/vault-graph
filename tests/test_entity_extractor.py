from vault_graph.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.extraction.graph_source_store import GraphExtractionContext, PreviewGraphSourceStore
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope


def document(
    path: str,
    *,
    vault_id: str = "default",
    document_id: str | None = None,
    frontmatter: dict[str, object] | None = None,
) -> DocumentSnapshot:
    return DocumentSnapshot(
        vault_id=vault_id,
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
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "raw", "docs")),
        current_documents=documents,
        source_store=PreviewGraphSourceStore(chunks=chunks, documents=documents),
    )


def extract(doc: DocumentSnapshot, source_chunk: ChunkSnapshot, *documents: DocumentSnapshot) -> tuple[str, ...]:
    all_documents = (doc, *documents)
    all_chunks = (source_chunk,)
    occurrences = DeterministicEntityExtractor().extract(
        chunk=source_chunk,
        document=doc,
        context=context_for(all_documents, all_chunks),
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki", "raw", "docs")),
        spec=current_graph_extraction_spec(),
    )
    return tuple(
        f"{occurrence.entity_type}:{occurrence.name}:{occurrence.extraction_method}"
        for occurrence in occurrences
    )


def test_document_entity_type_follows_path_and_decision_frontmatter() -> None:
    wiki_doc = document("wiki/page.md", frontmatter={"title": "Wiki Page"})
    raw_doc = document("raw/source.md")
    decision_doc = document("docs/notes/choice.md", frontmatter={"type": "decision", "title": "Choose Graph"})

    assert "WikiPage:Wiki Page:document-identity-v1" in extract(wiki_doc, chunk(wiki_doc, section="Wiki Page"))
    assert "Source:source:document-identity-v1" in extract(raw_doc, chunk(raw_doc, section=None))
    assert "Decision:Choose Graph:document-identity-v1" in extract(
        decision_doc,
        chunk(decision_doc, section="Choice"),
    )


def test_heading_concept_skips_generic_heading() -> None:
    doc = document("wiki/page.md")

    names = extract(doc, chunk(doc, section="Overview"))

    assert "Concept:Overview:heading-concept-v1" not in names


def test_frontmatter_tags_create_concepts_with_stripped_hash() -> None:
    doc = document("wiki/page.md", frontmatter={"tags": ["#GraphRAG", " context "]})

    names = extract(doc, chunk(doc))

    assert "Concept:GraphRAG:frontmatter-tag-concept-v1" in names
    assert "Concept:context:frontmatter-tag-concept-v1" in names


def test_resolvable_wiki_link_creates_target_document_entity() -> None:
    source = document("wiki/source.md")
    target = document("wiki/target.md", frontmatter={"title": "Target Page"})
    source_chunk = chunk(source, text="See [[target]].")

    names = extract(source, source_chunk, target)

    assert "WikiPage:Target Page:local-link-target-document-v1" in names


def test_unresolved_wiki_link_creates_concept_entity() -> None:
    source = document("wiki/source.md")
    source_chunk = chunk(source, text="See [[Missing Page|Missing]].")

    names = extract(source, source_chunk)

    assert "Concept:Missing:unresolved-local-link-concept-v1" in names


def test_frontmatter_relationship_targets_create_document_entities_through_context() -> None:
    source = document("wiki/source.md", frontmatter={"depends_on": "target"})
    target = document("wiki/target.md", frontmatter={"title": "Target Page"})
    source_chunk = chunk(source)

    names = extract(source, source_chunk, target)

    assert "WikiPage:Target Page:frontmatter-depends-on-target-v1" in names


def test_frontmatter_revisit_when_creates_concept_entity() -> None:
    source = document("wiki/source.md", frontmatter={"revisit_when": "Search ranking changes"})
    source_chunk = chunk(source)

    names = extract(source, source_chunk)

    assert "Concept:Search ranking changes:frontmatter-revisit-when-concept-v1" in names
