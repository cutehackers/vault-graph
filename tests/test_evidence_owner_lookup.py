import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerRecord
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore

SCOPE = QueryScope(vault_ids=("default",), content_scopes=("wiki",))


def test_sqlite_lookup_preserves_owner_anchor_identity_and_bounds(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("default")
    second_ref = replace(source.evidence_refs[0], evidence_ref_id="second-ref", anchor="other")
    source = replace(source, evidence_refs=(*source.evidence_refs, second_ref))
    target = make_entity("default", name="Target")
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,)))

    records = store.lookup_evidence_owners(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        scopes=(SCOPE,),
        include_cross_vault=False,
        limit=3,
    )

    assert len(records) == 3
    identities = [
        (row.owner_kind, row.owner_vault_id, row.owner_id, row.evidence_ref.evidence_ref_id) for row in records
    ]
    assert identities == sorted(identities)
    assert all(row.graph_revision == "graph-1" for row in records)
    assert (
        store.lookup_evidence_owners(
            vault_id="default",
            document_id="default-doc",
            chunk_id="default-chunk",
            scopes=(SCOPE,),
            include_cross_vault=False,
            limit=20,
        )[-1].source_entity_id
        == source.entity_id
    )
    assert (
        len(
            store.lookup_evidence_owners(
                vault_id="default",
                document_id="default-doc",
                chunk_id="default-chunk",
                scopes=(SCOPE,),
                include_cross_vault=False,
                limit=1,
            )
        )
        == 1
    )


