from dataclasses import FrozenInstanceError

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec
from vault_graph.errors import CatalogError, VectorStoreError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorHit,
    VectorManifestRecord,
    VectorQuery,
    VectorTombstone,
)

SPEC = EmbeddingModelSpec(
    model_name="deterministic",
    model_version="test",
    dimensions=4,
    spec_version="embedding-spec-v1",
)

SECOND_SPEC = EmbeddingModelSpec(
    model_name="deterministic",
    model_version="test-v2",
    dimensions=4,
    spec_version="embedding-spec-v2",
)


def make_record(
    *,
    vault_id: str,
    path: str,
    text: str,
    content_scope: str,
    model_spec: EmbeddingModelSpec = SPEC,
) -> VectorEmbeddingRecord:
    embeddings = DeterministicTextEmbeddings(model_spec)
    embedding = embeddings.embed((EmbeddingInput(input_id=f"{vault_id}:{path}", text=text),))[0]
    chunk_id = f"{path}:chunk"
    return VectorEmbeddingRecord(
        vector_id=make_vector_id(vault_id=vault_id, chunk_id=chunk_id, model_spec=model_spec),
        vault_id=vault_id,
        document_id=f"{path}:document",
        chunk_id=chunk_id,
        content_scope=content_scope,
        embedding=embedding,
        metadata_index_revision="metadata-1",
        vector_index_revision="vector-1",
    )


def make_query(*, text: str, scope: QueryScope, limit: int = 10) -> VectorQuery:
    embeddings = DeterministicTextEmbeddings(SPEC)
    query_vector = embeddings.embed((EmbeddingInput(input_id="query", text=text),))[0]
    return VectorQuery(query_vector=query_vector, scope=scope, limit=limit, embedding_spec=SPEC)


def make_vector_id(*, vault_id: str, chunk_id: str, model_spec: EmbeddingModelSpec) -> str:
    spec_key = "|".join(
        (
            model_spec.model_name,
            model_spec.model_version,
            str(model_spec.dimensions),
            model_spec.spec_version,
        )
    )
    return f"{vault_id}:{chunk_id}:{spec_key}:vector"


def test_search_returns_scoped_semantic_candidates() -> None:
    store = InMemoryVectorStore()
    expected = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    other = make_record(vault_id="other", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(expected, other), tombstones=())

    hits = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))

    assert tuple(hit.vault_id for hit in hits) == ("default",)
    assert hits[0].document_id == expected.document_id
    assert hits[0].chunk_id == expected.chunk_id
    assert hits[0].content_scope == "wiki"
    assert hits[0].rank == 1
    assert hits[0].backend == "memory-vector"


def test_search_filters_vault_and_content_scope_before_limit() -> None:
    store = InMemoryVectorStore()
    raw = make_record(vault_id="default", path="raw/source.md", text="exact query", content_scope="raw")
    wiki = make_record(vault_id="default", path="wiki/page.md", text="different text", content_scope="wiki")
    other_vault = make_record(vault_id="other", path="wiki/page.md", text="exact query", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(raw, wiki, other_vault), tombstones=())

    hits = store.search(
        make_query(
            text="exact query",
            scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            limit=1,
        )
    )

    assert tuple((hit.vault_id, hit.chunk_id) for hit in hits) == (("default", wiki.chunk_id),)


def test_content_scope_filter_uses_same_or_child_semantics() -> None:
    store = InMemoryVectorStore()
    broad = make_record(vault_id="default", path="wiki/index.md", text="broad", content_scope="wiki")
    child = make_record(vault_id="default", path="wiki/systems/vault.md", text="child", content_scope="wiki/systems")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(broad, child), tombstones=())

    broad_hits = store.search(
        make_query(text="child", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    )
    narrow_hits = store.search(
        make_query(text="broad", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)))
    )

    assert {hit.content_scope for hit in broad_hits} == {"wiki", "wiki/systems"}
    assert tuple(hit.content_scope for hit in narrow_hits) == ("wiki/systems",)


def test_include_cross_vault_does_not_expand_vector_scope() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/page.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/page.md", text="same", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True),
        )
    )

    assert tuple(hit.vault_id for hit in hits) == ("first",)


def test_same_relative_path_in_different_vaults_does_not_collide() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/same.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/same.md", text="same", content_scope="wiki")
    assert first.chunk_id == second.chunk_id
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        )
    )

    assert sorted((hit.vault_id, hit.chunk_id) for hit in hits) == [
        ("first", first.chunk_id),
        ("second", second.chunk_id),
    ]


def test_vector_id_is_stable_for_vault_chunk_and_model_spec() -> None:
    first = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    second = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )

    assert first.chunk_id == second.chunk_id
    assert first.vector_id == make_vector_id(vault_id=first.vault_id, chunk_id=first.chunk_id, model_spec=SPEC)
    assert second.vector_id == make_vector_id(
        vault_id=second.vault_id,
        chunk_id=second.chunk_id,
        model_spec=SECOND_SPEC,
    )
    assert first.vector_id != second.vector_id


