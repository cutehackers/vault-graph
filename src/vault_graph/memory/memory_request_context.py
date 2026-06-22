from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.memory_source_reader import MemorySourceReader

if TYPE_CHECKING:
    from vault_graph.app.index_service import StatusReport


class MemoryStatusService(Protocol):
    def status(self, *, scope: QueryScope | None = None) -> StatusReport: ...


@dataclass(frozen=True)
class MemoryVaultDocuments:
    vault_id: str
    scope: QueryScope
    documents: tuple[DocumentSnapshot, ...]


@dataclass(frozen=True)
class MemoryRequestContext:
    requested_scope: QueryScope
    actual_scopes: tuple[QueryScope, ...]
    status_report: StatusReport
    documents_by_vault: tuple[MemoryVaultDocuments, ...]
    generated_at: str


def build_memory_request_context(
    *,
    catalog: VaultCatalog,
    source_reader: MemorySourceReader,
    status_service: MemoryStatusService,
    requested_scope: QueryScope,
    clock: Callable[[], datetime] | None = None,
) -> MemoryRequestContext:
    status_report = status_service.status(scope=requested_scope)
    if not status_report.metadata_ok or not status_report.metadata_schema_compatible:
        raise MemoryProjectionError(f"metadata_unavailable: {status_report.metadata_message}")
    actual_scopes = actual_query_scopes(catalog=catalog, scope=requested_scope)
    generated_at = (clock or _utc_now)().isoformat()
    documents_by_vault = tuple(
        MemoryVaultDocuments(
            vault_id=actual_scope.vault_ids[0],
            scope=actual_scope,
            documents=source_reader.list_documents(scope=actual_scope),
        )
        for actual_scope in actual_scopes
    )
    return MemoryRequestContext(
        requested_scope=requested_scope,
        actual_scopes=actual_scopes,
        status_report=status_report,
        documents_by_vault=documents_by_vault,
        generated_at=generated_at,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
