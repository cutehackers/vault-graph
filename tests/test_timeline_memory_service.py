from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from tests.test_mcp_tools import make_status_report
from tests.test_sqlite_metadata_store import make_document
from vault_graph.app.index_service import StatusReport
from vault_graph.errors import MemoryProjectionError, MetadataStoreError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.memory.memory_models import MemoryWarning
from vault_graph.memory.timeline_memory import (
    RecentChangesProjection,
    TimelineEvidenceRef,
    TimelineItem,
    TimelineMemoryService,
    TimelineVault,
    parse_timeline_since,
    stable_timeline_item_id,
)
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class FakeMetadataStore:
    def __init__(self, documents: tuple[DocumentSnapshot, ...]) -> None:
        self.documents = documents
        self.recent_calls: list[dict[str, object]] = []

    def list_recent_documents(
        self,
        scope: QueryScope,
        *,
        since: str | None = None,
        limit: int = 20,
    ) -> tuple[DocumentSnapshot, ...]:
        self.recent_calls.append({"scope": scope, "since": since, "limit": limit})
        values = [document for document in self.documents if document.vault_id in scope.vault_ids]
        if since is not None:
            values = [document for document in values if _document_after(document, since)]
        return tuple(values[:limit])

    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        raise AssertionError("TimelineMemoryService must use list_recent_documents")


class FailingMetadataStore(FakeMetadataStore):
    def list_recent_documents(
        self,
        scope: QueryScope,
        *,
        since: str | None = None,
        limit: int = 20,
    ) -> tuple[DocumentSnapshot, ...]:
        del scope, since, limit
        raise MetadataStoreError("metadata unavailable")


class FakeStatusService:
    def __init__(self, *, metadata_ok: bool = True) -> None:
        self.calls: list[QueryScope | None] = []
        self.metadata_ok = metadata_ok

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        self.calls.append(scope)
        report = make_status_report()
        return replace(
            report,
            metadata_ok=self.metadata_ok,
            metadata_schema_compatible=self.metadata_ok,
            metadata_message="ok" if self.metadata_ok else "not initialized",
            vector_revision="vector-1",
            vector_last_success_at="2026-06-18T03:00:00+00:00",
            graph_last_success_revision="graph-1",
            graph_last_success_at="2026-06-18T02:00:00+00:00",
        )


class StaticStatusService:
    def __init__(self, report: StatusReport) -> None:
        self.report = report

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        del scope
        return self.report


def test_timeline_dtos_validate_evidence_warning_and_item_id_shape() -> None:
    warning = make_warning()
    with pytest.raises(MemoryProjectionError, match="document_id"):
        TimelineEvidenceRef(source_kind="document", vault_id="main", path="wiki/page.md", content_hash="hash")

    with pytest.raises(MemoryProjectionError, match="warning"):
        TimelineItem(
            item_id="timeline:warning:0123456789abcdef01234567",
            origin="warning",
            title="Warning",
            summary="Warning",
            vault_id="main",
            occurred_at=None,
            sort_key="no-time:main:warning",
            evidence=(),
            store_revisions=(),
            warnings=(),
        )

    item = TimelineItem(
        item_id=stable_timeline_item_id(
            origin="document_snapshot_change",
            vault_id="main",
            source_kind="document",
            document_id="doc-1",
            backend_kind=None,
            path_or_scope="wiki/page.md",
            revision="metadata-1",
            occurred_at="2026-06-18T00:00:00+00:00",
        ),
        origin="document_snapshot_change",
        title="Indexed document: wiki/page.md",
        summary="Indexed document state changed.",
        vault_id="main",
        occurred_at="2026-06-18T00:00:00+00:00",
        sort_key="2026-06-18T00:00:00+00:00",
        evidence=(
            TimelineEvidenceRef(
                source_kind="document",
                vault_id="main",
                document_id="doc-1",
                path="wiki/page.md",
                content_hash="hash",
            ),
        ),
        store_revisions=(),
        warnings=(warning,),
    )
    projection = RecentChangesProjection(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        since=None,
        limit=20,
        vaults=(
            TimelineVault(
                vault_id="main",
                display_name="Main",
                items=(item,),
                warnings=(),
                store_revisions=(),
                freshness="fresh",
            ),
        ),
        warnings=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )

    assert projection.vaults[0].items[0].origin == "document_snapshot_change"
    assert item.item_id.startswith("timeline:document_snapshot_change:")


