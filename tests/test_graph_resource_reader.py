from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from tests.test_graph_store_contract import make_entity, make_relationship
from vault_graph.app.graph_resource_service import GraphResourceService
from vault_graph.errors import GraphStoreError
from vault_graph.graph.graph_contracts import EntityRecord, RelationshipRecord, current_graph_extraction_spec
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_query import (
    GraphEntityMatch,
    GraphEntityQuery,
    GraphEntityQueryResult,
    GraphRelationshipQuery,
    GraphRelationshipQueryResult,
)
from vault_graph.graph.graph_readiness import GraphReadiness, GraphScopeReadiness
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.graph_resource_reader import GraphResourceReader
from vault_graph.mcp.mcp_errors import map_exception_to_mcp_error
from vault_graph.mcp.mcp_uri import parse_mcp_resource_uri
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


def make_catalog(tmp_path: Path) -> VaultCatalog:
    main = tmp_path / "main"
    main.mkdir(exist_ok=True)
    return VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=main, display_name="Main"),),
        active_vault_id="main",
    )


def make_readiness(actual_scopes: tuple[QueryScope, ...], *, freshness: str = "fresh") -> GraphReadiness:
    spec = current_graph_extraction_spec()
    return GraphReadiness(
        backend_name="fake-graph",
        backend_available=freshness not in {"missing", "unavailable"},
        schema_version="fake-graph-v1",
        schema_compatible=freshness != "incompatible",
        graph_extraction_spec_version=spec.spec_version,
        graph_extraction_spec_digest=spec.spec_digest,
        graph_extraction_spec_compatible=freshness != "incompatible",
        freshness=freshness,
        stale_count=1 if freshness == "stale" else 0,
        tombstone_count=0,
        last_graph_revision="graph-1" if freshness == "fresh" else None,
        affected_vault_ids=tuple(scope.vault_ids[0] for scope in actual_scopes),
        scope_readiness=tuple(
            GraphScopeReadiness(
                vault_id=scope.vault_ids[0],
                actual_scope=graph_scope_key(scope),
                freshness=freshness,
                stale_count=1 if freshness == "stale" else 0,
                tombstone_count=0,
                last_graph_revision="graph-1" if freshness == "fresh" else None,
                warnings=(),
            )
            for scope in actual_scopes
        ),
        warnings=(),
        recovery_hint="ok" if freshness == "fresh" else "run vg index",
    )


class RecordingReadiness:
    def __init__(self, *, calls: list[str], freshness: str = "fresh") -> None:
        self.calls = calls
        self.freshness = freshness
        self.last_requested_scope: QueryScope | None = None
        self.last_actual_scopes: tuple[QueryScope, ...] = ()

    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        self.calls.append("readiness")
        self.last_requested_scope = requested_scope
        self.last_actual_scopes = actual_scopes
        return make_readiness(actual_scopes, freshness=self.freshness)


class RecordingGraphStore:
    def __init__(
        self,
        *,
        calls: list[str],
        entities: tuple[EntityRecord, ...],
        relationships: tuple[RelationshipRecord, ...] = (),
    ) -> None:
        self.calls = calls
        self.entities = {(entity.vault_id, entity.entity_id): entity for entity in entities}
        self.relationships = relationships
        self.last_relationship_query: GraphRelationshipQuery | None = None

    def get_entity(self, *, vault_id: str, entity_id: str) -> EntityRecord | None:
        self.calls.append("get_entity")
        return self.entities.get((vault_id, entity_id))

    def find_entities(self, query: GraphEntityQuery) -> GraphEntityQueryResult:
        self.calls.append("find_entities")
        normalized = " ".join(query.text.casefold().split())
        matches = []
        for entity in self.entities.values():
            alias_matches = {alias.casefold() for alias in entity.aliases}
            if entity.normalized_name == normalized or normalized in alias_matches:
                matches.append(
                    GraphEntityMatch(
                        entity=entity,
                        match_kind="normalized_name",
                        match_rank=1,
                        matched_value=query.text,
                    )
                )
        return GraphEntityQueryResult(
            matches=tuple(matches[: query.limit]),
            truncated=False,
            affected_vault_ids=("main",),
        )

    def relationships_for_entities(self, query: GraphRelationshipQuery) -> GraphRelationshipQueryResult:
        self.calls.append("relationships_for_entities")
        self.last_relationship_query = query
        seeds = {(seed.vault_id, seed.entity_id) for seed in query.seeds}
        relationships = tuple(
            relationship
            for relationship in self.relationships
            if relationship.status in query.statuses
            and (
                (relationship.source_vault_id, relationship.source_entity_id) in seeds
                or (relationship.target_vault_id, relationship.target_entity_id) in seeds
            )
        )
        return GraphRelationshipQueryResult(
            relationships=relationships[: query.limit],
            truncated=False,
            omitted_cross_vault_count=0,
            affected_vault_ids=("main",),
        )


