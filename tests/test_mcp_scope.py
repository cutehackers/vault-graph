from __future__ import annotations

from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input


def _catalog(tmp_path: Path) -> VaultCatalog:
    first = tmp_path / "first"
    second = tmp_path / "second"
    disabled = tmp_path / "disabled"
    for root in (first, second, disabled):
        root.mkdir()
    return VaultCatalog.from_entries(
        entries=[
            VaultCatalogEntry.from_root(vault_id="default", root_path=first, content_scopes=("wiki", "docs")),
            VaultCatalogEntry.from_root(vault_id="work", root_path=second, content_scopes=("wiki",)),
            VaultCatalogEntry.from_root(vault_id="off", root_path=disabled, enabled=False),
        ],
        active_vault_id="default",
    )


def test_none_scope_uses_active_vault(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(None, catalog=_catalog(tmp_path))

    assert scope.vault_ids == ("default",)
    assert scope.content_scopes == ("wiki", "docs")
    assert scope.include_cross_vault is False


def test_all_vaults_expands_enabled_vaults(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(McpScopeInput(all_vaults=True), catalog=_catalog(tmp_path))

    assert scope.vault_ids == ("default", "work")
    assert scope.include_cross_vault is False


def test_scope_rejects_ambiguous_vault_selection(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="either all_vaults or vault_ids"):
        scope_from_mcp_input(McpScopeInput(vault_ids=("default",), all_vaults=True), catalog=_catalog(tmp_path))


def test_scope_rejects_disabled_vault_id(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="disabled vault_id: off"):
        scope_from_mcp_input(McpScopeInput(vault_ids=("off",)), catalog=_catalog(tmp_path))


def test_scope_rejects_cross_vault_without_graph_permission(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="explicit graph behavior"):
        scope_from_mcp_input(
            McpScopeInput(all_vaults=True, include_cross_vault=True),
            catalog=_catalog(tmp_path),
        )


def test_scope_allows_cross_vault_for_explicit_graph_behavior(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(
        McpScopeInput(all_vaults=True, include_cross_vault=True),
        catalog=_catalog(tmp_path),
        allow_graph_cross_vault=True,
    )

    assert scope.include_cross_vault is True


def test_scope_content_scopes_must_narrow_every_selected_vault(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="not enabled for vault_id: work"):
        scope_from_mcp_input(
            McpScopeInput(vault_ids=("default", "work"), content_scopes=("docs",)),
            catalog=_catalog(tmp_path),
        )


def test_scope_content_scopes_can_narrow_shared_scope(tmp_path: Path) -> None:
    scope = scope_from_mcp_input(
        McpScopeInput(vault_ids=("default", "work"), content_scopes=("wiki",)),
        catalog=_catalog(tmp_path),
    )

    assert scope.vault_ids == ("default", "work")
    assert scope.content_scopes == ("wiki",)
