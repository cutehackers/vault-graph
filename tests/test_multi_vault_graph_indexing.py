from pathlib import Path

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from vault_graph.app.index_service import IndexService
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_all_vault_graph_apply_creates_revisions_per_normalized_vault_scope(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_page(first_root, "docs/first.md", "# First\nBody\n")
    write_page(first_root, "wiki/first.md", "# First Wiki\nBody\n")
    write_page(second_root, "wiki/second.md", "# Second\nBody\n")
    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(
                vault_id="first",
                root_path=first_root,
                content_scopes=("docs", "wiki"),
            ),
            VaultCatalogEntry.from_root(
                vault_id="second",
                root_path=second_root,
                content_scopes=("wiki",),
            ),
        ],
        active_vault_id="first",
    )
    graph_store = InMemoryGraphStore()
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        graph_store=graph_store,
    )

    report = service.run_apply(scope=catalog.scope_for_all_enabled())

    first_scope = QueryScope(vault_ids=("first",), content_scopes=("docs", "wiki"))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    revisions = graph_store.latest_revisions((first_scope, second_scope))
    assert report.exit_code == 0
    assert tuple(revision.actual_scope for revision in revisions) == (
        graph_scope_key(first_scope),
        graph_scope_key(second_scope),
    )
