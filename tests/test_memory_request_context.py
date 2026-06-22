from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_mcp_tools import make_status_report
from tests.test_sqlite_metadata_store import make_document
from vault_graph.app.index_service import StatusReport
from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.memory.memory_request_context import build_memory_request_context


class RecordingSourceReader:
    def __init__(self, documents: tuple[DocumentSnapshot, ...]) -> None:
        self.documents = documents
        self.calls: list[QueryScope] = []

    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        self.calls.append(scope)
        return tuple(document for document in self.documents if document.vault_id in scope.vault_ids)


class RecordingStatusService:
    def __init__(self, report: StatusReport) -> None:
        self.report = report
        self.calls: list[QueryScope | None] = []

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        self.calls.append(scope)
        return self.report


def test_build_memory_request_context_checks_status_before_listing_documents(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    scope = QueryScope(vault_ids=("main",), content_scopes=("wiki",))
    source_reader = RecordingSourceReader((make_document("main", "wiki/page.md", "hash"),))
    status_service = RecordingStatusService(make_status_report())

    context = build_memory_request_context(
        catalog=catalog,
        source_reader=source_reader,  # type: ignore[arg-type]
        status_service=status_service,
        requested_scope=scope,
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )

    assert status_service.calls == [scope]
    assert source_reader.calls == [scope]
    assert context.generated_at == "2026-06-18T00:00:00+00:00"


def test_build_memory_request_context_raises_metadata_unavailable_when_status_is_unhealthy(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path)
    scope = QueryScope(vault_ids=("main",), content_scopes=("wiki",))
    source_reader = RecordingSourceReader(())
    status_service = RecordingStatusService(
        replace(make_status_report(), metadata_ok=False, metadata_schema_compatible=False, metadata_message="missing")
    )

    with pytest.raises(MemoryProjectionError, match="metadata_unavailable"):
        build_memory_request_context(
            catalog=catalog,
            source_reader=source_reader,  # type: ignore[arg-type]
            status_service=status_service,
            requested_scope=scope,
        )

    assert source_reader.calls == []


def test_build_memory_request_context_lists_documents_once_per_actual_scope(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, vault_ids=("main", "work"))
    scope = QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",))
    documents = (
        make_document("main", "wiki/main.md", "main"),
        make_document("work", "wiki/work.md", "work"),
    )
    source_reader = RecordingSourceReader(documents)

    context = build_memory_request_context(
        catalog=catalog,
        source_reader=source_reader,  # type: ignore[arg-type]
        status_service=RecordingStatusService(make_status_report()),
        requested_scope=scope,
    )

    assert [call.vault_ids for call in source_reader.calls] == [("main",), ("work",)]
    assert [group.vault_id for group in context.documents_by_vault] == ["main", "work"]


def test_build_memory_request_context_uses_one_generated_timestamp(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, vault_ids=("main", "work"))
    scope = QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",))

    context = build_memory_request_context(
        catalog=catalog,
        source_reader=RecordingSourceReader(()),  # type: ignore[arg-type]
        status_service=RecordingStatusService(make_status_report()),
        requested_scope=scope,
        clock=lambda: datetime(2026, 6, 18, 1, 2, 3, tzinfo=UTC),
    )

    assert context.generated_at == "2026-06-18T01:02:03+00:00"
    assert all(group.scope.vault_ids == (group.vault_id,) for group in context.documents_by_vault)


def make_catalog(tmp_path: Path, *, vault_ids: tuple[str, ...] = ("main",)) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir()
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, display_name=vault_id.title()))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])