def test_tombstone_removes_only_named_vault_and_chunk() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="first", path="wiki/same.md", text="same", content_scope="wiki")
    second = make_record(vault_id="second", path="wiki/same.md", text="same", content_scope="wiki")
    assert first.chunk_id == second.chunk_id
    store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(VectorTombstone(vault_id="first", chunk_id=first.chunk_id),),
    )

    hits = store.search(
        make_query(
            text="same",
            scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        )
    )

    assert tuple((hit.vault_id, hit.chunk_id) for hit in hits) == (("second", second.chunk_id),)


def test_store_rejects_records_from_multiple_model_specs() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    second = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )

    with pytest.raises(VectorStoreError, match="embedding model spec mismatch"):
        store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())


def test_failed_mixed_model_revision_does_not_pin_empty_store_spec() -> None:
    store = InMemoryVectorStore()
    first = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    second = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )

    with pytest.raises(VectorStoreError, match="embedding model spec mismatch"):
        store.apply_vector_revision(vector_index_revision="vector-1", records=(first, second), tombstones=())

    store.apply_vector_revision(vector_index_revision="vector-1", records=(second,), tombstones=())

    hits = store.search(
        VectorQuery(
            query_vector=second.embedding,
            scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            limit=10,
            embedding_spec=SECOND_SPEC,
        )
    )
    assert tuple(hit.vector_id for hit in hits) == (second.vector_id,)


def test_search_rejects_query_embedding_spec_mismatch() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    incompatible_spec = EmbeddingModelSpec(
        model_name="deterministic",
        model_version="other",
        dimensions=4,
        spec_version="embedding-spec-v1",
    )
    embeddings = DeterministicTextEmbeddings(incompatible_spec)
    query_vector = embeddings.embed((EmbeddingInput(input_id="query", text="alpha"),))[0]

    with pytest.raises(VectorStoreError, match="embedding model spec mismatch"):
        store.search(
            VectorQuery(
                query_vector=query_vector,
                scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
                limit=10,
                embedding_spec=incompatible_spec,
            )
        )


def test_vector_query_rejects_query_vector_model_spec_mismatch() -> None:
    query_vector = DeterministicTextEmbeddings(SECOND_SPEC).embed((EmbeddingInput(input_id="query", text="alpha"),))[0]

    with pytest.raises(VectorStoreError, match="query vector model spec must match embedding_spec"):
        VectorQuery(
            query_vector=query_vector,
            scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            limit=10,
            embedding_spec=SPEC,
        )


def test_vector_embedding_record_validates_content_scope_with_query_scope_vocabulary() -> None:
    with pytest.raises(VectorStoreError, match="unsupported content scope") as exc_info:
        make_record(vault_id="default", path="private/page.md", text="alpha", content_scope="private")

    assert isinstance(exc_info.value.__cause__, CatalogError)


def test_vector_records_validate_required_strings_and_positive_numbers() -> None:
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")

    with pytest.raises(VectorStoreError, match="vector_id is required"):
        VectorEmbeddingRecord(
            vector_id="",
            vault_id=record.vault_id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            content_scope=record.content_scope,
            embedding=record.embedding,
            metadata_index_revision=record.metadata_index_revision,
            vector_index_revision=record.vector_index_revision,
        )
    with pytest.raises(VectorStoreError, match="chunk_id is required"):
        VectorTombstone(vault_id="default", chunk_id="")
    with pytest.raises(VectorStoreError, match="limit must be positive"):
        make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=0)
    with pytest.raises(VectorStoreError, match="rank must be positive"):
        VectorHit(
            vector_id=record.vector_id,
            vault_id=record.vault_id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            content_scope=record.content_scope,
            score=1.0,
            rank=0,
            embedding_spec=record.embedding.model_spec,
            metadata_index_revision=record.metadata_index_revision,
            vector_index_revision=record.vector_index_revision,
            backend="memory-vector",
        )
    with pytest.raises(VectorStoreError, match="backend is required"):
        VectorManifestRecord(
            vector_id=record.vector_id,
            vault_id=record.vault_id,
            document_id=record.document_id,
            chunk_id=record.chunk_id,
            content_scope=record.content_scope,
            embedding_spec=record.embedding.model_spec,
            metadata_index_revision=record.metadata_index_revision,
            vector_index_revision=record.vector_index_revision,
            backend="",
        )


def test_vector_records_are_immutable() -> None:
    tombstone = VectorTombstone(vault_id="default", chunk_id="wiki/page.md:chunk")

    with pytest.raises(FrozenInstanceError):
        tombstone.__setattr__("chunk_id", "other")


def test_vector_hits_do_not_expose_user_evidence_fields() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())

    hit = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))[0]

    for field_name in ("path", "text", "title", "summary", "anchor", "evidence", "content_hash"):
        assert not hasattr(hit, field_name)


def test_manifest_and_health_are_inspectable() -> None:
    store = InMemoryVectorStore()
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    health = store.health()

    assert len(manifest) == 1
    assert manifest[0].vector_id == record.vector_id
    assert manifest[0].content_scope == "wiki"
    assert isinstance(health, StoreHealth)
    assert health.ok is True
    assert health.backend == "memory-vector"
    assert health.schema_compatible is True
