import gc
import hashlib
import json
import os
import sqlite3
import tracemalloc
import weakref
from contextlib import closing
from pathlib import Path

import pytest
from graph_document import DocumentGraphSnapshot, GraphDocument, GraphLimits, ReadLimits
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import write_page
from tests.test_graph_module_public_integration import indexed_home
from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.app.graph_store_factory import document_store_path
from vault_graph.cli.main import app
from vault_graph.errors import GraphStoreUnavailable
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.graph.graph_query import GraphEntityIdentity, GraphEntityQuery, GraphRelationshipQuery
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.document_graph_store import DocumentGraphStore, _snapshot_plan
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

GRAPH_LIMITS = GraphLimits(10, 100000, 1000000, 1000, 1000, 10000, 1024)
READ_LIMITS = ReadLimits(1000, 1000, 10000, 100, 1000000)


def test_read_only_open_does_not_create_cache(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    with pytest.raises(GraphStoreUnavailable):
        DocumentGraphStore.open_read_only(
            cache,
            metadata_store=None,  # type: ignore[arg-type]
            graph_limits=GRAPH_LIMITS,
            read_limits=READ_LIMITS,
        )
    assert not cache.exists()


def test_bootstrap_reopens_with_legacy_query_contract_without_old_graph_db(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    old_store = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
    directory = home / "cache" / "document-store-test"
    writer = DocumentGraphStore.open_writable(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    writer.bootstrap_from_legacy(old_store, (scope,))
    writer.close()
    assert (directory / "compatibility.json").is_file()

    reader = DocumentGraphStore.open_read_only(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    assert reader.health() == old_store.health()
    assert reader.latest_revisions((scope,)) == old_store.latest_revisions((scope,))
    assert reader.current_manifest((scope,)) == old_store.current_manifest((scope,))
    query = GraphEntityQuery(text="Source", actual_scopes=(scope,), limit=20)
    assert reader.find_entities(query) == old_store.find_entities(query)
    found = reader.find_entities(query).matches[0].entity
    relationship_query = GraphRelationshipQuery(
        seeds=(GraphEntityIdentity(found.vault_id, found.entity_id),),
        actual_scopes=(scope,),
        direction="both",
        relationship_types=(),
        statuses=("stated", "inferred", "contested"),
        include_cross_vault=False,
        limit=100,
    )
    assert reader.relationships_for_entities(relationship_query) == old_store.relationships_for_entities(
        relationship_query
    )
    reader.close()

    (directory / "compatibility.json").write_text("{}", encoding="utf-8")
    with pytest.raises(GraphStoreUnavailable):
        DocumentGraphStore.open_read_only(
            directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
        )


def test_changed_chunk_keeps_only_live_evidence_and_ready_graph(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"]).exit_code == 0
    write_page(vault, "wiki/new.md", "# New\nNew evidence.\n")
    write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[new]].\n")
    result = runner.invoke(app, ["index", "--graph-home", str(home)])
    assert result.exit_code == 0, result.output

    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    store = DocumentGraphStore.open_read_only(
        document_store_path(catalog_service),
        metadata_store=metadata_store,
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=store,
        expected_spec=current_graph_extraction_spec(),
    ).check(requested_scope=scope, actual_scopes=(scope,))
    assert readiness.freshness == "fresh"
    live_refs = store.current_document_evidence_refs()
    live_ids = {ref.evidence_ref_id for ref in live_refs}
    source = store.find_entities(GraphEntityQuery(text="Source", actual_scopes=(scope,), limit=20)).matches[0].entity
    assert {ref.evidence_ref_id for ref in source.evidence_refs} <= live_ids
    for ref in live_refs:
        current = metadata_store.resolve_chunk_evidence(
            vault_id=ref.evidence_vault_id, document_id=ref.document_id, chunk_id=ref.chunk_id
        )
        assert current is not None and current.content_hash == ref.content_hash
    store.close()


def test_tampered_compatibility_alias_fails_closed(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    directory = tmp_path / "document-store"
    writer = DocumentGraphStore.open_writable(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    writer.bootstrap_from_legacy(SQLiteGraphStore.open_read_only(catalog_service.graph_path), (scope,))
    writer.close()
    marker = directory / "compatibility.json"
    wrapped = json.loads(marker.read_text(encoding="utf-8"))
    wrapped["payload"]["plans"][0]["entity_upserts"][0]["aliases"] = ["forged alias"]
    content = json.dumps(wrapped["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    wrapped["digest"] = hashlib.sha256(content.encode()).hexdigest()
    marker.write_text(json.dumps(wrapped), encoding="utf-8")
    with pytest.raises(GraphStoreUnavailable):
        DocumentGraphStore.open_read_only(
            directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
        )


def test_failed_publication_poisoned_writable_instance(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    writer = DocumentGraphStore.open_writable(
        tmp_path / "document-store", metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    writer.bootstrap_from_legacy(SQLiteGraphStore.open_read_only(catalog_service.graph_path), (scope,))

    def fail_publication(_state: object) -> None:
        raise OSError("injected publication failure")

    monkeypatch.setattr(writer, "_publish", fail_publication)
    with pytest.raises(GraphStoreUnavailable, match="injected publication failure"):
        writer.apply_reconcile_plan(_snapshot_plan(writer, scope))
    with pytest.raises(GraphStoreUnavailable, match="must be reopened"):
        writer.health()
    with pytest.raises(GraphStoreUnavailable, match="must be reopened"):
        writer.find_entities(GraphEntityQuery(text="Source", actual_scopes=(scope,), limit=20))
    writer.close()


@pytest.mark.parametrize("change", ["status", "collections"])
def test_recomputed_digest_cannot_hide_document_graph_state(
    tmp_path: Path, monkeypatch: MonkeyPatch, change: str
) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    directory = tmp_path / "document-store"
    writer = DocumentGraphStore.open_writable(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    writer.bootstrap_from_legacy(
        SQLiteGraphStore.open_read_only(catalog_service.graph_path),
        (catalog_service.load_catalog().default_scope(),),
    )
    writer.close()
    marker = directory / "compatibility.json"
    wrapped = json.loads(marker.read_text(encoding="utf-8"))
    if change == "status":
        wrapped["payload"]["plans"][0]["entity_upserts"][0]["status"] = "tombstoned"
    else:
        wrapped["payload"]["collections"] = {}
    content = json.dumps(wrapped["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    wrapped["digest"] = hashlib.sha256(content.encode()).hexdigest()
    marker.write_text(json.dumps(wrapped), encoding="utf-8")
    with pytest.raises(GraphStoreUnavailable):
        DocumentGraphStore.open_read_only(
            directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
        )


def test_close_and_collection_release_end_store_lifetime(tmp_path: Path) -> None:
    store = DocumentGraphStore.open_writable(
        tmp_path / "document-store",
        metadata_store=None,  # type: ignore[arg-type]
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    uri = store._query._uri
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'graph_entities'").fetchone()
    store.close()
    store.close()
    with pytest.raises(GraphStoreUnavailable, match="closed"):
        store.health()
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'graph_entities'").fetchone() is None

    collected = DocumentGraphStore.open_writable(
        tmp_path / "another-document-store",
        metadata_store=None,  # type: ignore[arg-type]
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    collected_uri = collected._query._uri
    reference = weakref.ref(collected)
    del collected
    gc.collect()
    assert reference() is None
    with closing(sqlite3.connect(collected_uri, uri=True)) as connection:
        assert connection.execute("SELECT name FROM sqlite_master WHERE name = 'graph_entities'").fetchone() is None


def test_small_manifest_read_does_not_allocate_configured_limit(tmp_path: Path) -> None:
    marker = tmp_path / "compatibility.json"
    payload = {"version": 1, "plans": [], "collections": {}}
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    marker.write_text(
        json.dumps({"payload": payload, "digest": hashlib.sha256(content.encode()).hexdigest()}),
        encoding="utf-8",
    )
    store = object.__new__(DocumentGraphStore)
    store._marker = marker
    store._read_only = True
    store._max_compat_bytes = 64 * 1024 * 1024
    tracemalloc.start()
    try:
        assert store._load_state() == payload
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024 * 1024
    store._max_compat_bytes = marker.stat().st_size - 1
    with pytest.raises(GraphStoreUnavailable, match="exceeds read limit"):
        store._load_state()


def test_manifest_shrinking_during_read_fails_closed(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    marker = tmp_path / "compatibility.json"
    payload = {"version": 1, "plans": [], "collections": {}}
    content = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    marker.write_text(
        json.dumps({"payload": payload, "digest": hashlib.sha256(content.encode()).hexdigest()}),
        encoding="utf-8",
    )
    store = object.__new__(DocumentGraphStore)
    store._marker = marker
    store._read_only = True
    store._max_compat_bytes = 1024
    original_fstat = os.fstat

    def shrink_after_stat(fd: int) -> os.stat_result:
        result = original_fstat(fd)
        marker.write_text("{}", encoding="utf-8")
        return result

    with monkeypatch.context() as patch:
        patch.setattr("vault_graph.storage.local.document_graph_store.os.fstat", shrink_after_stat)
        with pytest.raises(GraphStoreUnavailable, match="changed during read"):
            store._load_state()


def test_manifest_cache_is_scope_bounded_and_cleared_before_apply(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    other_scope = QueryScope(vault_ids=scope.vault_ids, content_scopes=("wiki",))
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    store = DocumentGraphStore.open_writable(
        tmp_path / "document-store",
        metadata_store=metadata_store,
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    store.bootstrap_from_legacy(SQLiteGraphStore.open_read_only(catalog_service.graph_path), (scope,))
    first = store.current_manifest((scope,))
    assert store.current_manifest((scope,)) is first
    assert first == store._query.current_manifest((scope,))
    second = store.current_manifest((other_scope,))
    assert second == store._query.current_manifest((other_scope,))
    assert second is store.current_manifest((other_scope,))
    assert store.current_manifest((scope,)) is not first
    before_apply = store.current_manifest((scope,))
    store.apply_reconcile_plan(_snapshot_plan(store, scope))
    after_apply = store.current_manifest((scope,))
    assert after_apply is not before_apply
    assert after_apply == store._query.current_manifest((scope,))
    store.close()


def test_cold_open_reads_each_document_revision_once(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    directory = tmp_path / "document-store"
    writer = DocumentGraphStore.open_writable(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    writer.bootstrap_from_legacy(SQLiteGraphStore.open_read_only(catalog_service.graph_path), (scope,))
    writer.close()
    original_read = GraphDocument.read
    reads = 0

    def count_read(
        self: GraphDocument, *, collection_id: str, selection: str | tuple[str, ...], limits: ReadLimits
    ) -> DocumentGraphSnapshot:
        nonlocal reads
        reads += 1
        return original_read(self, collection_id=collection_id, selection=selection, limits=limits)

    monkeypatch.setattr(GraphDocument, "read", count_read)
    reader = DocumentGraphStore.open_read_only(
        directory, metadata_store=metadata_store, graph_limits=GRAPH_LIMITS, read_limits=READ_LIMITS
    )
    assert reader.health().ok
    assert reads == 1
    reader.close()


def test_backend_bootstrap_failure_closes_store_and_preserves_active_generation(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from tests.test_graph_module_public_integration import fingerprints

    vault, home = indexed_home(tmp_path, monkeypatch)
    before_home = fingerprints(home)
    before_vault = fingerprints(vault)
    closed: list[DocumentGraphStore] = []
    original_close = DocumentGraphStore.close

    def fail_bootstrap(self: DocumentGraphStore, *args: object, **kwargs: object) -> None:
        raise RuntimeError("injected bootstrap failure")

    def record_close(self: DocumentGraphStore) -> None:
        closed.append(self)
        original_close(self)

    monkeypatch.setattr(DocumentGraphStore, "bootstrap_from_legacy", fail_bootstrap)
    monkeypatch.setattr(DocumentGraphStore, "close", record_close)
    result = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])

    assert result.exit_code != 0
    assert len(closed) == 1
    assert fingerprints(home) == before_home
    assert fingerprints(vault) == before_vault
