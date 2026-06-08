from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


def test_catalog_uses_default_active_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )

    scope = catalog.default_scope()

    assert scope == QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki", "docs", "scratch/reports"))
    assert catalog.resolve("default").root_path == vault_root.resolve()


def test_duplicate_vault_ids_are_rejected(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    entry = VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root)

    with pytest.raises(CatalogError, match="duplicate vault_id"):
        VaultCatalog.from_entries(entries=[entry, entry], active_vault_id="main")


def test_all_vaults_expands_only_enabled_entries(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"
    first.mkdir()
    second.mkdir()
    third.mkdir()

    catalog = VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="first", root_path=first),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second),
            VaultCatalogEntry.from_root(vault_id="third", root_path=third, enabled=False),
        ],
        active_vault_id="first",
    )

    assert catalog.scope_for_all_enabled().vault_ids == ("first", "second")


def test_explicit_scope_rejects_unknown_vault_id(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root)],
        active_vault_id="default",
    )

    with pytest.raises(CatalogError, match="unknown vault_id"):
        catalog.scope_for_vault_ids(["missing"])


def test_catalog_rejects_content_scope_that_escapes_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with pytest.raises(CatalogError):
        VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root, content_scopes=("../outside",))


@pytest.mark.parametrize("content_scope", ["", ".", "raw/..", "data", "scratch", "scratch/notes"])
def test_catalog_rejects_unsupported_content_scope(tmp_path: Path, content_scope: str) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    with pytest.raises(CatalogError):
        VaultCatalogEntry.from_root(vault_id="default", root_path=vault_root, content_scopes=(content_scope,))


def test_catalog_allows_narrower_policy_scope_under_allowed_roots(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    entry = VaultCatalogEntry.from_root(
        vault_id="default",
        root_path=vault_root,
        content_scopes=("wiki/systems", "raw/sources", "scratch/reports/daily"),
    )

    assert entry.content_scopes == ("wiki/systems", "raw/sources", "scratch/reports/daily")


def test_query_scope_rejects_empty_vault_ids() -> None:
    with pytest.raises(CatalogError, match="QueryScope requires at least one vault_id"):
        QueryScope(vault_ids=())
