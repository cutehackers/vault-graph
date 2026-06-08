from pathlib import Path

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def make_vault(root: Path, body: str = "# Page\nBody\n") -> None:
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "page.md").write_text(body, encoding="utf-8")


def test_dry_run_reports_changes_without_writing_store(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3")

    plan = MetadataIndexer(catalog=catalog, metadata_store=store).plan(scope=catalog.default_scope())

    assert plan.changed_paths == (("default", "wiki/page.md"),)
    assert store.list_document_states(("default",)) == ()


def test_apply_writes_metadata_projection(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)

    result = MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.default_scope())

    assert result.index_revision.startswith("metadata-")
    assert store.document_state("default", "wiki/page.md").is_tombstoned is False


def test_frontmatter_only_change_is_changed(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root, "---\ntitle: One\n---\n# Page\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    (vault_root / "wiki" / "page.md").write_text("---\ntitle: Two\n---\n# Page\nBody\n", encoding="utf-8")
    plan = indexer.plan(scope=catalog.default_scope())

    assert plan.changed_paths == (("default", "wiki/page.md"),)


def test_chunker_version_change_is_changed(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    with store.connect_for_tests() as connection:
        connection.execute("UPDATE chunks SET chunker_version = 'old-chunker'")
    plan = indexer.plan(scope=catalog.default_scope())

    assert plan.changed_paths == (("default", "wiki/page.md"),)


def test_scoped_apply_does_not_tombstone_other_vaults(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    make_vault(first_root, "# First\nBody\n")
    make_vault(second_root, "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first_root),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second_root),
        ],
        active_vault_id="first",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.scope_for_all_enabled())

    (first_root / "wiki" / "page.md").unlink()
    indexer.apply(scope=catalog.scope_for_vault_ids(["first"]))

    assert store.document_state("first", "wiki/page.md").is_tombstoned is True
    assert store.document_state("second", "wiki/page.md").is_tombstoned is False


def test_partial_content_scope_does_not_delete_out_of_scope_documents(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "docs").mkdir()
    (vault_root / "wiki" / "page.md").write_text("# Wiki\nBody\n", encoding="utf-8")
    (vault_root / "docs" / "note.md").write_text("# Docs\nBody\n", encoding="utf-8")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    plan = indexer.plan(scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)))

    assert plan.deleted_paths == ()
    assert store.document_state("default", "docs/note.md").is_tombstoned is False


def test_tombstoned_document_is_not_repeated_as_deleted(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    make_vault(vault_root)
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    (vault_root / "wiki" / "page.md").unlink()
    first_delete = indexer.apply(scope=catalog.default_scope())
    second_plan = indexer.plan(scope=catalog.default_scope())

    assert first_delete.deleted_paths == (("default", "wiki/page.md"),)
    assert second_plan.deleted_paths == ()


def test_narrower_policy_scope_indexes_existing_file_under_broader_entry_scope(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki" / "systems").mkdir(parents=True)
    (vault_root / "wiki" / "systems" / "page.md").write_text("# System\nBody\n", encoding="utf-8")
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root, content_scopes=("wiki",))],
        active_vault_id="default",
    )
    store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    indexer = MetadataIndexer(catalog=catalog, metadata_store=store)
    indexer.apply(scope=catalog.default_scope())

    plan = indexer.plan(scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)))

    assert plan.deleted_paths == ()
    assert plan.unchanged_paths == (("default", "wiki/systems/page.md"),)
