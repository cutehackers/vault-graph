from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_keyword_index import InMemoryKeywordIndex
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_read_only_boundary import file_bytes
from tests.test_sqlite_metadata_store import make_chunk, make_document
from tests.test_vector_indexer import SPEC
from vault_graph.app.search_readiness_service import ReadOnlySearchReadiness
from vault_graph.cli.main import app
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingModelSpec, EmbeddingVector
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.retrieval.retrieval_service import RetrievalService
from vault_graph.storage.interfaces.keyword_index import KeywordHit, KeywordQuery
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


class _ConfiguredDeterministicTextEmbeddings(DeterministicTextEmbeddings):
    class Config:
        embedding_batch_size = 256
        embedding_parallelism = None
        embedding_lazy_load = True

    config = Config()


class _OfflineTextEmbeddings:
    def __init__(self) -> None:
        self.embed_calls = 0
        self.local_checks = 0

    def model_spec(self) -> EmbeddingModelSpec:
        return SPEC

    def can_embed_without_download(self) -> bool:
        self.local_checks += 1
        return False

    def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
        self.embed_calls += 1
        raise AssertionError("offline search must not load or download embeddings")


def _fake_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def _write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def _keyword_hit(document_id: str, chunk_id: str) -> KeywordHit:
    return KeywordHit(
        vault_id="default",
        document_id=document_id,
        chunk_id=chunk_id,
        rank=1,
        score=-1.0,
        backend="memory-keyword",
        index_revision="metadata-1",
        matched_fields=("text",),
    )


def test_deleted_vault_graph_index_state_rebuilds_from_vault_without_mutating_vault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _fake_text_embeddings)
    runner = CliRunner()
    vault_root = tmp_path / "vault"
    state_path = tmp_path / "state"
    _write_page(
        vault_root,
        "wiki/project.md",
        "---\ntags: [GraphRAG, Retrieval]\n---\n# GraphRAG\nGraphRAG depends on Retrieval evidence.\n",
    )
    assert runner.invoke(
        app,
        ["init", "--vault", str(vault_root), "--state", str(state_path)],
    ).exit_code == 0
    assert runner.invoke(app, ["index", "--state", str(state_path), "--vault-id", "default"]).exit_code == 0
    before = file_bytes(vault_root)

    for index_state_dir in ("metadata", "vector", "graph"):
        shutil.rmtree(state_path / index_state_dir)

    rebuild = runner.invoke(app, ["index", "--state", str(state_path), "--vault-id", "default"])
    status = runner.invoke(app, ["status", "--state", str(state_path), "--vault-id", "default", "--format", "json"])

    assert rebuild.exit_code == 0
    assert status.exit_code == 0
    assert file_bytes(vault_root) == before
    payload = json.loads(status.stdout)
    assert payload["metadata"]["ok"] is True
    assert payload["vector"]["ok"] is True
    assert payload["vector"]["stale_count"] == 0
    assert payload["graph"]["freshness"] == "fresh"
    assert payload["graph"]["stale_count"] == 0

    scope = QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki", "docs", "scratch/reports"))
    metadata_store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3")
    document_state = metadata_store.document_state("default", "wiki/project.md")
    assert document_state.document_id is not None
    keyword_hits = SQLiteKeywordIndex(state_path / "metadata" / "metadata.sqlite3").search(
        query=KeywordQuery(query_text="GraphRAG", scope=scope, limit=10)
    )
    vector_manifest = ChromaVectorStore(state_path / "vector" / "chroma", read_only=True).export_manifest(scope)
    graph_manifest = SQLiteGraphStore.open_read_only(state_path / "graph" / "graph.sqlite3").current_manifest((scope,))

    assert keyword_hits
    assert vector_manifest
    assert graph_manifest.entity_rows


def test_offline_search_threshold_degrades_without_embedding_or_cache_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document("default", "wiki/page.md", "hash-1")
    chunk = make_chunk("default", document.document_id, document.path, chunk_id="chunk-1", text="GraphRAG body")
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[document],
        chunks=[chunk],
        tombstones=[],
    )
    offline_embeddings = _OfflineTextEmbeddings()
    before = file_bytes(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=metadata_store,
        keyword_index=InMemoryKeywordIndex((_keyword_hit(document.document_id, chunk.chunk_id),)),
        vector_store=InMemoryVectorStore(),
        text_embeddings=offline_embeddings,
        readiness=ReadOnlySearchReadiness(
            metadata_store=metadata_store,
            keyword_index=InMemoryKeywordIndex((_keyword_hit(document.document_id, chunk.chunk_id),)),
            vector_store=InMemoryVectorStore(),
            text_embeddings=offline_embeddings,
        ),
    )

    response = service.search(
        query_text="GraphRAG",
        requested_scope=catalog.default_scope(),
        limit=10,
        output_format="json",
    )

    assert response.result_count == 1
    assert response.degraded is True
    assert {warning.code for warning in response.warnings} >= {
        "embedding_model_unavailable",
        "degraded_keyword_only",
    }
    assert tuple(signal.kind for signal in response.results[0].signals) == ("keyword",)
    assert offline_embeddings.local_checks == 1
    assert offline_embeddings.embed_calls == 0
    assert file_bytes(tmp_path) == before


def test_mcp_document_resources_keep_same_relative_paths_separate_by_vault_id(tmp_path: Path) -> None:
    main = tmp_path / "main"
    work = tmp_path / "work"
    main.mkdir()
    work.mkdir()
    state_path = tmp_path / "state"
    catalog = VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=main, display_name="Main"),
            VaultCatalogEntry.from_root(vault_id="work", root_path=work, display_name="Work"),
        ),
        active_vault_id="main",
    )
    catalog.save(state_path / "configs" / "vaults.yaml")
    main_doc = make_document("main", "wiki/same.md", "main-hash")
    work_doc = make_document("work", "wiki/same.md", "work-hash")
    metadata_store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[main_doc, work_doc],
        chunks=[
            make_chunk("main", main_doc.document_id, main_doc.path, chunk_id="main-chunk", text="Main-only body"),
            make_chunk("work", work_doc.document_id, work_doc.path, chunk_id="work-chunk", text="Work-only body"),
        ],
        tombstones=[],
    )
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    main_body = registered.resource_registry.read(McpResourceRequest(uri="vault://main/documents/wiki%2Fsame.md"))
    work_body = registered.resource_registry.read(McpResourceRequest(uri="vault://work/documents/wiki%2Fsame.md"))

    assert main_body.text == "Main-only body"
    assert work_body.text == "Work-only body"
    assert main_body.metadata["vault_id"] == "main"
    assert work_body.metadata["vault_id"] == "work"
    assert main_body.metadata["document_id"] != work_body.metadata["document_id"]
