from __future__ import annotations

from pathlib import Path

from tests.fakes.in_memory_graph_store import InMemoryGraphStore
from tests.test_graph_retrieval_service import StaticGraphReadiness, apply_metadata_refs
from tests.test_graph_store_contract import make_entity, make_plan, make_relationship
from vault_graph.app.graph_retrieval_service import GraphRetrievalService
from vault_graph.graph.graph_contracts import (
    EntityRecord,
    GraphEvidenceRef,
    RelationshipRecord,
    current_graph_extraction_spec,
)
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_readiness import GraphReadiness, GraphScopeReadiness
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_target_candidates_are_keyed_by_vault_and_entity(tmp_path: Path) -> None:
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    first = make_entity("first", name="GraphRAG")
    second = make_entity("second", name="GraphRAG")
    service = _service(
        tmp_path=tmp_path,
        scopes=(first_scope, second_scope),
        entities=(first, second),
        relationships=(),
        metadata_refs=(),
    )

    response = service.related(
        target="GraphRAG",
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
    )

    assert response.resolved_target is None
    assert response.warnings[0].code == "ambiguous_graph_target"
    assert sorted((entity.vault_id, entity.entity_id) for entity in response.target_candidates) == sorted(
        ((first.vault_id, first.entity_id), (second.vault_id, second.entity_id))
    )


def test_include_cross_vault_does_not_turn_same_name_targets_into_multi_seed_traversal(tmp_path: Path) -> None:
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    first = make_entity("first", name="GraphRAG")
    second = make_entity("second", name="GraphRAG")
    service = _service(
        tmp_path=tmp_path,
        scopes=(first_scope, second_scope),
        entities=(first, second),
        relationships=(),
        metadata_refs=(),
    )

    response = service.related(
        target="GraphRAG",
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        include_cross_vault=True,
    )

    assert response.items == ()
    assert response.resolved_target is None
    assert response.warnings[0].code == "ambiguous_graph_target"


def test_cross_vault_relationship_output_preserves_relationship_and_evidence_identity(tmp_path: Path) -> None:
    first_scope = QueryScope(vault_ids=("first",), content_scopes=("wiki",))
    second_scope = QueryScope(vault_ids=("second",), content_scopes=("wiki",))
    source = make_entity("first", name="GraphRAG")
    target = make_entity("second", name="Search")
    relationship = make_relationship(source, target)
    service = _service(
        tmp_path=tmp_path,
        scopes=(first_scope, second_scope),
        entities=(source, target),
        relationships=(relationship,),
        metadata_refs=relationship.evidence_refs,
    )

    response = service.related(
        target="GraphRAG",
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        include_cross_vault=True,
    )

    assert response.result_count == 1
    assert response.items[0].relationship_path[0].source_vault_id == "first"
    assert response.items[0].relationship_path[0].relationship_id == relationship.relationship_id
    assert response.items[0].relationship_path[0].target_vault_id == "second"
    assert response.items[0].evidence[0].vault_id == "first"
    assert response.items[0].evidence[0].document_id == relationship.evidence_refs[0].document_id
    assert response.items[0].evidence[0].chunk_id == relationship.evidence_refs[0].chunk_id


def test_stale_graph_scope_warns_for_one_vault_while_fresh_scope_returns_results(tmp_path: Path) -> None:
    stale_scope = QueryScope(vault_ids=("stale",), content_scopes=("wiki",))
    fresh_scope = QueryScope(vault_ids=("fresh",), content_scopes=("wiki",))
    source = make_entity("fresh", name="GraphRAG")
    target = make_entity("fresh", name="Search")
    relationship = make_relationship(source, target)
    service = _service(
        tmp_path=tmp_path,
        scopes=(stale_scope, fresh_scope),
        entities=(source, target),
        relationships=(relationship,),
        metadata_refs=relationship.evidence_refs,
        freshness_by_vault={"stale": "stale", "fresh": "fresh"},
    )

    response = service.related(
        target="GraphRAG",
        requested_scope=QueryScope(vault_ids=("stale", "fresh"), content_scopes=("wiki",)),
    )

    stale_warning = next(warning for warning in response.warnings if warning.code == "graph_stale")
    assert stale_warning.affected_vault_ids == ("stale",)
    assert response.result_count == 1
    assert response.items[0].entity.vault_id == "fresh"


def _service(
    *,
    tmp_path: Path,
    scopes: tuple[QueryScope, ...],
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...],
    metadata_refs: tuple[GraphEvidenceRef, ...],
    freshness_by_vault: dict[str, str] | None = None,
) -> GraphRetrievalService:
    catalog = _catalog(tmp_path=tmp_path, vault_ids=tuple(scope.vault_ids[0] for scope in scopes))
    metadata_store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    apply_metadata_refs(metadata_store, metadata_refs)
    graph_store = InMemoryGraphStore()
    for scope in scopes:
        scoped_entities = tuple(entity for entity in entities if entity.vault_id == scope.vault_ids[0])
        scoped_relationships = tuple(
            relationship for relationship in relationships if relationship.source_vault_id == scope.vault_ids[0]
        )
        graph_store.apply_reconcile_plan(
            make_plan(entities=scoped_entities, relationships=scoped_relationships, scope=scope)
        )
    return GraphRetrievalService(
        catalog=catalog,
        metadata_store=metadata_store,
        graph_store=graph_store,
        graph_readiness=StaticGraphReadiness(_readiness(scopes=scopes, freshness_by_vault=freshness_by_vault or {})),
        projection=RustworkxGraphProjection(),
    )


def _catalog(*, tmp_path: Path, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries: list[VaultCatalogEntry] = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki",)))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])


def _readiness(*, scopes: tuple[QueryScope, ...], freshness_by_vault: dict[str, str]) -> GraphReadiness:
    spec = current_graph_extraction_spec()
    rows = tuple(
        row
        for scope in scopes
        for row in (
            _readiness_row(scope=scope, freshness_by_vault=freshness_by_vault),
            _readiness_row(
                scope=QueryScope(
                    vault_ids=scope.vault_ids,
                    content_scopes=scope.content_scopes,
                    include_cross_vault=True,
                ),
                freshness_by_vault=freshness_by_vault,
            ),
        )
    )
    freshness = "stale" if any(row.freshness == "stale" for row in rows) else "fresh"
    return GraphReadiness(
        backend_name="memory-graph",
        backend_available=True,
        schema_version="memory-graph-v1",
        schema_compatible=True,
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_extraction_spec_compatible=True,
        freshness=freshness,
        stale_count=sum(row.stale_count for row in rows),
        tombstone_count=0,
        last_graph_revision="graph-1",
        affected_vault_ids=tuple(scope.vault_ids[0] for scope in scopes),
        scope_readiness=rows,
        warnings=(),
        recovery_hint="ok" if freshness == "fresh" else "run `vg index`",
    )


def _readiness_row(*, scope: QueryScope, freshness_by_vault: dict[str, str]) -> GraphScopeReadiness:
    freshness = freshness_by_vault.get(scope.vault_ids[0], "fresh")
    return GraphScopeReadiness(
        vault_id=scope.vault_ids[0],
        actual_scope=graph_scope_key(scope),
        freshness=freshness,
        stale_count=1 if freshness == "stale" else 0,
        tombstone_count=0,
        last_graph_revision="graph-1" if freshness == "fresh" else None,
        warnings=(),
    )
