from pathlib import Path

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_graph_store_contract import make_entity, make_plan
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.errors import GraphStoreUnavailable
from vault_graph.graph.graph_contracts import GraphManifest, current_graph_extraction_spec
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def metadata_store_with_chunk(
    tmp_path: Path,
    *,
    vault_id: str = "default",
    index_revision: str = "metadata-1",
) -> SQLiteMetadataStore:
    store, _, _, _ = metadata_store_with_chunk_ids(tmp_path, vault_id=vault_id, index_revision=index_revision)
    return store


def metadata_store_with_chunk_ids(
    tmp_path: Path,
    *,
    vault_id: str = "default",
    index_revision: str = "metadata-1",
) -> tuple[SQLiteMetadataStore, str, str, str]:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    document = make_document(vault_id, "wiki/page.md", "hash")
    document = type(document)(
        vault_id=document.vault_id,
        document_id=document.document_id,
        path=document.path,
        kind=document.kind,
        frontmatter=document.frontmatter,
        frontmatter_hash=document.frontmatter_hash,
        content_hash=document.content_hash,
        raw_sha256=document.raw_sha256,
        parser_version="markdown-frontmatter-v1",
        last_seen_at=document.last_seen_at,
        last_indexed_at=document.last_indexed_at,
        vault_revision=document.vault_revision,
        index_revision=document.index_revision,
    )
    chunk = make_chunk(vault_id, document.document_id, document.path)
    chunk = type(chunk)(
        vault_id=chunk.vault_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        path=chunk.path,
        section=chunk.section,
        anchor=chunk.anchor,
        text=chunk.text,
        token_count=chunk.token_count,
        content_hash=chunk.content_hash,
        chunker_version="heading-section-v1",
        index_revision=index_revision,
    )
    store.apply_metadata_revision(index_revision=index_revision, documents=[document], chunks=[chunk], tombstones=[])
    return store, document.document_id, chunk.chunk_id, chunk.content_hash


