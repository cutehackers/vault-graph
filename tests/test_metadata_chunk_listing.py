from pathlib import Path

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def make_catalog(root: Path, vault_id: str = "default") -> VaultCatalog:
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root)],
        active_vault_id=vault_id,
    )


def test_list_chunks_returns_current_non_tombstoned_chunks(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    chunks = store.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert len(chunks) == 1
    assert chunks[0].vault_id == "default"
    assert chunks[0].path == "wiki/page.md"
    assert chunks[0].text == "Body"
    assert chunks[0].content_hash
    assert chunks[0].chunker_version == "heading-section-v1"
    assert chunks[0].index_revision is not None


def test_list_chunks_filters_vault_and_content_scope(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_page(first_root, "wiki/page.md", "# First\nBody\n")
    write_page(first_root, "docs/page.md", "# Docs\nBody\n")
    write_page(second_root, "wiki/page.md", "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.scope_for_all_enabled())

    chunks = store.list_chunks(QueryScope(vault_ids=("first",), content_scopes=("wiki",)))

    assert tuple((chunk.vault_id, chunk.path) for chunk in chunks) == (("first", "wiki/page.md"),)


def test_list_chunks_excludes_tombstoned_documents(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())
    (vault_root / "wiki" / "page.md").unlink()
    indexer.apply(scope=catalog.default_scope())

    chunks = store.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert chunks == ()


def test_metadata_preview_contains_chunks_after_apply_without_writing(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = make_catalog(vault_root)
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")
    preview = MetadataIndexer(catalog=catalog, metadata_store=store).preview(scope=catalog.default_scope())

    assert preview.plan.changed_paths == (("default", "wiki/page.md"),)
    assert len(preview.chunks_after_apply) == 1
    assert preview.chunks_after_apply[0].index_revision == preview.plan.index_revision
    assert not (tmp_path / "state" / "metadata.sqlite3").exists()
