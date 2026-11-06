"""A-14: an embedding key decides re-embedding, a metadata fingerprint decides metadata-only updates (spec 4.3.2)."""

import hashlib
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from vector_index import IndexedItem, IndexItem, IndexPlan, plan_index

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_vector_indexer import SPEC, ChunkStore, chunk
from tests.test_vector_store_contract import make_record
from vault_graph.errors import VectorStoreError
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentNormalizer
from vault_graph.indexing.ingestion.vault_frontmatter_reader import read_frontmatter
from vault_graph.indexing.ingestion.vault_loader import LoadedVaultDocument
from vault_graph.indexing.vector_index_adapter import VectorIndexer
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.storage.interfaces.vector_manifest_store import VectorManifestRow
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorManifestRecord,
    VectorMetadataRecord,
    VectorMetadataUpdater,
)
from vault_graph.storage.local import vector_store_adapter
from vault_graph.storage.local.chroma_vector_store import COLLECTION_PREFIX, ChromaVectorStore
from vault_graph.storage.local.sqlite_vector_manifest_store import (
    ChromaSQLiteListing,
    ManifestTrackedVectorStore,
    SQLiteVectorManifestStore,
    manifest_path_for_vector_path,
)
from vault_graph.storage.local.vector_store_adapter import CHROMA_BACKEND
from vault_graph.storage.local.vector_store_adapter import ChromaVectorStore as OldChromaVectorStore

SCOPES = (QueryScope(vault_ids=("default",), content_scopes=("wiki",)),)


class CountingEmbeddings(DeterministicTextEmbeddings):
    def __init__(self) -> None:
        super().__init__(SPEC)
        self.inputs: list[EmbeddingInput] = []

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        self.inputs.extend(inputs)
        return super().embed(inputs)


def open_store(vector_path: Path) -> ManifestTrackedVectorStore:
    return ManifestTrackedVectorStore(
        ChromaVectorStore(vector_path, initialize=True),
        manifest=SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)),
        listing=ChromaSQLiteListing(vector_path, collection_prefix=COLLECTION_PREFIX, backend=CHROMA_BACKEND),
        backend=CHROMA_BACKEND,
    )


def run(vector_path: Path, chunks: tuple[ChunkSnapshot, ...]) -> tuple[int, int, int]:
    """Apply one run and return (model inputs, metadata updates, unchanged)."""
    embeddings = CountingEmbeddings()
    store = open_store(vector_path)
    try:
        result = VectorIndexer(chunk_store=ChunkStore(chunks), vector_store=store, text_embeddings=embeddings).apply(
            scopes=SCOPES
        )
    finally:
        store.close()
    assert result.failed is False, result.error
    return len(embeddings.inputs), result.metadata_update_count, result.unchanged_count


def run_without_keys(vector_path: Path, chunks: tuple[ChunkSnapshot, ...]) -> None:
    """Write as the adapter did before spec 4.3.2: no manifest table and no keys in Chroma metadata."""
    store = OldChromaVectorStore(vector_path, initialize=True)
    original = vector_store_adapter.key_metadata
    vector_store_adapter.key_metadata = lambda *_: {}  # type: ignore[assignment]
    try:
        result = VectorIndexer(
            chunk_store=ChunkStore(chunks), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
        ).apply(scopes=SCOPES)
    finally:
        vector_store_adapter.key_metadata = original
        store.close()
    assert result.failed is False, result.error
    assert not manifest_path_for_vector_path(vector_path).exists()


def paragraph(index: int, words: int = 200) -> str:
    return " ".join(f"w{index}x{word}" for word in range(words))


def document_chunks(paragraphs: list[str], *, index_revision: str = "metadata-1") -> tuple[ChunkSnapshot, ...]:
    text = "# Log\n\n" + "\n\n".join(paragraphs) + "\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    loaded = LoadedVaultDocument("default", Path("/vault"), "wiki/log.md", text, digest, digest, read_frontmatter(text))
    return tuple(replace(item, index_revision=index_revision) for item in DocumentNormalizer().normalize(loaded).chunks)