def test_graph_readiness_reports_missing_graph_store(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore(
        health_override=StoreHealth(
            ok=False,
            backend="memory-graph",
            schema_version="memory-graph-v1",
            schema_compatible=False,
            message="not initialized",
        )
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.backend_name == "memory-graph"
    assert report.backend_available is False
    assert report.freshness == "missing"
    assert "run `vg index`" in report.recovery_hint


def test_graph_readiness_reports_empty_when_store_has_no_revision(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=InMemoryGraphStore(),
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "empty"
    assert report.last_graph_revision is None


def test_graph_readiness_reports_unavailable_when_manifest_read_fails(tmp_path: Path) -> None:
    class FailingGraphStore(InMemoryGraphStore):
        def current_manifest(self, scopes: tuple[QueryScope, ...]) -> GraphManifest:
            raise GraphStoreUnavailable("graph read failed")

    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = FailingGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "unavailable"
    assert "graph read failed" in report.recovery_hint


def test_graph_readiness_short_circuits_when_metadata_health_is_incompatible() -> None:
    class BrokenMetadataStore:
        def health(self) -> StoreHealth:
            return StoreHealth(
                ok=False,
                backend="sqlite",
                schema_version="metadata-v1",
                schema_compatible=False,
                message="metadata incompatible",
            )

        def list_chunks(self, scope: QueryScope) -> object:
            raise AssertionError("list_chunks should not be called when metadata is unhealthy")

        def list_document_states(self, vault_ids: tuple[str, ...]) -> object:
            raise AssertionError("list_document_states should not be called when metadata is unhealthy")

        def resolve_chunk_evidence(self, *, vault_id: str, document_id: str, chunk_id: str) -> object:
            raise AssertionError("resolve_chunk_evidence should not be called when metadata is unhealthy")

    service = ReadOnlyGraphReadiness(
        metadata_store=BrokenMetadataStore(),  # type: ignore[arg-type]
        graph_store=InMemoryGraphStore(),
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "unavailable"
    assert "metadata unavailable" in report.warnings[0]


def test_graph_readiness_reports_fresh_when_lineage_matches(tmp_path: Path) -> None:
    metadata_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity(
        "default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "fresh"
    assert report.graph_extraction_spec_compatible is True
    assert report.stale_count == 0
    assert report.tombstone_count == 0
    assert report.last_graph_revision == "graph-1"


def test_graph_readiness_reports_fresh_with_sqlite_graph_store_opened_read_only(tmp_path: Path) -> None:
    metadata_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(tmp_path)
    graph_path = tmp_path / "graph.sqlite3"
    writable_graph_store = SQLiteGraphStore.open_writable(graph_path)
    entity = make_entity(
        "default",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    writable_graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=SQLiteGraphStore.open_read_only(graph_path),
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.backend_name == "sqlite-graph"
    assert report.freshness == "fresh"
    assert report.last_graph_revision == "graph-1"


def test_graph_readiness_reports_scope_rows_for_all_vaults(tmp_path: Path) -> None:
    first_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(
        tmp_path,
        vault_id="first",
        index_revision="metadata-1",
    )
    graph_store = InMemoryGraphStore()
    first_entity = make_entity(
        "first",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    graph_store.apply_reconcile_plan(
        make_plan(
            entities=(first_entity,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
        )
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=first_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        actual_scopes=(
            QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
            QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        ),
    )

    assert report.freshness == "empty"
    assert tuple((row.vault_id, row.freshness) for row in report.scope_readiness) == (
        ("first", "fresh"),
        ("second", "empty"),
    )
    assert tuple(row.last_graph_revision for row in report.scope_readiness) == ("graph-1", None)


def test_graph_readiness_keeps_evidence_warnings_scope_local(tmp_path: Path) -> None:
    metadata_store, document_id, chunk_id, content_hash = metadata_store_with_chunk_ids(
        tmp_path,
        vault_id="first",
        index_revision="metadata-1",
    )
    second_store, second_document_id, second_chunk_id, second_content_hash = metadata_store_with_chunk_ids(
        tmp_path / "second",
        vault_id="second",
        index_revision="metadata-1",
    )
    second_document = second_store.resolve_document(second_document_id)
    second_chunk = second_store.resolve_chunk(vault_id="second", chunk_id=second_chunk_id)
    assert second_document is not None
    assert second_chunk is not None
    metadata_store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[second_document],
        chunks=[second_chunk],
        tombstones=[],
    )
    graph_store = InMemoryGraphStore()
    first_entity = make_entity(
        "first",
        document_id=document_id,
        chunk_id=chunk_id,
        content_hash=content_hash,
        path="wiki/page.md",
    )
    second_entity = make_entity(
        "second",
        document_id=second_document_id,
        chunk_id=second_chunk_id,
        content_hash=second_content_hash,
        path="wiki/page.md",
    )
    missing_entity = make_entity("first", name="Missing", document_id="missing-doc", chunk_id="missing-chunk")
    graph_store.apply_reconcile_plan(
        make_plan(
            entities=(first_entity, missing_entity),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
        )
    )
    graph_store.apply_reconcile_plan(
        make_plan(
            entities=(second_entity,),
            relationships=(),
            scope=QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        )
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        actual_scopes=(
            QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
            QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        ),
    )

    assert tuple((row.vault_id, row.freshness) for row in report.scope_readiness) == (
        ("first", "stale"),
        ("second", "fresh"),
    )


def test_graph_readiness_reports_stale_when_graph_evidence_is_unresolved(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity("default", document_id="missing-doc", chunk_id="missing-chunk")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "stale"
    assert any("unresolved graph evidence" in warning for warning in report.warnings)
    assert "rerun metadata indexing, then graph indexing" in report.recovery_hint


def test_graph_readiness_reports_stale_when_metadata_revision_changes(tmp_path: Path) -> None:
    old_metadata = metadata_store_with_chunk(tmp_path / "old", index_revision="metadata-1")
    graph_store = InMemoryGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    new_metadata = metadata_store_with_chunk(tmp_path / "new", index_revision="metadata-2")
    service = ReadOnlyGraphReadiness(
        metadata_store=new_metadata,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert old_metadata.health().ok is True
    assert report.freshness == "stale"
    assert "rerun `vg index`" in report.recovery_hint


def test_graph_readiness_reports_incompatible_when_spec_digest_conflicts(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    different_spec = current_graph_extraction_spec().__class__.from_payload(
        {
            **current_graph_extraction_spec().payload(),
            "entity_schema_version": "entity-schema-v2",
        }
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=different_spec,
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "incompatible"
    assert report.graph_extraction_spec_compatible is False


def test_graph_readiness_reports_incompatible_when_spec_version_changes_without_policy(tmp_path: Path) -> None:
    metadata_store = metadata_store_with_chunk(tmp_path)
    graph_store = InMemoryGraphStore()
    entity = make_entity("default")
    graph_store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))
    different_spec = current_graph_extraction_spec().__class__.from_payload(
        {
            **current_graph_extraction_spec().payload(),
            "spec_version": "graph-extraction-spec-v3",
        }
    )
    service = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=different_spec,
    )

    report = service.check(
        requested_scope=QueryScope(vault_ids=("default",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),),
    )

    assert report.freshness == "incompatible"
    assert report.graph_extraction_spec_compatible is False
