from pathlib import Path

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_vector_indexer import SPEC
from tests.test_vector_store_contract import make_record
from vault_graph.app.index_service import IndexService
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.indexing.vector_indexer import VectorApplyResult
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore
from vault_graph.storage.local.vector_status_store import (
    LocalVectorStatusStore,
    embedding_spec_key,
    scope_key_for_status,
)


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_index_service_applies_metadata_then_vector(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    scope = catalog.default_scope()
    report = service.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert report.metadata.index_revision.startswith("metadata-")
    assert isinstance(report.vector, VectorApplyResult)
    assert report.vector.failed is False
    assert vector_store.export_manifest(catalog.default_scope())
    assert status.last_error is None


def test_index_service_records_vector_failure_after_metadata_success(tmp_path: Path) -> None:
    class FailingEmbeddings(DeterministicTextEmbeddings):
        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            raise RuntimeError("model unavailable")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=InMemoryVectorStore(),
        text_embeddings=FailingEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    scope = catalog.default_scope()
    report = service.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert report.metadata.index_revision.startswith("metadata-")
    assert isinstance(report.vector, VectorApplyResult)
    assert report.vector.failed is True
    assert "model unavailable" in (status.last_error or "")


def test_index_service_successful_retry_clears_vector_error(tmp_path: Path) -> None:
    class FailingEmbeddings(DeterministicTextEmbeddings):
        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            raise RuntimeError("model unavailable")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    status_store = LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json")
    scope = catalog.default_scope()
    failing = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=FailingEmbeddings(SPEC),
        vector_status_store=status_store,
    )
    failing.run_apply(scope=scope)
    succeeding = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=status_store,
    )

    report = succeeding.run_apply(scope=scope)
    status = status_store.read(scope_key=scope_key_for_status(scope), embedding_spec_key=embedding_spec_key(SPEC))

    assert isinstance(report.vector, VectorApplyResult)
    assert report.vector.failed is False
    assert status.last_error is None


def test_index_service_uses_per_vault_actual_scopes_for_vector_reconcile(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_page(first_root, "wiki/page.md", "# First\nBody\n")
    write_page(second_root, "docs/page.md", "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root, content_scopes=("docs",)),
        ],
        active_vault_id="first",
    )
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    vector_store = InMemoryVectorStore()
    outside_first_scope = make_record(vault_id="first", path="docs/old.md", text="old", content_scope="docs")
    vector_store.apply_vector_revision(vector_index_revision="vector-1", records=(outside_first_scope,), tombstones=())
    service = IndexService(
        catalog=catalog,
        metadata_store=metadata_store,
        vector_store=vector_store,
        text_embeddings=DeterministicTextEmbeddings(SPEC),
        vector_status_store=LocalVectorStatusStore(tmp_path / "state" / "vector" / "status.json"),
    )

    service.run_apply(scope=catalog.scope_for_all_enabled())
    manifest = vector_store.export_manifest(catalog.scope_for_all_enabled())

    assert ("first", outside_first_scope.chunk_id) in tuple((row.vault_id, row.chunk_id) for row in manifest)
