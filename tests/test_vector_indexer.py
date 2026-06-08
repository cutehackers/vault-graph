from dataclasses import replace

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from vault_graph.embeddings.text_embeddings import EmbeddingModelSpec
from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.ingestion.document_normalizer import ChunkSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope

SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v1", dimensions=4, spec_version="spec-v1")
SECOND_SPEC = EmbeddingModelSpec(model_name="deterministic", model_version="v2", dimensions=4, spec_version="spec-v2")


class ChunkStore:
    def __init__(self, chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.chunks = chunks

    def list_chunks(self, scope: QueryScope) -> tuple[ChunkSnapshot, ...]:
        return tuple(
            chunk
            for chunk in self.chunks
            if chunk.vault_id in scope.vault_ids
            and any(
                chunk.path == content_scope or chunk.path.startswith(f"{content_scope}/")
                for content_scope in scope.content_scopes
            )
        )


def chunk(vault_id: str = "default", path: str = "wiki/page.md", text: str = "alpha") -> ChunkSnapshot:
    return ChunkSnapshot(
        vault_id=vault_id,
        chunk_id=f"{vault_id}:{path}:chunk",
        document_id=f"{vault_id}:{path}:document",
        path=path,
        section="Page",
        anchor="page",
        text=text,
        token_count=len(text.split()),
        content_hash=f"hash:{text}",
        chunker_version="heading-section-v1",
        index_revision="metadata-1",
    )


def test_plan_marks_new_chunks_for_upsert() -> None:
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=InMemoryVectorStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    plan = indexer.plan(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert plan.upsert_count == 1
    assert plan.tombstone_count == 0
    assert plan.unchanged_count == 0
    assert plan.embedding_count == 1


def test_apply_embeds_upserts_and_records_manifest() -> None:
    vector_store = InMemoryVectorStore()
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    manifest = vector_store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    assert result.upsert_count == 1
    assert result.tombstone_count == 0
    assert result.failed is False
    assert manifest[0].source_chunk_hash == "hash:alpha"
    assert manifest[0].metadata_index_revision == "metadata-1"


def test_changed_chunk_hash_replaces_existing_vector() -> None:
    vector_store = InMemoryVectorStore()
    first = chunk(text="alpha")
    VectorIndexer(
        chunk_store=ChunkStore((first,)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    second = replace(first, text="beta", content_hash="hash:beta")
    indexer = VectorIndexer(
        chunk_store=ChunkStore((second,)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    plan = indexer.plan(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert plan.upsert_count == 1
    assert plan.tombstone_count == 1
    assert result.upsert_count == 1


def test_model_spec_change_tombstones_old_model_row() -> None:
    vector_store = InMemoryVectorStore()
    VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SECOND_SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))
    manifest = vector_store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert result.upsert_count == 1
    assert result.tombstone_count == 1
    assert tuple(row.embedding_spec for row in manifest) == (SECOND_SPEC,)


def test_narrow_scope_does_not_tombstone_other_vault() -> None:
    vector_store = InMemoryVectorStore()
    chunks = (chunk(vault_id="first"), chunk(vault_id="second"))
    VectorIndexer(
        chunk_store=ChunkStore(chunks),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),))
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(vault_id="second"),)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("second",), content_scopes=("wiki",)),))
    manifest = vector_store.export_manifest(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)))

    assert result.tombstone_count == 0
    assert sorted(row.vault_id for row in manifest) == ["first", "second"]


def test_same_chunk_id_in_different_vaults_embeds_without_collision() -> None:
    shared_chunk_id = "wiki/page.md:chunk"
    first = replace(chunk(vault_id="first", text="first"), chunk_id=shared_chunk_id)
    second = replace(chunk(vault_id="second", text="second"), chunk_id=shared_chunk_id)
    vector_store = InMemoryVectorStore()

    result = VectorIndexer(
        chunk_store=ChunkStore((first, second)),
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    ).apply(scopes=(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),))

    manifest = vector_store.export_manifest(QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)))
    assert result.failed is False
    assert sorted((row.vault_id, row.chunk_id) for row in manifest) == [
        ("first", shared_chunk_id),
        ("second", shared_chunk_id),
    ]
