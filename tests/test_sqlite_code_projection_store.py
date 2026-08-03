import hashlib
import sqlite3
from pathlib import Path

import pytest

from vault_graph.code_index.code_models import (
    CODE_PARSER_SPEC_VERSION,
    CODE_PROJECTION_SCHEMA_VERSION,
    CodeEdgeRecord,
    CodeFileSnapshot,
    CodeManifest,
    CodeReconcilePlan,
    CodeSymbolQuery,
    CodeSymbolRecord,
    CodeTraversalQuery,
    code_file_identity,
)
from vault_graph.storage.local.sqlite_code_projection_store import (
    CODE_SQLITE_BACKEND,
    SQLiteCodeProjectionStore,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _plan(*, generation_id: str = "generation-1", target_symbol_id: str | None = "symbol-b") -> CodeReconcilePlan:
    file_id = code_file_identity("repo-a", "lib/example.py")
    file_snapshot = CodeFileSnapshot(
        repository_id="repo-a",
        relative_path="lib/example.py",
        language="python",
        content_hash=_digest("source"),
        byte_count=6,
        line_count=3,
        source_revision="working-tree:1",
        is_test_file=False,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    symbol_a = CodeSymbolRecord(
        symbol_id="symbol-a",
        repository_id="repo-a",
        file_id=file_id,
        kind="function",
        language_kind="function_definition",
        name="alpha",
        qualified_name="example.alpha",
        signature="def alpha()",
        start_line=1,
        end_line=1,
        start_column=0,
        end_column=12,
        content_hash=file_snapshot.content_hash,
        source_revision=file_snapshot.source_revision,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    symbol_b = CodeSymbolRecord(
        symbol_id="symbol-b",
        repository_id="repo-a",
        file_id=file_id,
        kind="function",
        language_kind="function_definition",
        name="beta",
        qualified_name="example.beta",
        signature="def beta()",
        start_line=2,
        end_line=2,
        start_column=0,
        end_column=11,
        content_hash=file_snapshot.content_hash,
        source_revision=file_snapshot.source_revision,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    edge = CodeEdgeRecord(
        edge_id="edge-a-b",
        repository_id="repo-a",
        source_symbol_id="symbol-a",
        relation_kind="CALLS",
        target_symbol_id=target_symbol_id,
        unresolved_target_key=None if target_symbol_id else "missing.beta",
        extraction_status="extracted" if target_symbol_id else "unresolved",
        anchor_start_line=1,
        anchor_start_column=4,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    manifest = CodeManifest(
        generation_id=generation_id,
        schema_version=CODE_PROJECTION_SCHEMA_VERSION,
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
        repository_ids=("repo-a",),
        policy_revision="policy-1",
        source_revisions=(("repo-a", file_snapshot.source_revision),),
        file_ids=(file_id,),
    )
    return CodeReconcilePlan(
        manifest=manifest,
        files=(file_snapshot,),
        symbols=(symbol_a, symbol_b),
        edges=(edge,),
        run_id="run-1",
    )


def test_sqlite_code_store_initializes_required_schema_without_source_body(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)

    assert store.health().ok is True
    assert store.health().backend == CODE_SQLITE_BACKEND
    with sqlite3.connect(path) as connection:
        tables = {
            str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        }
        assert {
            "repositories",
            "files",
            "symbols",
            "edges",
            "pending_references",
            "symbol_fts",
            "projection_runs",
            "file_fingerprints",
        } <= tables
        for table in ("repositories", "files", "symbols", "edges", "pending_references"):
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
            assert not columns.intersection({"body", "source_body", "excerpt", "source_excerpt", "text"})


def test_sqlite_code_store_reconciles_and_searches_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()

    result = store.apply_reconcile_plan(plan)
    readonly = SQLiteCodeProjectionStore.open_read_only(path)

    assert result.generation_id == "generation-1"
    assert result.activated is False
    assert result.file_count == 1
    assert result.symbol_count == 2
    assert result.edge_count == 1
    assert readonly.get_symbol("symbol-a") == plan.symbols[0]
    assert [hit.symbol_id for hit in readonly.search_symbols(CodeSymbolQuery("example"))] == ["symbol-a", "symbol-b"]
    assert readonly.current_manifest(("repo-a",)).file_ids == plan.manifest.file_ids


def test_sqlite_code_store_rejects_dangling_or_cross_repository_edges(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)

    with pytest.raises(ValueError, match="target_symbol_id"):
        store.apply_reconcile_plan(_plan(target_symbol_id="missing"))


def test_sqlite_code_store_read_only_open_does_not_create_missing_state(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_read_only(path)

    assert store.health().ok is False
    assert store.health().schema_compatible is False
    assert not path.exists()
    assert not path.parent.exists()


def test_sqlite_code_store_reports_dangling_endpoint_health_failure(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    store.apply_reconcile_plan(_plan())
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM symbols WHERE symbol_id = 'symbol-b'")

    health = SQLiteCodeProjectionStore.open_read_only(path).health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "dangling" in health.message


def test_sqlite_code_store_rejects_writes_when_open_read_only(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    SQLiteCodeProjectionStore.open_writable(path)
    readonly = SQLiteCodeProjectionStore.open_read_only(path)

    with pytest.raises(PermissionError):
        readonly.apply_reconcile_plan(_plan())


def test_sqlite_code_store_traverses_confident_edges(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    store.apply_reconcile_plan(_plan())

    result = store.traverse(CodeTraversalQuery("symbol-a", direction="outbound"))

    assert [hit.symbol_id for hit in result.hits] == ["symbol-b"]
    assert [edge.edge_id for edge in result.edges] == ["edge-a-b"]
