from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.errors import SearchError
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth


@dataclass(frozen=True)
class SearchStoreRevision:
    kind: str
    revision: str
    scope_key: str
    vault_id: str | None = None

    def __post_init__(self) -> None:
        _require_revision_value(self.kind, "kind")
        _require_revision_value(self.revision, "revision")
        _require_revision_value(self.scope_key, "scope_key")


@dataclass(frozen=True)
class SearchScopeReadiness:
    scope_key: str
    vault_ids: tuple[str, ...]
    vector_stale_count: int | None


@dataclass(frozen=True)
class SearchReadinessReport:
    metadata_health: StoreHealth
    keyword_health: StoreHealth
    vector_health: StoreHealth | None
    vector_stale_count: int | None
    can_embed_without_download: bool
    store_revisions: tuple[SearchStoreRevision, ...]
    scope_readiness: tuple[SearchScopeReadiness, ...] = ()


class SearchReadiness(Protocol):
    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport: ...


def _require_revision_value(value: str, field_name: str) -> None:
    if not value:
        raise SearchError(f"{field_name} is required")
