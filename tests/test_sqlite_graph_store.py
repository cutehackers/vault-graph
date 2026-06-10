import sqlite3
from pathlib import Path

import pytest

from tests.test_graph_store_contract import graph_store_contract, make_entity, make_plan
from vault_graph.errors import GraphReadOnlyViolation
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_graph_store import GRAPH_SCHEMA_VERSION, SQLiteGraphStore


def test_sqlite_graph_store_satisfies_contract(tmp_path: Path) -> None:
    graph_store_contract(lambda: SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3"))


def test_sqlite_graph_store_persists_records(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    writable = SQLiteGraphStore.open_writable(path)
    entity = make_entity("default")
    writable.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))

    readonly = SQLiteGraphStore.open_read_only(path)

    assert readonly.get_entity(vault_id="default", entity_id=entity.entity_id) == entity
    assert readonly.health().ok is True
    assert readonly.health().schema_version == GRAPH_SCHEMA_VERSION


def test_sqlite_graph_store_stamps_revision_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    store = SQLiteGraphStore.open_writable(path)
    entity = make_entity("default")
    store.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))

    revision = store.latest_revisions((QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))[0]

    assert revision.graph_store_schema_version == GRAPH_SCHEMA_VERSION


def test_read_only_missing_graph_store_does_not_create_state(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "graph.sqlite3"
    store = SQLiteGraphStore.open_read_only(path)

    health = store.health()
    manifest = store.current_manifest((QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert health.ok is False
    assert health.schema_compatible is False
    assert "not initialized" in health.message
    assert manifest.entity_rows == ()
    assert not path.exists()
    assert not path.parent.exists()


def test_read_only_sqlite_graph_store_rejects_apply(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    SQLiteGraphStore.open_writable(path)
    readonly = SQLiteGraphStore.open_read_only(path)
    entity = make_entity("default")

    with pytest.raises(GraphReadOnlyViolation):
        readonly.apply_reconcile_plan(make_plan(entities=(entity,), relationships=()))


def test_sqlite_graph_health_reports_missing_required_table(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE graph_entities (vault_id TEXT)")

    store = SQLiteGraphStore.open_read_only(path)

    health = store.health()
    assert health.ok is False
    assert health.schema_compatible is False
    assert "missing" in health.message


def test_sqlite_graph_health_checks_every_required_read_column(tmp_path: Path) -> None:
    path = tmp_path / "graph.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE graph_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO graph_metadata (key, value) VALUES ('schema_version', 'sqlite-graph-v1')")
        connection.execute(
            "CREATE TABLE graph_specs (spec_digest TEXT PRIMARY KEY, spec_version TEXT, serialized_spec TEXT)"
        )
        connection.execute(
            """
            CREATE TABLE graph_entities (
              vault_id TEXT,
              entity_id TEXT,
              aliases_json TEXT,
              graph_extraction_spec_digest TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE graph_relationships (
              source_vault_id TEXT,
              relationship_id TEXT,
              target_vault_id TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE graph_evidence_refs (
              evidence_ref_id TEXT,
              owner_kind TEXT,
              owner_vault_id TEXT,
              owner_id TEXT,
              anchor_key TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE graph_record_scopes (
              record_kind TEXT,
              record_vault_id TEXT,
              record_id TEXT,
              actual_scope TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE graph_revisions (
              vault_id TEXT,
              actual_scope TEXT,
              graph_store_schema_version TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE graph_tombstones (
              tombstone_id TEXT,
              record_kind TEXT,
              record_vault_id TEXT,
              record_id TEXT,
              actual_scope TEXT
            )
            """
        )

    store = SQLiteGraphStore.open_read_only(path)

    health = store.health()
    assert health.ok is False
    assert health.schema_compatible is False
    assert "entity_schema_version" in health.message