def test_parse_timeline_since_normalizes_naive_values_to_utc() -> None:
    assert parse_timeline_since("2026-06-18T00:00:00") == "2026-06-18T00:00:00+00:00"

    with pytest.raises(MemoryProjectionError, match="invalid_timeline_since"):
        parse_timeline_since("not-a-date")


def test_recent_changes_uses_bounded_recent_documents_and_groups_by_vault(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main", "work"))
    main = replace(
        make_document("main", "wiki/page.md", "hash-main"),
        last_seen_at="2026-06-18T00:00:00+00:00",
        last_indexed_at="2026-06-18T01:00:00+00:00",
        index_revision="metadata-main",
    )
    work = replace(
        make_document("work", "wiki/page.md", "hash-work"),
        last_seen_at="2026-06-18T00:30:00+00:00",
        last_indexed_at="2026-06-18T01:30:00+00:00",
        index_revision="metadata-work",
    )
    metadata = FakeMetadataStore((main, work))
    status = FakeStatusService()
    service = TimelineMemoryService(
        catalog=catalog,
        metadata_store=cast(MetadataStore, metadata),
        status_service=status,
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
        limit=5,
    )

    assert [vault.vault_id for vault in projection.vaults] == ["main", "work"]
    assert all(
        sum(1 for item in vault.items if item.origin == "document_snapshot_change") == 1 for vault in projection.vaults
    )
    assert len(metadata.recent_calls) == 2
    assert all(cast(int, call["limit"]) == 5 for call in metadata.recent_calls)
    assert [cast(QueryScope, call).vault_ids for call in status.calls] == [("main",), ("work",)]


def test_recent_changes_since_excludes_untimestamped_status_items_with_visible_warning(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main",))
    document = replace(
        make_document("main", "wiki/page.md", "hash"),
        last_seen_at="2026-06-17T00:00:00+00:00",
        last_indexed_at=None,
    )
    service = TimelineMemoryService(
        catalog=catalog,
        metadata_store=cast(MetadataStore, FakeMetadataStore((document,))),
        status_service=FakeStatusService(),
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )

    projection = service.recent_changes(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        since="2026-06-18T00:00:00+00:00",
    )

    assert all(item.occurred_at is not None for vault in projection.vaults for item in vault.items)
    assert any(warning.code == "timeline_items_without_timestamps_excluded" for warning in projection.warnings)


def test_recent_changes_fails_when_metadata_status_or_listing_is_unavailable(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main",))
    scope = QueryScope(vault_ids=("main",), content_scopes=("wiki",))

    with pytest.raises(MemoryProjectionError, match="metadata_unavailable"):
        TimelineMemoryService(
            catalog=catalog,
            metadata_store=cast(MetadataStore, FakeMetadataStore(())),
            status_service=FakeStatusService(metadata_ok=False),
        ).recent_changes(requested_scope=scope)

    with pytest.raises(MemoryProjectionError, match="metadata_unavailable"):
        TimelineMemoryService(
            catalog=catalog,
            metadata_store=cast(MetadataStore, FailingMetadataStore(())),
            status_service=FakeStatusService(),
        ).recent_changes(requested_scope=scope)


def test_recent_changes_reports_vector_unavailable_when_vector_is_not_configured(tmp_path: Path) -> None:
    catalog = make_catalog(tmp_path, ("main",))
    status_report = replace(
        make_status_report(),
        vector_ok=False,
        vector_backend="none",
        vector_schema_compatible=False,
        vector_message="not configured",
        vector_revision=None,
        vector_last_success_at=None,
        vector_last_error_at=None,
    )

    projection = TimelineMemoryService(
        catalog=catalog,
        metadata_store=cast(MetadataStore, FakeMetadataStore(())),
        status_service=StaticStatusService(status_report),
    ).recent_changes(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert any(
        warning.code == "vector_unavailable"
        for vault in projection.vaults
        for item in vault.items
        for warning in item.warnings
    )


def make_catalog(tmp_path: Path, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        (root / "wiki").mkdir(parents=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, display_name=vault_id.title()))
    return VaultCatalog.from_entries(entries=tuple(entries), active_vault_id=vault_ids[0])


def make_warning() -> MemoryWarning:
    return MemoryWarning(
        code="timeline_warning",
        message="Timeline warning",
        severity="warning",
        affected_vault_ids=("main",),
        recovery_hint="Check status.",
    )


def _document_time(document: DocumentSnapshot) -> str | None:
    return document.last_indexed_at or document.last_seen_at


def _document_after(document: DocumentSnapshot, since: str) -> bool:
    timestamp = _document_time(document)
    return timestamp is not None and timestamp > since
