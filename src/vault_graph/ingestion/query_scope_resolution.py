from __future__ import annotations

from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog


def effective_query_scopes(*, catalog: VaultCatalog, scope: QueryScope) -> tuple[QueryScope, ...]:
    effective_scopes: list[QueryScope] = []
    for vault_id in scope.vault_ids:
        entry = catalog.resolve(vault_id)
        content_scopes: list[str] = []
        for query_scope in scope.content_scopes:
            for entry_scope in entry.content_scopes:
                if _is_same_or_child(path=query_scope, parent=entry_scope):
                    content_scopes.append(query_scope)
                elif _is_same_or_child(path=entry_scope, parent=query_scope):
                    content_scopes.append(entry_scope)
        deduped = tuple(dict.fromkeys(content_scopes))
        if deduped:
            effective_scopes.append(
                QueryScope(
                    vault_ids=(entry.vault_id,),
                    content_scopes=deduped,
                    include_cross_vault=scope.include_cross_vault,
                )
            )
    return tuple(effective_scopes)


def _is_same_or_child(*, path: str, parent: str) -> bool:
    return path == parent or path.startswith(f"{parent}/")
