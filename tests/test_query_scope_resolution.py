from pathlib import Path

from vault_graph.app.query_scope_resolution import effective_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


def _entry(tmp_path: Path, vault_id: str, scopes: tuple[str, ...]) -> VaultCatalogEntry:
    root = tmp_path / vault_id
    root.mkdir()
    return VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=scopes)


def test_effective_scopes_keep_each_vault_narrow(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[
            _entry(tmp_path, "first", ("wiki",)),
            _entry(tmp_path, "second", ("docs",)),
        ],
        active_vault_id="first",
    )

    scopes = effective_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki", "docs")),
    )

    assert tuple(scope.vault_ids for scope in scopes) == (("first",), ("second",))
    assert tuple(scope.content_scopes for scope in scopes) == (("wiki",), ("docs",))


def test_effective_scopes_use_narrower_child_scope(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = effective_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/systems",)),
    )

    assert scopes[0].content_scopes == ("wiki/systems",)


def test_effective_scopes_skip_disjoint_scope_pairs(tmp_path: Path) -> None:
    catalog = VaultCatalog.from_entries(
        entries=[_entry(tmp_path, "default", ("wiki",))],
        active_vault_id="default",
    )

    scopes = effective_query_scopes(
        catalog=catalog,
        scope=QueryScope(vault_ids=("default",), content_scopes=("docs",)),
    )

    assert scopes == ()