class RecordingMetadataStore:
    def __init__(self, *, missing_chunk_ids: tuple[str, ...] = ()) -> None:
        self.missing_chunk_ids = set(missing_chunk_ids)

    def resolve_chunk_evidence(
        self,
        *,
        vault_id: str,
        document_id: str,
        chunk_id: str,
    ) -> EvidenceReference | None:
        if chunk_id in self.missing_chunk_ids:
            return None
        return EvidenceReference(
            vault_id=vault_id,
            document_id=document_id,
            chunk_id=chunk_id,
            path="wiki/graphrag.md",
            section="GraphRAG",
            anchor="graphrag",
            content_hash=f"{vault_id}-{chunk_id}-hash",
            raw_sha256=f"{vault_id}-{document_id}-raw",
            metadata_index_revision="metadata-1",
            vault_revision=f"git-{vault_id}",
        )


def make_service(
    *,
    tmp_path: Path,
    entities: tuple[EntityRecord, ...],
    relationships: tuple[RelationshipRecord, ...] = (),
    freshness: str = "fresh",
    missing_chunk_ids: tuple[str, ...] = (),
    calls: list[str] | None = None,
) -> tuple[GraphResourceService, RecordingGraphStore]:
    call_log = calls if calls is not None else []
    graph_store = RecordingGraphStore(calls=call_log, entities=entities, relationships=relationships)
    service = GraphResourceService(
        catalog=make_catalog(tmp_path),
        metadata_store=RecordingMetadataStore(missing_chunk_ids=missing_chunk_ids),  # type: ignore[arg-type]
        graph_store=graph_store,  # type: ignore[arg-type]
        graph_readiness=RecordingReadiness(calls=call_log, freshness=freshness),
    )
    return service, graph_store


def test_get_entity_checks_graph_readiness_before_store_read(tmp_path: Path) -> None:
    calls: list[str] = []
    entity = make_entity("main")
    service, graph_store = make_service(tmp_path=tmp_path, entities=(entity,), calls=calls)

    result = service.get_entity(vault_id="main", entity_id=entity.entity_id)

    assert result.entity == entity
    assert calls[:2] == ["readiness", "get_entity"]
    assert graph_store.last_relationship_query is not None
    assert graph_store.last_relationship_query.statuses == ("stated", "inferred", "contested", "deprecated")


def test_missing_or_stale_graph_state_is_unavailable(tmp_path: Path) -> None:
    entity = make_entity("main")
    service, _ = make_service(tmp_path=tmp_path, entities=(entity,), freshness="stale")

    with pytest.raises(GraphStoreError, match="graph_unavailable"):
        service.get_entity(vault_id="main", entity_id=entity.entity_id)


def test_missing_or_tombstoned_entity_is_not_found(tmp_path: Path) -> None:
    tombstoned = replace(make_entity("main"), status="tombstoned")
    service, _ = make_service(tmp_path=tmp_path, entities=(tombstoned,))

    with pytest.raises(GraphStoreError, match="resource_not_found"):
        service.get_entity(vault_id="main", entity_id=tombstoned.entity_id)


