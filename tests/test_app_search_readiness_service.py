import sqlite3
from dataclasses import replace
from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.indexing.vector_indexer import VectorIndexer
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class HealthyKeywordIndex:
    def search(self, query: KeywordQuery) -> tuple[KeywordHit, ...]:
        return ()

    def index_revision(self, scope: QueryScope) -> str:
        return "keyword-1"

    def health(self) -> StoreHealth:
        return StoreHealth(ok=True, backend="keyword", schema_version="v1", schema_compatible=True, message="ok")


def metadata_store_with_chunk(tmp_path: Path, *, content_hash: str = "chunk") -> tuple[SQLiteMetadataStore, QueryScope]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path)
    chunk = replace(chunk, content_hash=content_hash, index_revision="metadata-1")
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    return store, QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def test_search_readiness_reports_vector_freshness(tmp_path: Path) -> None:
    metadata_store, scope = metadata_store_with_chunk(tmp_path)
    vector_store = InMemoryVectorStore()
    embeddings = DeterministicTextEmbeddings(SPEC)
    VectorIndexer(chunk_store=metadata_store, vector_store=vector_store, text_embeddings=embeddings).apply(
        scopes=(scope,)
    )
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=vector_store,
        text_embeddings=embeddings,
    )

    report = readiness.check(actual_scopes=(scope,))

    assert report.metadata_health.ok is True
    assert report.keyword_health.ok is True
    assert report.vector_health is not None
    assert report.vector_stale_count == 0
    assert report.scope_readiness[0].scope_key == "default:wiki"
    assert report.scope_readiness[0].vector_stale_count == 0
    assert report.can_embed_without_download is True
    assert {revision.kind for revision in report.store_revisions} >= {"metadata", "keyword", "vector"}
    assert any(revision.kind == "keyword" and revision.revision == "keyword-1" for revision in report.store_revisions)
    assert all(revision.scope_key for revision in report.store_revisions)


def test_search_readiness_reports_stale_vector_without_status_store(tmp_path: Path) -> None:
    old_store, scope = metadata_store_with_chunk(tmp_path / "old", content_hash="old")
    vector_store = InMemoryVectorStore()
    embeddings = DeterministicTextEmbeddings(SPEC)
    VectorIndexer(chunk_store=old_store, vector_store=vector_store, text_embeddings=embeddings).apply(scopes=(scope,))
    new_store, _ = metadata_store_with_chunk(tmp_path / "new", content_hash="changed")
    readiness = ReadOnlySearchReadiness(
        metadata_store=new_store,
        keyword_index=HealthyKeywordIndex(),
        vector_store=vector_store,
        text_embeddings=embeddings,
    )

    report = readiness.check(actual_scopes=(scope,))

    assert report.vector_stale_count == 2
    assert report.scope_readiness[0].scope_key == "default:wiki"
    assert report.scope_readiness[0].vector_stale_count == 2


def test_search_readiness_does_not_read_chunks_when_metadata_schema_is_incompatible(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE documents (id TEXT PRIMARY KEY)")
    metadata_store = SQLiteMetadataStore(database_path)
    readiness = ReadOnlySearchReadiness(
        metadata_store=metadata_store,
        keyword_index=HealthyKeywordIndex(),
    )

    report = readiness.check(actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert report.metadata_health.ok is False
    assert report.store_revisions == ()