# The last paragraph is short, so the first appended paragraph joins the last chunk and changes it.
HUNDRED = [paragraph(index) for index in range(99)] + [paragraph(99, 60)]
APPENDED = [paragraph(100, 190)] + [paragraph(101 + index) for index in range(19)]


# --- generic plan_index -------------------------------------------------------------------------


def item(fingerprint: str, metadata_fingerprint: str | None = None) -> IndexItem:
    return IndexItem("c", "i", "r", "text", fingerprint, metadata_fingerprint=metadata_fingerprint)


def indexed(fingerprint: str, metadata_fingerprint: str | None = None) -> IndexedItem:
    return IndexedItem("c", "i", "r", "space", fingerprint, metadata_fingerprint=metadata_fingerprint)


def plan(desired: IndexItem, current: IndexedItem, *, full: bool = False) -> IndexPlan:
    return plan_index((desired,), (current,), collection_ids=("c",), input_kind="snapshot", space_id="space", full=full)


def test_plan_without_metadata_fingerprint_behaves_as_before() -> None:
    assert plan(item("same"), indexed("same")).unchanged_count == 1
    assert plan(item("same"), indexed("same")).metadata_updates == ()
    assert plan(item("new"), indexed("old")).upserts == (item("new"),)


def test_plan_separates_metadata_updates_from_upserts() -> None:
    result = plan(item("key", "meta-2"), indexed("key", "meta-1"))

    assert result.metadata_updates == (item("key", "meta-2"),)
    assert result.upserts == ()
    assert result.deletions == ()
    assert result.unchanged_count == 0


def test_plan_embeds_when_embedding_key_differs_even_if_metadata_differs() -> None:
    result = plan(item("key-2", "meta-2"), indexed("key-1", "meta-1"))

    assert result.upserts == (item("key-2", "meta-2"),)
    assert result.metadata_updates == ()


def test_plan_ignores_metadata_fingerprint_missing_on_one_side() -> None:
    assert plan(item("key", "meta"), indexed("key")).unchanged_count == 1
    assert plan(item("key"), indexed("key", "meta")).unchanged_count == 1


def test_full_plan_embeds_everything() -> None:
    result = plan(item("key", "meta-2"), indexed("key", "meta-1"), full=True)

    assert len(result.upserts) == 1
    assert result.metadata_updates == ()


# --- vector manifest table ----------------------------------------------------------------------


def test_manifest_table_keeps_embedding_key_and_metadata_fingerprint(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    record = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki")
    row = replace(
        VectorManifestRow.from_record(_manifest_record(record)), embedding_key="key", metadata_fingerprint="meta"
    )

    store.apply((row,), (), ())

    assert store.rows(("alpha",)) == (row,)


def test_manifest_table_from_before_the_two_columns_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "manifest.sqlite3"
    record = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki")
    old_row = VectorManifestRow.from_record(_manifest_record(record))
    with sqlite3.connect(path) as connection:
        connection.executescript(_OLD_SCHEMA)
        connection.execute(
            "INSERT INTO vector_manifest VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                old_row.vector_id,
                old_row.vault_id,
                old_row.document_id,
                old_row.chunk_id,
                old_row.content_scope,
                SPEC_FIELDS[0],
                SPEC_FIELDS[1],
                SPEC_FIELDS[2],
                SPEC_FIELDS[3],
                old_row.source_chunk_hash,
                old_row.chunker_version,
                old_row.metadata_index_revision,
                old_row.vector_index_revision,
                old_row.backend,
                old_row.backend_schema_version,
                old_row.source_role,
                old_row.provenance_family_id,
            ),
        )
    connection.close()
    store = SQLiteVectorManifestStore(path)

    assert store.rows(("alpha",)) == (old_row,)
    filled = replace(old_row, embedding_key="key", metadata_fingerprint="meta")
    store.apply((), (filled,), ())
    assert store.rows(("alpha",)) == (filled,)


