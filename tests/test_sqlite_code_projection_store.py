import hashlib
import json
import sqlite3
from dataclasses import replace
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
    PendingCodeReference,
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


def test_sqlite_code_store_rejects_cross_repository_resolved_edge(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    other_file_id = code_file_identity("repo-b", "lib/other.py")
    other_file = replace(
        plan.files[0],
        repository_id="repo-b",
        relative_path="lib/other.py",
        content_hash=_digest("other-source"),
    )
    other_symbol = replace(
        plan.symbols[1],
        symbol_id="symbol-c",
        repository_id="repo-b",
        file_id=other_file_id,
        qualified_name="other.gamma",
        name="gamma",
        content_hash=other_file.content_hash,
    )
    cross_repository_edge = replace(plan.edges[0], edge_id="cross-repository", target_symbol_id="symbol-c")
    manifest = replace(
        plan.manifest,
        repository_ids=("repo-a", "repo-b"),
        source_revisions=(("repo-a", plan.files[0].source_revision), ("repo-b", other_file.source_revision)),
        file_ids=(plan.manifest.file_ids[0], other_file_id),
    )
    cross_repository_plan = CodeReconcilePlan(
        manifest=manifest,
        files=(*plan.files, other_file),
        symbols=(*plan.symbols, other_symbol),
        edges=(cross_repository_edge,),
        run_id="cross-repository-run",
    )

    with pytest.raises(ValueError, match="same repository"):
        store.apply_reconcile_plan(cross_repository_plan)


def test_sqlite_code_store_rejects_file_parser_mismatch_with_manifest(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    mismatched_file = replace(plan.files[0], parser_spec_version="other-parser-v1")
    mismatched_plan = CodeReconcilePlan(
        manifest=plan.manifest,
        files=(mismatched_file,),
        symbols=plan.symbols,
        edges=plan.edges,
        run_id="mismatched-file-parser-run",
    )

    with pytest.raises(ValueError, match="parser spec version"):
        store.apply_reconcile_plan(mismatched_plan)


def test_sqlite_code_store_rejects_symbol_source_identity_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    mismatched_symbol = replace(plan.symbols[0], content_hash=_digest("different-source"))
    mismatched_plan = CodeReconcilePlan(
        manifest=plan.manifest,
        files=plan.files,
        symbols=(mismatched_symbol, plan.symbols[1]),
        edges=plan.edges,
        run_id="mismatched-symbol-source-run",
    )

    with pytest.raises(ValueError, match="symbol source identity"):
        store.apply_reconcile_plan(mismatched_plan)


def test_sqlite_code_store_rejects_manifest_source_revision_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    mismatched_manifest = replace(plan.manifest, source_revisions=(("repo-a", "working-tree:2"),))
    mismatched_plan = replace(plan, manifest=mismatched_manifest, run_id="mismatched-revision-run")

    with pytest.raises(ValueError, match="source revision"):
        store.apply_reconcile_plan(mismatched_plan)


def test_sqlite_code_store_rejects_edge_and_pending_parser_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    mismatched_edge = replace(plan.edges[0], parser_spec_version="other-parser-v1")
    edge_plan = replace(plan, edges=(mismatched_edge,), run_id="mismatched-edge-parser-run")
    with pytest.raises(ValueError, match="parser spec version"):
        store.apply_reconcile_plan(edge_plan)

    pending = PendingCodeReference(
        pending_id="pending-parser-mismatch",
        repository_id="repo-a",
        reference_id="reference-parser-mismatch",
        source_revision="working-tree:1",
        relation_kind="CALLS",
        target_key="missing.gamma",
        reason="unresolved",
        parser_spec_version="other-parser-v1",
    )
    pending_plan = replace(plan, edges=(), pending_references=(pending,), run_id="mismatched-pending-parser-run")
    with pytest.raises(ValueError, match="parser spec version"):
        store.apply_reconcile_plan(pending_plan)


def test_sqlite_code_store_rejects_duplicate_edge_id_before_transaction(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    duplicate_edges = CodeReconcilePlan(
        manifest=plan.manifest,
        files=plan.files,
        symbols=plan.symbols,
        edges=(plan.edges[0], plan.edges[0]),
        run_id="duplicate-edge-run",
    )

    with pytest.raises(ValueError, match="duplicate edge identity"):
        store.apply_reconcile_plan(duplicate_edges)

    assert store.health().ok is True
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM edges").fetchone()[0] == 0


def test_sqlite_code_store_rejects_duplicate_pending_id_before_transaction(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    plan = _plan()
    pending = PendingCodeReference(
        pending_id="pending-1",
        repository_id="repo-a",
        reference_id="reference-1",
        source_revision="working-tree:1",
        relation_kind="CALLS",
        target_key="missing.gamma",
        reason="unresolved",
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    duplicate_pending = CodeReconcilePlan(
        manifest=plan.manifest,
        files=plan.files,
        symbols=plan.symbols,
        edges=plan.edges,
        pending_references=(pending, pending),
        run_id="duplicate-pending-run",
    )

    with pytest.raises(ValueError, match="duplicate pending reference identity"):
        store.apply_reconcile_plan(duplicate_pending)

    assert store.health().ok is True
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM pending_references").fetchone()[0] == 0


def test_sqlite_code_store_rejects_cross_repository_symbol_identity_collision(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    first = _plan()
    store.apply_reconcile_plan(first)
    other_file_id = code_file_identity("repo-b", "lib/other.py")
    other_file = replace(first.files[0], repository_id="repo-b", relative_path="lib/other.py")
    other_symbol = replace(first.symbols[0], repository_id="repo-b", file_id=other_file_id)
    other_manifest = replace(
        first.manifest,
        generation_id="generation-2",
        repository_ids=("repo-b",),
        file_ids=(other_file_id,),
        source_revisions=(("repo-b", other_file.source_revision),),
    )
    second = CodeReconcilePlan(
        manifest=other_manifest,
        files=(other_file,),
        symbols=(other_symbol,),
        edges=(),
        run_id="cross-repository-symbol-collision",
    )

    with pytest.raises(ValueError, match="symbol identity.*another repository"):
        store.apply_reconcile_plan(second)


def test_sqlite_code_store_rejects_cross_repository_edge_and_pending_identity_collisions(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    first = _plan()
    initial_pending = PendingCodeReference(
        pending_id="pending-1",
        repository_id="repo-a",
        reference_id="repo-a-reference",
        source_revision=first.files[0].source_revision,
        relation_kind="CALLS",
        target_key="missing.gamma",
        reason="unresolved",
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    store.apply_reconcile_plan(replace(first, pending_references=(initial_pending,)))
    other_file_id = code_file_identity("repo-b", "lib/other.py")
    other_file = replace(first.files[0], repository_id="repo-b", relative_path="lib/other.py")
    other_symbol = replace(first.symbols[0], repository_id="repo-b", file_id=other_file_id, symbol_id="repo-b-symbol")
    other_manifest = replace(
        first.manifest,
        generation_id="generation-2",
        repository_ids=("repo-b",),
        file_ids=(other_file_id,),
        source_revisions=(("repo-b", other_file.source_revision),),
    )
    edge_collision = replace(
        first.edges[0],
        repository_id="repo-b",
        source_symbol_id=other_symbol.symbol_id,
        target_symbol_id=None,
        unresolved_target_key="missing.gamma",
        extraction_status="unresolved",
    )
    edge_plan = CodeReconcilePlan(
        manifest=other_manifest,
        files=(other_file,),
        symbols=(other_symbol,),
        edges=(edge_collision,),
        run_id="cross-repository-edge-collision",
    )
    with pytest.raises(ValueError, match="edge identity.*another repository"):
        store.apply_reconcile_plan(edge_plan)

    pending_collision = PendingCodeReference(
        pending_id="pending-1",
        repository_id="repo-b",
        reference_id="repo-b-reference",
        source_revision=other_file.source_revision,
        relation_kind="CALLS",
        target_key="missing.gamma",
        reason="unresolved",
        parser_spec_version=CODE_PARSER_SPEC_VERSION,
    )
    pending_plan = CodeReconcilePlan(
        manifest=other_manifest,
        files=(other_file,),
        symbols=(other_symbol,),
        edges=(),
        pending_references=(pending_collision,),
        run_id="cross-repository-pending-collision",
    )
    with pytest.raises(ValueError, match="pending reference identity.*another repository"):
        store.apply_reconcile_plan(pending_plan)


def test_sqlite_code_store_rejects_deletion_outside_manifest_repository_scope(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    first = _plan()
    store.apply_reconcile_plan(first)
    other_manifest = replace(
        first.manifest,
        generation_id="generation-2",
        repository_ids=("repo-b",),
        source_revisions=(("repo-b", "working-tree:2"),),
        file_ids=(),
    )
    deletion_plan = CodeReconcilePlan(
        manifest=other_manifest,
        files=(),
        symbols=(),
        edges=(),
        deleted_file_ids=first.manifest.file_ids,
        run_id="cross-repository-deletion",
    )

    with pytest.raises(ValueError, match="deleted file.*repository scope"):
        store.apply_reconcile_plan(deletion_plan)


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


def test_sqlite_code_store_reports_manifest_file_identity_health_failure(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    store.apply_reconcile_plan(_plan())
    with sqlite3.connect(path) as connection:
        manifest_row = connection.execute("SELECT value FROM code_metadata WHERE key = 'manifest_json'").fetchone()
        assert manifest_row is not None
        payload = json.loads(str(manifest_row[0]))
        payload["file_ids"] = ["missing-file-id"]
        connection.execute(
            "UPDATE code_metadata SET value = ? WHERE key = 'manifest_json'",
            (json.dumps(payload),),
        )

    health = SQLiteCodeProjectionStore.open_read_only(path).health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "manifest" in health.message


def test_sqlite_code_store_reports_manifest_source_revision_health_failure(tmp_path: Path) -> None:
    path = tmp_path / "code.sqlite3"
    store = SQLiteCodeProjectionStore.open_writable(path)
    store.apply_reconcile_plan(_plan())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE repositories SET source_revision = 'working-tree:tampered' WHERE repository_id = 'repo-a'"
        )

    health = SQLiteCodeProjectionStore.open_read_only(path).health()

    assert health.ok is False
    assert health.schema_compatible is False
    assert "source revision" in health.message


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
