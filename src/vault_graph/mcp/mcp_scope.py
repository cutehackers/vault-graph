from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import CatalogError
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry


@dataclass(frozen=True)
class McpScopeInput:
    vault_ids: tuple[str, ...] | None = None
    all_vaults: bool = False
    content_scopes: tuple[str, ...] | None = None
    include_cross_vault: bool = False


def scope_from_mcp_input(
    scope_input: McpScopeInput | None,
    *,
    catalog: VaultCatalog,
    allow_graph_cross_vault: bool = False,
) -> QueryScope:
    if scope_input is None:
        base_scope = catalog.default_scope()
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in base_scope.vault_ids)
        _reject_disabled_entries(selected_entries)
        return base_scope
    if scope_input.all_vaults and scope_input.vault_ids:
        raise CatalogError("Use either all_vaults or vault_ids, not both.")
    if scope_input.all_vaults:
        base_scope = catalog.scope_for_all_enabled()
    elif scope_input.vault_ids:
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in scope_input.vault_ids)
        _reject_disabled_entries(selected_entries)
        base_scope = catalog.scope_for_vault_ids(scope_input.vault_ids)
    else:
        base_scope = catalog.default_scope()
        selected_entries = tuple(catalog.resolve(vault_id) for vault_id in base_scope.vault_ids)
        _reject_disabled_entries(selected_entries)
    if scope_input.include_cross_vault and not allow_graph_cross_vault:
        raise CatalogError("include_cross_vault is allowed only for explicit graph behavior")
    content_scopes = base_scope.content_scopes
    if scope_input.content_scopes is not None:
        narrowed_scope = QueryScope(
            vault_ids=base_scope.vault_ids,
            content_scopes=scope_input.content_scopes,
            include_cross_vault=scope_input.include_cross_vault,
        )
        _validate_content_scope_narrowing(catalog=catalog, requested_scope=narrowed_scope)
        content_scopes = scope_input.content_scopes
    return QueryScope(
        vault_ids=base_scope.vault_ids,
        content_scopes=content_scopes,
        include_cross_vault=scope_input.include_cross_vault,
    )


def _reject_disabled_entries(entries: tuple[VaultCatalogEntry, ...]) -> None:
    for entry in entries:
        if not entry.enabled:
            raise CatalogError(f"disabled vault_id: {entry.vault_id}")


def _validate_content_scope_narrowing(*, catalog: VaultCatalog, requested_scope: QueryScope) -> None:
    if not requested_scope.content_scopes:
        raise CatalogError("content_scopes cannot be empty")
    actual_by_vault = {
        actual_scope.vault_ids[0]: actual_scope
        for actual_scope in actual_query_scopes(catalog=catalog, scope=requested_scope)
    }
    for vault_id in requested_scope.vault_ids:
        actual_scope = actual_by_vault.get(vault_id)
        if actual_scope is None or actual_scope.content_scopes != requested_scope.content_scopes:
            requested = ", ".join(requested_scope.content_scopes)
            raise CatalogError(f"content scope {requested} is not enabled for vault_id: {vault_id}")