# --- tracked store ------------------------------------------------------------------------------


class UpdatingStore(InMemoryVectorStore):
    def __init__(self) -> None:
        super().__init__()
        self.updates: list[tuple[VectorMetadataRecord, ...]] = []

    def supports_metadata_update(self) -> bool:
        return True

    def update_metadata(self, records: tuple[VectorMetadataRecord, ...]) -> None:
        self.updates.append(records)


def test_tracked_store_updates_inner_store_then_table(tmp_path: Path) -> None:
    inner = UpdatingStore()
    manifest = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store = ManifestTrackedVectorStore(inner, manifest=manifest, listing=_NoListing(), backend="memory-vector")
    record = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    update = _metadata_record(record, provenance_family_id="family:new", embedding_key="k", metadata_fingerprint="m")

    assert isinstance(store, VectorMetadataUpdater)
    assert store.supports_metadata_update() is True
    store.update_metadata((update,))

    assert inner.updates == [(update,)]
    (row,) = manifest.rows(("alpha",))
    assert (row.provenance_family_id, row.embedding_key, row.metadata_fingerprint) == ("family:new", "k", "m")


def test_tracked_store_without_inner_support_reports_it(tmp_path: Path) -> None:
    store = ManifestTrackedVectorStore(
        InMemoryVectorStore(),
        manifest=SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3"),
        listing=_NoListing(),
        backend="memory-vector",
    )
    record = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki")

    assert store.supports_metadata_update() is False
    with pytest.raises(VectorStoreError, match="metadata"):
        store.update_metadata((_metadata_record(record),))


# --- A-14 with Chroma and a fake embedding provider --------------------------------------------


def test_appending_to_a_document_embeds_only_new_chunks_and_the_last_chunk(tmp_path: Path) -> None:
    vector_path = tmp_path / "vector" / "chroma"
    before = document_chunks(HUNDRED)
    assert len(before) == 100
    assert run(vector_path, before)[0] == 100

    after = document_chunks(HUNDRED + APPENDED, index_revision="metadata-2")
    new_ids = {item.chunk_id for item in after} - {item.chunk_id for item in before}
    embedded, updated, unchanged = run(vector_path, after)

    assert embedded <= len(new_ids) + 1
    assert embedded == len(new_ids)
    assert updated == len(after) - len(new_ids)
    assert run(vector_path, after) == (0, 0, len(after))


def test_family_change_embeds_nothing_and_updates_chroma_metadata(tmp_path: Path) -> None:
    vector_path = tmp_path / "vector" / "chroma"
    before = document_chunks(HUNDRED)
    run(vector_path, before)

    moved = tuple(replace(item, provenance_family_id="family:other") for item in before)
    assert run(vector_path, moved) == (0, 100, 0)

    reader = ChromaVectorStore(vector_path, read_only=True)
    assert {row.provenance_family_id for row in reader.export_manifest(SCOPES[0])} == {"family:other"}
    assert run(vector_path, moved) == (0, 0, 100)


def test_first_transition_run_fills_embedding_keys_of_document_chunks(tmp_path: Path) -> None:
    vector_path = tmp_path / "vector" / "chroma"
    documents = document_chunks(HUNDRED[:10])
    legacy = chunk(text="legacy chunker")
    # A generation from before this change: Chroma metadata and no table hold embedding keys.
    run_without_keys(vector_path, (*documents, legacy))

    next_run = tuple(replace(item, index_revision="metadata-2") for item in documents) + (
        replace(legacy, index_revision="metadata-2"),
    )
    embedded, updated, unchanged = run(vector_path, next_run)

    # Document chunks whose hash, chunker and spec match only get their key. The other chunker re-embeds.
    assert (embedded, updated, unchanged) == (1, 10, 0)
    rows = SQLiteVectorManifestStore(manifest_path_for_vector_path(vector_path)).rows(("default",))
    assert all(row.embedding_key and row.metadata_fingerprint for row in rows)
    assert {row.chunker_version for row in rows} == {CHUNKER_VERSION, "heading-section-v1"}
    assert run(vector_path, next_run) == (0, 0, 11)


