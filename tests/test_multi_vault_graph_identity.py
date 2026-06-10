from pathlib import Path

from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from vault_graph.graph.graph_contracts import GraphEvidenceRef, RelationshipRecord
from vault_graph.graph.graph_identity import (
    graph_scope_key,
    stable_entity_id,
    stable_evidence_ref_id,
    stable_relationship_id,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore


def test_same_entity_name_in_two_vaults_does_not_collide() -> None:
    first = stable_entity_id(
        vault_id="first",
        entity_type="concept",
        normalized_name="retrieval",
        canonical_path="wiki/retrieval.md",
    )
    second = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="retrieval",
        canonical_path="wiki/retrieval.md",
    )

    assert first != second


def test_cross_vault_relationship_preserves_source_target_and_evidence_vaults() -> None:
    source = stable_entity_id(
        vault_id="first",
        entity_type="system",
        normalized_name="vault graph",
        canonical_path="wiki/vault-graph.md",
    )
    target = stable_entity_id(
        vault_id="second",
        entity_type="concept",
        normalized_name="context pack",
        canonical_path="wiki/context-pack.md",
    )
    relationship_id = stable_relationship_id(
        relationship_type="references",
        source_vault_id="first",
        source_entity_id=source,
        target_vault_id="second",
        target_entity_id=target,
    )
    evidence = GraphEvidenceRef(
        evidence_ref_id=stable_evidence_ref_id(
            owner_kind="relationship",
            owner_vault_id="first",
            owner_id=relationship_id,
            evidence_vault_id="second",
            document_id="doc",
            chunk_id="chunk",
            anchor=None,
        ),
        owner_kind="relationship",
        owner_vault_id="first",
        owner_id=relationship_id,
        evidence_vault_id="second",
        document_id="doc",
        chunk_id="chunk",
        content_hash="hash",
        section=None,
        anchor=None,
        path="wiki/context-pack.md",
        excerpt=None,
    )

    relationship = RelationshipRecord(
        relationship_id=relationship_id,
        type="references",
        source_vault_id="first",
        source_entity_id=source,
        target_vault_id="second",
        target_entity_id=target,
        evidence_refs=(evidence,),
        status="stated",
        confidence=1.0,
        extraction_method="test",
        graph_extraction_spec_version="graph-extraction-spec-v1",
        graph_extraction_spec_digest="0" * 64,
        created_at="2026-06-10T00:00:00+00:00",
        updated_at="2026-06-10T00:00:00+00:00",
        graph_index_revision="graph-1",
    )

    assert relationship.source_vault_id == "first"
    assert relationship.target_vault_id == "second"
    assert relationship.evidence_refs[0].evidence_vault_id == "second"


def test_graph_scope_key_includes_cross_vault_policy() -> None:
    local = QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=False)
    cross = QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True)

    assert graph_scope_key(local) == "first:wiki:local"
    assert graph_scope_key(cross) == "first:wiki:cross"


def test_sqlite_graph_manifest_keeps_same_names_separate_by_vault(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    first = make_entity("first", name="Shared")
    second = make_entity("second", name="Shared")
    store.apply_reconcile_plan(
        make_plan(
            entities=(first,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(second,),
            relationships=(),
            scope=QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        )
    )

    first_manifest = store.current_manifest((QueryScope(vault_ids=("first",), content_scopes=("wiki",)),))
    second_manifest = store.current_manifest((QueryScope(vault_ids=("second",), content_scopes=("wiki",)),))

    assert tuple(row.vault_id for row in first_manifest.entity_rows) == ("first",)
    assert tuple(row.vault_id for row in second_manifest.entity_rows) == ("second",)


def test_sqlite_graph_manifest_requires_explicit_cross_vault_scope(tmp_path: Path) -> None:
    store = SQLiteGraphStore.open_writable(tmp_path / "graph.sqlite3")
    source = make_entity("first", name="Source")
    target = make_entity("second", name="Target")
    relationship = make_relationship(source, target)
    store.apply_reconcile_plan(
        make_plan(
            entities=(source,),
            relationships=(),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(target,),
            relationships=(),
            scope=QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        )
    )
    store.apply_reconcile_plan(
        make_plan(
            entities=(),
            relationships=(relationship,),
            scope=QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True),
        )
    )

    local_manifest = store.current_manifest((QueryScope(vault_ids=("first",), content_scopes=("wiki",)),))
    cross_manifest = store.current_manifest(
        (
            QueryScope(vault_ids=("first",), content_scopes=("wiki",), include_cross_vault=True),
            QueryScope(vault_ids=("second",), content_scopes=("wiki",), include_cross_vault=True),
        )
    )

    assert local_manifest.relationship_rows == ()
    assert tuple(row.relationship_id for row in cross_manifest.relationship_rows) == (relationship.relationship_id,)