def test_find_concept_resolves_one_exact_active_match(tmp_path: Path) -> None:
    entity = make_entity("main", name="GraphRAG")
    service, _ = make_service(tmp_path=tmp_path, entities=(entity,))

    result = service.find_concept(vault_id="main", name="Graph RAG")

    assert result.entity == entity


def test_find_concept_without_exact_match_is_not_found(tmp_path: Path) -> None:
    entity = make_entity("main", name="Search")
    service, _ = make_service(tmp_path=tmp_path, entities=(entity,))

    with pytest.raises(GraphStoreError, match="resource_not_found"):
        service.find_concept(vault_id="main", name="GraphRAG")


def test_find_concept_with_multiple_exact_matches_is_ambiguous(tmp_path: Path) -> None:
    first = make_entity("main", name="GraphRAG", path="wiki/one.md")
    second = make_entity("main", name="GraphRAG", path="wiki/two.md")
    service, _ = make_service(tmp_path=tmp_path, entities=(first, second))

    with pytest.raises(GraphStoreError, match="ambiguous_resource"):
        service.find_concept(vault_id="main", name="GraphRAG")


def test_missing_graph_evidence_becomes_warning(tmp_path: Path) -> None:
    entity = make_entity("main")
    service, _ = make_service(
        tmp_path=tmp_path,
        entities=(entity,),
        missing_chunk_ids=(entity.evidence_refs[0].chunk_id,),
    )

    result = service.get_entity(vault_id="main", entity_id=entity.entity_id)

    assert result.evidence == ()
    assert result.warnings[0].code == "missing_evidence"


def test_graph_reader_returns_canonical_json_envelope(tmp_path: Path) -> None:
    source = make_entity("main", name="GraphRAG")
    target = make_entity("main", name="Search", path="wiki/search.md")
    relationship = replace(make_relationship(source, target), status="deprecated")
    service, _ = make_service(tmp_path=tmp_path, entities=(source, target), relationships=(relationship,))
    reader = GraphResourceReader(graph_resource_service=service)
    uri = parse_mcp_resource_uri(f"vault://main/graph/entities/{source.entity_id}", catalog=make_catalog(tmp_path))

    body = reader.read_entity(uri)
    payload = json.loads(body.text)

    assert body.content_mime_type == "application/json"
    assert body.metadata["vault_id"] == "main"
    assert body.metadata["entity_id"] == source.entity_id
    assert body.metadata["relationship_count"] == 1
    assert payload["entity"]["entity_id"] == source.entity_id
    assert payload["relationships_by_status"]["deprecated"][0]["target_entity_id"] == target.entity_id
    assert payload["relationships_by_status"]["deprecated"][0]["source_vault_id"] == "main"
    assert payload["relationships_by_status"]["deprecated"][0]["evidence_refs"][0]["owner_vault_id"] == "main"
    assert payload["evidence"][0]["vault_id"] == "main"
    assert body.text.endswith("\n")


def test_graph_reader_reads_concept_through_service(tmp_path: Path) -> None:
    entity = make_entity("main", name="GraphRAG")
    service, _ = make_service(tmp_path=tmp_path, entities=(entity,))
    reader = GraphResourceReader(graph_resource_service=service)
    uri = parse_mcp_resource_uri("vault://main/concepts/Graph%20RAG", catalog=make_catalog(tmp_path))

    body = reader.read_concept(uri)

    assert body.metadata["entity_id"] == entity.entity_id
    assert json.loads(body.text)["entity"]["name"] == "GraphRAG"


@pytest.mark.parametrize(
    ("message", "kind", "code"),
    [
        ("graph_unavailable: run vg index", "execution", "graph_unavailable"),
        ("resource_not_found: missing entity", "not_found", "resource_not_found"),
        ("ambiguous_resource: use entity URI", "invalid_parameter", "ambiguous_resource"),
    ],
)
def test_graph_store_resource_errors_map_to_specific_mcp_codes(message: str, kind: str, code: str) -> None:
    error = map_exception_to_mcp_error(GraphStoreError(message), affected_vault_ids=("main",))

    assert error.kind == kind
    assert error.payload.code == code
    assert error.payload.affected_vault_ids == ("main",)