def test_transition_does_not_trust_a_changed_document_chunk(tmp_path: Path) -> None:
    vector_path = tmp_path / "vector" / "chroma"
    documents = document_chunks(HUNDRED[:3])
    run_without_keys(vector_path, documents)

    changed = (replace(documents[0], text="other text", content_hash="other-hash"), *documents[1:])

    assert run(vector_path, changed) == (1, 2, 0)


def test_store_without_metadata_update_re_embeds_metadata_changes() -> None:
    store = InMemoryVectorStore()
    original = chunk()
    VectorIndexer(
        chunk_store=ChunkStore((original,)), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).apply(scopes=SCOPES)
    moved = replace(original, provenance_family_id="family:other")

    plan = VectorIndexer(
        chunk_store=ChunkStore((moved,)), vector_store=store, text_embeddings=DeterministicTextEmbeddings(SPEC)
    ).plan(scopes=SCOPES)

    assert (plan.embedding_count, plan.metadata_update_count, plan.unchanged_count) == (1, 0, 0)


# --- helpers ------------------------------------------------------------------------------------

SPEC_FIELDS = ("deterministic", "test", 4, "embedding-spec-v1")

_OLD_SCHEMA = """
CREATE TABLE vector_manifest (
    vector_id TEXT PRIMARY KEY, vault_id TEXT NOT NULL, document_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
    content_scope TEXT NOT NULL, embedding_model_name TEXT NOT NULL, embedding_model_version TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL, embedding_spec_version TEXT NOT NULL, source_chunk_hash TEXT NOT NULL,
    chunker_version TEXT NOT NULL, metadata_index_revision TEXT NOT NULL, vector_index_revision TEXT NOT NULL,
    backend TEXT NOT NULL, backend_schema_version TEXT NOT NULL, source_role TEXT NOT NULL,
    provenance_family_id TEXT NOT NULL
);
CREATE INDEX vector_manifest_vault ON vector_manifest (vault_id);
"""


class _NoListing:
    def counts(self, vault_ids: tuple[str, ...]) -> dict[str, int]:
        return dict.fromkeys(vault_ids, 0)

    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRow, ...]:
        return ()


def _manifest_record(record: VectorEmbeddingRecord) -> VectorManifestRecord:
    return VectorManifestRecord(
        vector_id=record.vector_id,
        vault_id=record.vault_id,
        document_id=record.document_id,
        chunk_id=record.chunk_id,
        content_scope=record.content_scope,
        embedding_spec=record.embedding.model_spec,
        source_chunk_hash=record.source_chunk_hash,
        chunker_version=record.chunker_version,
        metadata_index_revision=record.metadata_index_revision,
        vector_index_revision=record.vector_index_revision,
        backend="memory-vector",
        backend_schema_version=record.backend_schema_version,
        source_role=record.source_role,
        provenance_family_id=record.provenance_family_id,
    )


def _metadata_record(record: VectorEmbeddingRecord, **changes: Any) -> VectorMetadataRecord:
    values: dict[str, Any] = {
        "vector_id": record.vector_id,
        "vault_id": record.vault_id,
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "content_scope": record.content_scope,
        "embedding_spec": record.embedding.model_spec,
        "source_chunk_hash": record.source_chunk_hash,
        "chunker_version": record.chunker_version,
        "metadata_index_revision": record.metadata_index_revision,
        "vector_index_revision": record.vector_index_revision,
        "backend_schema_version": record.backend_schema_version,
        "source_role": record.source_role,
        "provenance_family_id": record.provenance_family_id,
    }
    values.update(changes)
    return VectorMetadataRecord(**values)
