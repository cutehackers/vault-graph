from pathlib import Path

import chromadb

from tests.test_vector_store_contract import SECOND_SPEC, make_query, make_record
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.vector_store import VectorTombstone
from vault_graph.storage.local.chroma_vector_store import CHROMA_VECTOR_SCHEMA_VERSION, ChromaVectorStore


def test_chroma_persists_records_and_exports_manifest(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")

    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    reopened = ChromaVectorStore(tmp_path / "chroma", initialize=False)

    manifest = reopened.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.vector_id for row in manifest) == (record.vector_id,)
    assert manifest[0].backend == "chroma"
    assert manifest[0].backend_schema_version == CHROMA_VECTOR_SCHEMA_VERSION


def test_chroma_filters_scope_before_limit(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    wiki = make_record(vault_id="default", path="wiki/page.md", text="exact query", content_scope="wiki")
    docs = make_record(vault_id="default", path="docs/page.md", text="exact query", content_scope="docs")
    other = make_record(vault_id="other", path="wiki/page.md", text="exact query", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(wiki, docs, other), tombstones=())

    hits = store.search(
        make_query(text="exact query", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)), limit=1)
    )

    assert tuple((hit.vault_id, hit.content_scope) for hit in hits) == (("default", "wiki"),)


def test_chroma_exports_old_model_manifest_rows(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    old_record = make_record(
        vault_id="default",
        path="wiki/page.md",
        text="alpha",
        content_scope="wiki",
        model_spec=SECOND_SPEC,
    )
    store.apply_vector_revision(vector_index_revision="vector-1", records=(old_record,), tombstones=())

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.embedding_spec for row in manifest) == (SECOND_SPEC,)


def test_chroma_exact_tombstone_removes_record(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(
            VectorTombstone(
                vector_id=record.vector_id,
                vault_id=record.vault_id,
                chunk_id=record.chunk_id,
                embedding_spec=record.embedding.model_spec,
            ),
        ),
    )

    assert (
        store.search(
            make_query(
                text="alpha",
                scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
            )
        )
        == ()
    )


def test_chroma_tombstone_requires_matching_vault_chunk_and_spec(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")
    store.apply_vector_revision(vector_index_revision="vector-1", records=(record,), tombstones=())
    store.apply_vector_revision(
        vector_index_revision="vector-2",
        records=(),
        tombstones=(
            VectorTombstone(
                vector_id=record.vector_id,
                vault_id="other",
                chunk_id=record.chunk_id,
                embedding_spec=record.embedding.model_spec,
            ),
        ),
    )

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert tuple(row.vector_id for row in manifest) == (record.vector_id,)


def test_chroma_missing_path_reports_uninitialized_health(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "missing", initialize=False)

    health = store.health()

    assert health.ok is False
    assert health.backend == "chroma"
    assert health.schema_compatible is False
    assert "not initialized" in health.message


def test_chroma_missing_readonly_path_export_and_search_do_not_create_state(tmp_path: Path) -> None:
    path = tmp_path / "missing"
    store = ChromaVectorStore(path, initialize=False)

    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    hits = store.search(make_query(text="alpha", scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",))))

    assert manifest == ()
    assert hits == ()
    assert not path.exists()


def test_chroma_readonly_existing_empty_path_does_not_create_sqlite(tmp_path: Path) -> None:
    path = tmp_path / "empty-chroma"
    path.mkdir()
    store = ChromaVectorStore(path, initialize=False, read_only=True)

    health = store.health()
    manifest = store.export_manifest(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert health.ok is False
    assert "not initialized" in health.message
    assert manifest == ()
    assert not (path / "chroma.sqlite3").exists()


def test_chroma_health_rejects_incompatible_vault_graph_collection_schema(tmp_path: Path) -> None:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    client.get_or_create_collection(
        "vault_graph_old",
        metadata={
            "vault_graph_backend": "chroma",
            "vault_graph_schema_version": "old-schema",
        },
    )
    store = ChromaVectorStore(tmp_path / "chroma", initialize=False, read_only=True)

    health = store.health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "schema incompatible" in health.message


def test_chroma_rejects_record_revision_mismatch(tmp_path: Path) -> None:
    store = ChromaVectorStore(tmp_path / "chroma", initialize=True)
    record = make_record(vault_id="default", path="wiki/page.md", text="alpha", content_scope="wiki")

    try:
        store.apply_vector_revision(vector_index_revision="vector-other", records=(record,), tombstones=())
    except Exception as exc:
        assert "record vector_index_revision must match revision being applied" in str(exc)
    else:
        raise AssertionError("Chroma should reject records whose vector revision does not match the apply revision")