def test_sqlite_lookup_filters_before_limit_and_uses_evidence_index(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    entities = tuple(make_entity("default", name=f"Owner {index}") for index in range(40))
    store.apply_reconcile_plan(make_plan(entities=entities, relationships=()))
    statements: list[str] = []
    original_connect = store._connect

    def traced_connect() -> sqlite3.Connection:
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(store, "_connect", traced_connect)

    def forbid_full_record(*args: object, **kwargs: object) -> None:
        raise AssertionError("lookup must not load a manifest or full owner")

    monkeypatch.setattr(store, "current_manifest", forbid_full_record)
    monkeypatch.setattr(store, "get_entity", forbid_full_record)
    rows = store.lookup_evidence_owners(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        scopes=(SCOPE,),
        include_cross_vault=False,
        limit=2,
    )
    assert len(rows) == 2
    queries = [sql for sql in statements if "SELECT ref.evidence_ref_id" in sql]
    assert len(queries) == 1
    assert queries[0].rstrip().endswith("LIMIT 2")
    with original_connect() as connection:
        plan = connection.execute("EXPLAIN QUERY PLAN " + queries[0]).fetchall()
    assert any("idx_graph_evidence_chunk" in str(row["detail"]) for row in plan)


def test_sqlite_lookup_excludes_missing_owners_and_endpoint_scope(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("default")
    target = make_entity("default", name="Target")
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(make_plan(entities=(source, target), relationships=(relationship,)))
    with store._connect() as connection:
        connection.execute("DELETE FROM graph_entities WHERE entity_id = ?", (target.entity_id,))
    rows = store.lookup_evidence_owners(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        scopes=(SCOPE,),
        include_cross_vault=False,
        limit=10,
    )
    assert [(row.owner_kind, row.owner_id) for row in rows] == [("entity", source.entity_id)]
    with store._connect() as connection:
        connection.execute("DELETE FROM graph_record_scopes")
    assert (
        store.lookup_evidence_owners(
            vault_id="default",
            document_id="default-doc",
            chunk_id="default-chunk",
            scopes=(SCOPE,),
            include_cross_vault=False,
            limit=10,
        )
        == ()
    )


def test_sqlite_lookup_checks_cross_vault_endpoints_and_all_relationship_evidence(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    other_scope = QueryScope(vault_ids=("other",), content_scopes=("wiki",))
    source = make_entity("default")
    target = make_entity("other")
    store.apply_reconcile_plan(make_plan(entities=(target,), relationships=(), scope=other_scope))
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(make_plan(entities=(source,), relationships=(relationship,), scope=SCOPE))

    def lookup(scopes: tuple[QueryScope, ...], cross: bool) -> tuple[EvidenceOwnerRecord, ...]:
        return store.lookup_evidence_owners(
            vault_id="default",
            document_id="default-doc",
            chunk_id="default-chunk",
            scopes=scopes,
            include_cross_vault=cross,
            limit=10,
        )

    assert all(row.owner_kind == "entity" for row in lookup((SCOPE,), True))
    assert all(row.owner_kind == "entity" for row in lookup((SCOPE, other_scope), False))
    rows = lookup((SCOPE, other_scope), True)
    assert rows[-1].owner_kind == "relationship"
    assert rows[-1].target_vault_id == "other"
    assert rows[-1].target_entity_id == target.entity_id
    with store._connect() as connection:
        connection.execute(
            """INSERT INTO graph_evidence_refs
            SELECT 'forbidden', owner_kind, owner_vault_id, owner_id, 'forbidden-vault',
                   document_id, chunk_id, content_hash, section, anchor, anchor_key, path
            FROM graph_evidence_refs WHERE owner_kind = 'relationship'"""
        )
    assert all(row.owner_kind == "entity" for row in lookup((SCOPE, other_scope), True))


def test_document_lookup_uses_verified_view_without_writes_or_full_owner_reads(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from tests.test_document_graph_store import GRAPH_LIMITS, READ_LIMITS
    from tests.test_graph_module_public_integration import fingerprints, indexed_home
    from vault_graph.app.catalog_service import CatalogService
    from vault_graph.storage.local.document_graph_store import DocumentGraphStore
    from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

    vault, home = indexed_home(tmp_path, monkeypatch)
    catalog = CatalogService(graph_home_path=home)
    scope = catalog.load_catalog().default_scope()
    metadata = SQLiteMetadataStore(catalog.metadata_path, initialize=False)
    legacy = SQLiteGraphStore.open_read_only(catalog.graph_path)
    directory = home / "cache" / "evidence-lookup"
    writer = DocumentGraphStore.open_writable(
        directory,
        metadata_store=metadata,
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    writer.bootstrap_from_legacy(legacy, (scope,))
    writer.close()
    reader = DocumentGraphStore.open_read_only(
        directory,
        metadata_store=metadata,
        graph_limits=GRAPH_LIMITS,
        read_limits=READ_LIMITS,
    )
    refs = reader.current_document_evidence_refs()
    ref = next(ref for ref in refs if ref.owner_kind == "relationship")
    before_vault, before_home = fingerprints(vault), fingerprints(home)

    def forbid_full_record(*args: object, **kwargs: object) -> None:
        raise AssertionError("bounded lookup must use restored verified query view")

    monkeypatch.setattr(reader._query, "current_manifest", forbid_full_record)
    monkeypatch.setattr(reader._query, "get_entity", forbid_full_record)
    monkeypatch.setattr(reader._query, "get_relationship", forbid_full_record)

    def read_rows(store: SQLiteGraphStore | DocumentGraphStore) -> tuple[EvidenceOwnerRecord, ...]:
        return store.lookup_evidence_owners(
            vault_id=ref.evidence_vault_id,
            document_id=ref.document_id,
            chunk_id=ref.chunk_id,
            scopes=(scope,),
            include_cross_vault=False,
            limit=2,
        )

    assert read_rows(reader) == read_rows(legacy)
    assert len(read_rows(reader)) <= 2
    revisions = reader.evidence_lookup_revisions()
    assert revisions and all(isinstance(value, str) and value.isdigit() for _, value in revisions)
    assert legacy.evidence_lookup_revisions() == ()
    reader.close()
    assert fingerprints(vault) == before_vault
    assert fingerprints(home) == before_home


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_lookup_rejects_unbounded_or_invalid_limit_before_opening(tmp_path: Path, limit: int | float) -> None:
    store = SQLiteGraphStore.open_read_only(tmp_path / "missing" / "graph.sqlite3")
    with pytest.raises(ValueError, match="positive integer"):
        store.lookup_evidence_owners(
            vault_id="default",
            document_id="doc",
            chunk_id="chunk",
            scopes=(SCOPE,),
            include_cross_vault=False,
            limit=cast(int, limit),
        )
    assert not (tmp_path / "missing").exists()


def test_lookup_matches_full_evidence_key_and_keeps_vault_identity(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    first = make_entity("default", document_id="same-doc", chunk_id="same-chunk")
    other = make_entity("other", document_id="same-doc", chunk_id="same-chunk")
    other_scope = QueryScope(vault_ids=("other",), content_scopes=("wiki",))
    store.apply_reconcile_plan(make_plan(entities=(first,), relationships=(), scope=SCOPE))
    store.apply_reconcile_plan(make_plan(entities=(other,), relationships=(), scope=other_scope))
    result = store.lookup_evidence_owners(
        vault_id="default",
        document_id="same-doc",
        chunk_id="same-chunk",
        scopes=(SCOPE, other_scope),
        include_cross_vault=True,
        limit=5,
    )
    assert len(result) == 1
    assert result[0].owner_vault_id == "default"
    assert (
        store.lookup_evidence_owners(
            vault_id="default",
            document_id="wrong-doc",
            chunk_id="same-chunk",
            scopes=(SCOPE, other_scope),
            include_cross_vault=True,
            limit=5,
        )
        == ()
    )
    assert (
        store.lookup_evidence_owners(
            vault_id="other",
            document_id="same-doc",
            chunk_id="same-chunk",
            scopes=(SCOPE,),
            include_cross_vault=True,
            limit=5,
        )
        == ()
    )


def test_sqlite_lookup_applies_scope_before_returned_row_limit(tmp_path: Path) -> None:
    from vault_graph.graph.graph_identity import graph_scope_key

    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    entities = tuple(make_entity("default", name=f"Owner {index}") for index in range(12))
    store.apply_reconcile_plan(make_plan(entities=entities, relationships=()))
    allowed_id = max(entity.entity_id for entity in entities)
    outside_scope = graph_scope_key(QueryScope(vault_ids=("default",), content_scopes=("docs",)))
    with store._connect() as connection:
        connection.execute(
            "UPDATE graph_record_scopes SET actual_scope = ? WHERE record_id != ?", (outside_scope, allowed_id)
        )
    rows = store.lookup_evidence_owners(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        scopes=(SCOPE,),
        include_cross_vault=False,
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0].owner_id == allowed_id


def test_lookup_attests_latest_scope_revision_without_changing_unchanged_owner_revision(tmp_path: Path) -> None:
    from vault_graph.graph.graph_identity import graph_scope_key

    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    entity = make_entity("default")
    initial = make_plan(entities=(entity,), relationships=(), scope=SCOPE)
    store.apply_reconcile_plan(initial)
    unchanged = replace(
        initial,
        entity_upserts=(),
        evidence_ref_upserts=(),
        graph_revision_rows=(
            replace(
                initial.graph_revision_rows[0],
                graph_index_revision="graph-2",
                updated_at="2026-06-11T00:00:00+00:00",
            ),
        ),
    )
    store.apply_reconcile_plan(unchanged)
    rows = store.lookup_evidence_owners(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        scopes=(SCOPE,),
        include_cross_vault=False,
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0].graph_revision == "graph-1"
    assert rows[0].scope_key == graph_scope_key(SCOPE)
    assert rows[0].scope_revision == "graph-2"
