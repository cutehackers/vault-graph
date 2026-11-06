from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import pytest

from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_vector_store_contract import SECOND_SPEC, SPEC, make_record
from vault_graph.errors import VectorStoreError
from vault_graph.storage.interfaces.vector_manifest_store import VectorManifestRow, VectorManifestSource
from vault_graph.storage.interfaces.vector_store import (
    VectorEmbeddingRecord,
    VectorManifestRecord,
    VectorTombstone,
)
from vault_graph.storage.local.sqlite_vector_manifest_store import (
    ManifestTrackedVectorStore,
    SQLiteVectorManifestStore,
    manifest_path_for_vector_path,
)


def row(record: VectorEmbeddingRecord) -> VectorManifestRow:
    return VectorManifestRow(
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


def tombstone(record: VectorEmbeddingRecord) -> VectorTombstone:
    return VectorTombstone(
        vector_id=record.vector_id,
        vault_id=record.vault_id,
        chunk_id=record.chunk_id,
        embedding_spec=record.embedding.model_spec,
    )


class StaticListing:
    def __init__(self, store: InMemoryVectorStore) -> None:
        self._store = store

    def counts(self, vault_ids: tuple[str, ...]) -> Mapping[str, int]:
        rows = self.rows(vault_ids)
        return {vault: sum(1 for item in rows if item.vault_id == vault) for vault in vault_ids}

    def rows(self, vault_ids: tuple[str, ...]) -> tuple[VectorManifestRecord, ...]:
        records = self._store._records.values()
        return tuple(VectorManifestRow.from_record(row(record)) for record in records if record.vault_id in vault_ids)


ALPHA = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki")
BETA = make_record(vault_id="beta", path="wiki/b.md", text="b", content_scope="wiki")


def test_manifest_path_sits_beside_chroma_in_the_generation(tmp_path: Path) -> None:
    assert manifest_path_for_vector_path(tmp_path / "vector" / "chroma") == tmp_path / "vector" / "manifest.sqlite3"


def test_missing_table_reads_empty_and_counts_zero(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "vector" / "manifest.sqlite3")

    assert store.exists() is False
    assert store.rows(("alpha",)) == ()
    assert store.count("alpha") == 0
    assert not (tmp_path / "vector" / "manifest.sqlite3").exists()


def test_apply_writes_rows_readable_by_vault(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")

    store.apply((row(ALPHA), row(BETA)), (), ())

    assert store.exists() is True
    assert store.rows(("alpha",)) == (row(ALPHA),)
    assert store.rows(("alpha", "beta")) == (row(ALPHA), row(BETA))
    assert store.count("beta") == 1


def test_metadata_update_replaces_the_row(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store.apply((row(ALPHA),), (), ())
    updated = replace(row(ALPHA), provenance_family_id="family:moved")

    store.apply((), (updated,), ())

    assert store.rows(("alpha",)) == (updated,)


def test_deletion_removes_only_matching_vault_chunk_and_spec(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store.apply((row(ALPHA),), (), ())
    wrong_spec = VectorTombstone(
        vector_id=ALPHA.vector_id, vault_id="alpha", chunk_id=ALPHA.chunk_id, embedding_spec=SECOND_SPEC
    )

    store.apply((), (), (wrong_spec,))
    assert store.count("alpha") == 1

    store.apply((), (), (tombstone(ALPHA),))
    assert store.count("alpha") == 0


def test_replace_vault_rows_leaves_other_vaults(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store.apply((row(ALPHA), row(BETA)), (), ())
    other = make_record(vault_id="alpha", path="wiki/c.md", text="c", content_scope="wiki")

    store.replace_vault_rows(("alpha",), (row(other),))

    assert store.rows(("alpha", "beta")) == (row(other), row(BETA))


def test_tracked_store_writes_table_after_store_write(tmp_path: Path) -> None:
    inner = InMemoryVectorStore()
    manifest = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store = ManifestTrackedVectorStore(inner, manifest=manifest, listing=StaticListing(inner), backend="memory-vector")

    store.apply_vector_revision(vector_index_revision="vector-1", records=(ALPHA,), tombstones=())
    assert manifest.rows(("alpha",)) == (row(ALPHA),)

    store.apply_vector_revision(vector_index_revision="vector-2", records=(), tombstones=(tombstone(ALPHA),))
    assert manifest.count("alpha") == 0
    assert isinstance(store, VectorManifestSource)


def test_tracked_store_skips_table_when_store_write_fails(tmp_path: Path) -> None:
    class FailingStore(InMemoryVectorStore):
        def apply_vector_revision(
            self,
            *,
            vector_index_revision: str,
            records: tuple[VectorEmbeddingRecord, ...],
            tombstones: tuple[VectorTombstone, ...],
        ) -> None:
            raise VectorStoreError("too many SQL variables")

    inner = FailingStore()
    manifest = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store = ManifestTrackedVectorStore(inner, manifest=manifest, listing=StaticListing(inner), backend="memory-vector")

    with pytest.raises(VectorStoreError):
        store.apply_vector_revision(vector_index_revision="vector-1", records=(ALPHA,), tombstones=())

    assert manifest.exists() is False


def test_manifest_rows_rebuild_only_vaults_whose_count_differs(tmp_path: Path) -> None:
    inner = InMemoryVectorStore()
    manifest = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    store = ManifestTrackedVectorStore(inner, manifest=manifest, listing=StaticListing(inner), backend="memory-vector")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(ALPHA, BETA), tombstones=())
    manifest.apply((), (), (tombstone(BETA),))

    read = store.manifest_rows(("alpha", "beta"))

    assert read.rows == (row(ALPHA), row(BETA))
    assert read.warnings == (
        "vector manifest table rebuilt from the vector store for beta: row count differs from the vector store",
    )
    assert store.manifest_rows(("alpha", "beta")).warnings == ()


def test_record_spec_survives_round_trip(tmp_path: Path) -> None:
    store = SQLiteVectorManifestStore(tmp_path / "manifest.sqlite3")
    second = make_record(vault_id="alpha", path="wiki/a.md", text="a", content_scope="wiki", model_spec=SECOND_SPEC)

    store.apply((row(ALPHA), row(second)), (), ())

    assert {item.embedding_spec for item in store.rows(("alpha",))} == {SPEC, SECOND_SPEC}
