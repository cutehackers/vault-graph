from pathlib import Path

from vault_graph.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.graph_status_store import (
    LocalGraphStatusStore,
    graph_scope_status_key,
    graph_spec_key,
)


def test_graph_status_failure_preserves_previous_success(tmp_path: Path) -> None:
    path = tmp_path / "graph" / "status.json"
    store = LocalGraphStatusStore(path)
    scope_key = graph_scope_status_key(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    spec_key = graph_spec_key(current_graph_extraction_spec())

    store.record_success(scope_key=scope_key, graph_spec_key=spec_key, graph_index_revision="graph-1")
    store.record_failure(scope_key=scope_key, graph_spec_key=spec_key, error="graph failed")

    status = store.read(scope_key=scope_key, graph_spec_key=spec_key)
    assert status.last_success_revision == "graph-1"
    assert status.last_success_at is not None
    assert status.last_error == "graph failed"
    assert status.last_error_at is not None


def test_graph_status_success_clears_previous_error(tmp_path: Path) -> None:
    path = tmp_path / "graph" / "status.json"
    store = LocalGraphStatusStore(path)
    scope_key = graph_scope_status_key(QueryScope(vault_ids=("default",), content_scopes=("wiki",)))
    spec_key = graph_spec_key(current_graph_extraction_spec())

    store.record_failure(scope_key=scope_key, graph_spec_key=spec_key, error="graph failed")
    store.record_success(scope_key=scope_key, graph_spec_key=spec_key, graph_index_revision="graph-2")

    status = store.read(scope_key=scope_key, graph_spec_key=spec_key)
    assert status.last_success_revision == "graph-2"
    assert status.last_error is None
    assert status.last_error_at is None


def test_graph_status_read_does_not_create_file(tmp_path: Path) -> None:
    path = tmp_path / "graph" / "status.json"
    store = LocalGraphStatusStore(path)

    status = store.read(scope_key="scope", graph_spec_key="spec")

    assert status.scope_key == "scope"
    assert status.graph_spec_key == "spec"
    assert not path.exists()
    assert not path.parent.exists()
