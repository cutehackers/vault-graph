from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.store_health import StoreHealth


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
    def check(self, *, effective_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport: ...
