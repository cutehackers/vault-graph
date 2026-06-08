from __future__ import annotations

from dataclasses import dataclass

from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.revision_planner import MetadataRevisionPlan
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore


@dataclass(frozen=True)
class StatusReport:
    active_vault_id: str
    vaults: tuple[tuple[str, str], ...]
    metadata_ok: bool
    metadata_schema_compatible: bool
    metadata_message: str


class IndexService:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store

    def plan(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).plan(scope=scope, full=full)

    def apply(self, *, scope: QueryScope, full: bool = False) -> MetadataRevisionPlan:
        return MetadataIndexer(catalog=self._catalog, metadata_store=self._metadata_store).apply(scope=scope, full=full)

    def status(self) -> StatusReport:
        health = self._metadata_store.health()
        return StatusReport(
            active_vault_id=self._catalog.active_vault_id,
            vaults=tuple((entry.vault_id, str(entry.root_path)) for entry in self._catalog.entries()),
            metadata_ok=health.ok,
            metadata_schema_compatible=health.schema_compatible,
            metadata_message=health.message,
        )
