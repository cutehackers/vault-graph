from pathlib import Path

import pytest

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_vector_indexer import SPEC
from vault_graph.app.graph_readiness_service import ReadOnlyGraphReadiness
from vault_graph.app.index_service import IndexService
from vault_graph.embeddings.text_embeddings import EmbeddingInput, EmbeddingVector
from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.indexing.graph_indexer import GraphIndexApplyResult, GraphIndexPlanReport
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.storage.local.graph_status_store import (
    LocalGraphStatusStore,
    graph_scope_status_key,
    graph_spec_key,
)
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def catalog_for(root: Path, *, content_scopes: tuple[str, ...] = ("wiki",)) -> VaultCatalog:
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root, content_scopes=content_scopes)],
        active_vault_id="default",
    )


def test_run_plan_returns_graph_counts_without_applying(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "---\ntags: [GraphRAG]\n---\n# Page\nBody\n")
    catalog = catalog_for(vault_root)
    graph_store = InMemoryGraphStore()
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        graph_store=graph_store,
    )

    report = service.run_plan(scope=catalog.default_scope())

    assert isinstance(report.graph, GraphIndexPlanReport)
    assert report.graph.reconcile_plan.entity_upserts
    assert graph_store.current_manifest((catalog.default_scope(),)).entity_rows == ()


def test_run_apply_writes_graph_after_metadata(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    graph_store = InMemoryGraphStore()
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        graph_store=graph_store,
    )

    report = service.run_apply(scope=catalog.default_scope())

    assert isinstance(report.graph, GraphIndexApplyResult)
    assert report.graph.failed is False
    assert graph_store.current_manifest((catalog.default_scope(),)).entity_rows


def test_vector_failure_still_allows_graph_apply(tmp_path: Path) -> None:
    class FailingEmbeddings(DeterministicTextEmbeddings):
        def embed(self, inputs: tuple[EmbeddingInput, ...]) -> tuple[EmbeddingVector, ...]:
            raise RuntimeError("model unavailable")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    graph_store = InMemoryGraphStore()
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        vector_store=InMemoryVectorStore(),
        text_embeddings=FailingEmbeddings(SPEC),
        graph_store=graph_store,
    )

    report = service.run_apply(scope=catalog.default_scope())

    assert report.exit_code == 1
    assert getattr(report.vector, "failed", False) is True
    assert isinstance(report.graph, GraphIndexApplyResult)
    assert report.graph.failed is False
    assert graph_store.current_manifest((catalog.default_scope(),)).entity_rows


def test_graph_failure_sets_exit_code_and_status(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    status_store = LocalGraphStatusStore(tmp_path / "state" / "graph" / "status.json")
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        graph_store=InMemoryGraphStore(read_only=True),
        graph_status_store=status_store,
    )

    report = service.run_apply(scope=catalog.default_scope())
    status = status_store.read(
        scope_key=graph_scope_status_key(catalog.default_scope()),
        graph_spec_key=graph_spec_key(current_graph_extraction_spec()),
    )

    assert report.exit_code == 1
    assert isinstance(report.graph, GraphIndexApplyResult)
    assert report.graph.failed is True
    assert status.last_error is not None


def test_metadata_failure_prevents_graph_indexing(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    graph_store = InMemoryGraphStore()
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "missing" / "metadata.sqlite3"),
        graph_store=graph_store,
    )

    with pytest.raises(FileNotFoundError):
        service.run_apply(scope=catalog.default_scope())

    assert graph_store.current_manifest((catalog.default_scope(),)).entity_rows == ()


def test_delete_reconcile_reports_fresh_readiness_and_does_not_double_count_tombstones(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    page = vault_root / "wiki" / "page.md"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    graph_store = InMemoryGraphStore()
    service = IndexService(catalog=catalog, metadata_store=metadata_store, graph_store=graph_store)
    scope = catalog.default_scope()
    service.run_apply(scope=scope)

    page.unlink()
    service.run_apply(scope=scope)
    repeat_report = service.run_apply(scope=scope)
    manifest = graph_store.current_manifest((scope,))
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    ).check(requested_scope=scope, actual_scopes=(scope,))

    assert readiness.freshness == "fresh"
    assert readiness.tombstone_count == len(manifest.tombstone_rows)
    assert isinstance(repeat_report.graph, GraphIndexApplyResult)
    assert repeat_report.graph.reconcile_plan is not None
    assert repeat_report.graph.reconcile_plan.entity_tombstones == ()
    assert repeat_report.graph.reconcile_plan.relationship_tombstones == ()


def test_changed_content_reindex_reports_fresh_with_zero_stale_count(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    metadata_store = SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True)
    graph_store = InMemoryGraphStore()
    service = IndexService(catalog=catalog, metadata_store=metadata_store, graph_store=graph_store)
    scope = catalog.default_scope()
    service.run_apply(scope=scope)

    write_page(vault_root, "wiki/page.md", "# Page\nChanged body\n")
    service.run_apply(scope=scope)
    readiness = ReadOnlyGraphReadiness(
        metadata_store=metadata_store,
        graph_store=graph_store,
        expected_spec=current_graph_extraction_spec(),
    ).check(requested_scope=scope, actual_scopes=(scope,))

    assert readiness.freshness == "fresh"
    assert readiness.stale_count == 0


def test_unsupported_content_scope_returns_graph_failure_without_touching_graph_store(tmp_path: Path) -> None:
    class TrapGraphStore(InMemoryGraphStore):
        def current_manifest(self, scopes: tuple[QueryScope, ...]):  # type: ignore[no-untyped-def]
            raise AssertionError("current_manifest should not be called")

        def apply_reconcile_plan(self, plan):  # type: ignore[no-untyped-def]
            raise AssertionError("apply_reconcile_plan should not be called")

    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/sub/page.md", "# Page\nBody\n")
    catalog = catalog_for(vault_root)
    service = IndexService(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(tmp_path / "state" / "metadata.sqlite3", initialize=True),
        graph_store=TrapGraphStore(),
    )

    report = service.run_plan(scope=QueryScope(vault_ids=("default",), content_scopes=("wiki/sub",)))

    assert isinstance(report.graph, GraphIndexApplyResult)
    assert report.graph.failed is True
    assert "unsupported_graph_scope_width" in (report.graph.error or "")
