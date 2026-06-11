from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from vault_graph.errors import GraphStoreError, SearchError
from vault_graph.graph.graph_contracts import EntityRecord, GraphEvidenceRef, RelationshipRecord
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_query import (
    GraphEntityIdentity,
    GraphEntityMatch,
    GraphEntityQuery,
    GraphRelationshipQuery,
)
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
    GRAPH_PROJECTION_VERSION,
    MAX_GRAPH_PROJECTION_DEPTH,
    GraphPath,
    GraphProjection,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
)
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    GraphOutputFormat,
    GraphRetrievalRevision,
    GraphRetrievalWarning,
    RelatedItem,
    RelatedResponse,
)
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

GRAPH_TARGET_LIMIT = 20
GRAPH_RELATIONSHIP_READ_LIMIT = 200


class GraphReadinessChecker(Protocol):
    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        raise NotImplementedError


class GraphRetrievalService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        graph_readiness: GraphReadinessChecker,
        projection: GraphProjection,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._graph_store = graph_store
        self._graph_readiness = graph_readiness
        self._projection = projection

    def related(
        self,
        *,
        target: str,
        requested_scope: QueryScope,
        depth: int = 1,
        direction: str = "both",
        relationship_types: tuple[str, ...] = (),
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> RelatedResponse:
        if depth <= 0 or depth > MAX_GRAPH_PROJECTION_DEPTH:
            raise GraphStoreError("unsupported graph projection depth")
        projection_direction = _projection_direction(direction)
        actual_scopes = _actual_scopes(
            catalog=self._catalog,
            requested_scope=requested_scope,
            include_cross_vault=include_cross_vault,
        )
        readiness = self._graph_readiness.check(requested_scope=requested_scope, actual_scopes=actual_scopes)
        _raise_fatal_readiness(readiness)
        fresh_scopes, warnings = _fresh_scopes_with_warnings(readiness=readiness, actual_scopes=actual_scopes)
        if not fresh_scopes:
            return _empty_related_response(
                target=target,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
                warnings=warnings,
            )

        target_result = self._graph_store.find_entities(
            GraphEntityQuery(text=target, actual_scopes=fresh_scopes, limit=GRAPH_TARGET_LIMIT)
        )
        if target_result.truncated:
            warnings.append(
                GraphRetrievalWarning(
                    code="graph_target_scan_truncated",
                    message="Graph target lookup reached the scan limit.",
                    severity="warning",
                    affected_vault_ids=target_result.affected_vault_ids,
                )
            )
        target_resolution = _resolve_target(target_result.matches)
        if target_resolution.warning is not None:
            warnings.append(target_resolution.warning)
            return _empty_related_response(
                target=target,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
                warnings=warnings,
                target_candidates=target_resolution.candidates,
            )

        resolved_target = target_resolution.entity
        if resolved_target is None:
            raise SearchError("resolved graph target is required")
        traversal = self._collect_relationships(
            seed=GraphEntityIdentity(resolved_target.vault_id, resolved_target.entity_id),
            actual_scopes=fresh_scopes,
            depth=depth,
            direction=projection_direction,
            relationship_types=relationship_types,
            include_cross_vault=include_cross_vault,
            warnings=warnings,
        )
        evidence_valid_relationships, relationship_evidence = self._evidence_valid_relationships(
            relationships=traversal.relationships,
            warnings=warnings,
        )
        projection_result = self._projection.project(
            GraphProjectionInput(
                seeds=(_projection_node(resolved_target),),
                nodes=tuple(_projection_node(entity) for entity in traversal.entities),
                relationships=tuple(_projection_edge(relationship) for relationship in evidence_valid_relationships),
                actual_scope_keys=tuple(graph_scope_key(scope) for scope in fresh_scopes),
                source_graph_revisions=tuple(
                    row.last_graph_revision for row in readiness.scope_readiness if row.last_graph_revision
                ),
                max_depth=depth,
                direction=projection_direction,
                relationship_types=relationship_types,
                statuses=("stated", "inferred", "contested"),
                include_cross_vault=include_cross_vault,
                limit=limit,
                edge_limit=DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
            )
        )
        if projection_result.truncated:
            warnings.append(
                GraphRetrievalWarning(
                    code="graph_projection_truncated",
                    message="Graph projection reached its result or edge limit.",
                    severity="warning",
                    affected_vault_ids=_affected_vault_ids(fresh_scopes),
                )
            )
        items = tuple(
            self._related_item_from_path(
                path=path,
                entities=traversal.entities_by_identity,
                relationships=traversal.relationships_by_identity,
                relationship_evidence=relationship_evidence,
                rank=rank,
            )
            for rank, path in enumerate(projection_result.paths, start=1)
        )
        return RelatedResponse(
            target=target,
            resolved_target=resolved_target,
            target_candidates=target_resolution.candidates,
            requested_scope=requested_scope,
            actual_scopes=actual_scopes,
            projection_build_id=projection_result.projection_build_id,
            graph_projection_version=projection_result.graph_projection_version,
            result_count=len(items),
            items=items,
            warnings=tuple(warnings),
            store_revisions=_store_revisions(
                readiness=readiness,
                projection_build_id=projection_result.projection_build_id,
                evidence=tuple(evidence for values in relationship_evidence.values() for evidence in values),
            ),
            generated_at=datetime.now(UTC).isoformat(),
        )

    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        depth: int = 2,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse:
        raise NotImplementedError("decision_trace is implemented in Phase 3C Task 8")

    def _collect_relationships(
        self,
        *,
        seed: GraphEntityIdentity,
        actual_scopes: tuple[QueryScope, ...],
        depth: int,
        direction: Literal["out", "in", "both"],
        relationship_types: tuple[str, ...],
        include_cross_vault: bool,
        warnings: list[GraphRetrievalWarning],
    ) -> _TraversalResult:
        visited = {(seed.vault_id, seed.entity_id)}
        frontier: tuple[GraphEntityIdentity, ...] = (seed,)
        relationships_by_identity: dict[tuple[str, str], RelationshipRecord] = {}
        entities_by_identity: dict[tuple[str, str], EntityRecord] = {}
        seed_entity = self._graph_store.get_entity(vault_id=seed.vault_id, entity_id=seed.entity_id)
        if seed_entity is not None:
            entities_by_identity[(seed.vault_id, seed.entity_id)] = seed_entity
        for _ in range(depth):
            if not frontier:
                break
            result = self._graph_store.relationships_for_entities(
                GraphRelationshipQuery(
                    seeds=frontier,
                    actual_scopes=actual_scopes,
                    direction=direction,
                    relationship_types=relationship_types,
                    include_cross_vault=include_cross_vault,
                    limit=GRAPH_RELATIONSHIP_READ_LIMIT,
                )
            )
            if result.truncated:
                warnings.append(
                    GraphRetrievalWarning(
                        code="graph_relationship_read_truncated",
                        message="Graph relationship read reached the limit.",
                        severity="warning",
                        affected_vault_ids=result.affected_vault_ids,
                    )
                )
            if result.omitted_cross_vault_count:
                warnings.append(
                    GraphRetrievalWarning(
                        code="cross_vault_relationship_omitted",
                        message=f"Omitted {result.omitted_cross_vault_count} cross-Vault graph relationships.",
                        severity="warning",
                        affected_vault_ids=result.affected_vault_ids,
                    )
                )
            next_frontier: list[GraphEntityIdentity] = []
            for relationship in result.relationships:
                relationships_by_identity.setdefault(
                    (relationship.source_vault_id, relationship.relationship_id),
                    relationship,
                )
                for endpoint in _relationship_endpoints(relationship):
                    entity = self._graph_store.get_entity(vault_id=endpoint.vault_id, entity_id=endpoint.entity_id)
                    if entity is not None:
                        entities_by_identity[(endpoint.vault_id, endpoint.entity_id)] = entity
                    key = (endpoint.vault_id, endpoint.entity_id)
                    if key not in visited:
                        visited.add(key)
                        next_frontier.append(endpoint)
            frontier = tuple(next_frontier)
        return _TraversalResult(
            relationships=tuple(relationships_by_identity.values()),
            relationships_by_identity=relationships_by_identity,
            entities=tuple(entities_by_identity.values()),
            entities_by_identity=entities_by_identity,
        )

    def _evidence_valid_relationships(
        self,
        *,
        relationships: tuple[RelationshipRecord, ...],
        warnings: list[GraphRetrievalWarning],
    ) -> tuple[tuple[RelationshipRecord, ...], dict[tuple[str, str], tuple[EvidenceReference, ...]]]:
        valid: list[RelationshipRecord] = []
        evidence_by_relationship: dict[tuple[str, str], tuple[EvidenceReference, ...]] = {}
        for relationship in relationships:
            evidence = _resolve_graph_evidence(self._metadata_store, relationship.evidence_refs)
            if not evidence:
                warnings.append(
                    GraphRetrievalWarning(
                        code="graph_evidence_missing",
                        message="Relationship graph evidence could not be resolved from metadata.",
                        severity="warning",
                        affected_vault_ids=(relationship.source_vault_id,),
                        relationship_id=relationship.relationship_id,
                    )
                )
                continue
            key = (relationship.source_vault_id, relationship.relationship_id)
            evidence_by_relationship[key] = evidence
            valid.append(relationship)
        return tuple(valid), evidence_by_relationship

    def _related_item_from_path(
        self,
        *,
        path: GraphPath,
        entities: dict[tuple[str, str], EntityRecord],
        relationships: dict[tuple[str, str], RelationshipRecord],
        relationship_evidence: dict[tuple[str, str], tuple[EvidenceReference, ...]],
        rank: int,
    ) -> RelatedItem:
        target_key = (path.target.vault_id, path.target.entity_id)
        relationship_path = tuple(
            relationships[(edge.source_vault_id, edge.relationship_id)] for edge in path.edges
        )
        evidence = _dedupe_evidence(
            tuple(
                item
                for relationship in relationship_path
                for item in relationship_evidence[(relationship.source_vault_id, relationship.relationship_id)]
            )
        )
        return RelatedItem(
            rank=rank,
            entity=entities[target_key],
            relationship_path=relationship_path,
            evidence=evidence,
            score=path.score,
            explanation=path.explanation,
        )


@dataclass(frozen=True)
class _TargetResolution:
    entity: EntityRecord | None
    candidates: tuple[EntityRecord, ...]
    warning: GraphRetrievalWarning | None


@dataclass(frozen=True)
class _TraversalResult:
    relationships: tuple[RelationshipRecord, ...]
    relationships_by_identity: dict[tuple[str, str], RelationshipRecord]
    entities: tuple[EntityRecord, ...]
    entities_by_identity: dict[tuple[str, str], EntityRecord]


def _actual_scopes(
    *,
    catalog: VaultCatalog,
    requested_scope: QueryScope,
    include_cross_vault: bool,
) -> tuple[QueryScope, ...]:
    scopes = actual_query_scopes(catalog=catalog, scope=requested_scope)
    if not include_cross_vault:
        return scopes
    return tuple(
        QueryScope(vault_ids=scope.vault_ids, content_scopes=scope.content_scopes, include_cross_vault=True)
        for scope in scopes
    )


def _projection_direction(direction: str) -> Literal["out", "in", "both"]:
    if direction not in ("out", "in", "both"):
        raise SearchError("unsupported graph traversal direction")
    return cast(Literal["out", "in", "both"], direction)


def _raise_fatal_readiness(readiness: GraphReadiness) -> None:
    if readiness.freshness in {"incompatible", "unavailable"}:
        raise SearchError(f"graph_{readiness.freshness}: {readiness.recovery_hint}")


def _fresh_scopes_with_warnings(
    *,
    readiness: GraphReadiness,
    actual_scopes: tuple[QueryScope, ...],
) -> tuple[tuple[QueryScope, ...], list[GraphRetrievalWarning]]:
    rows_by_scope = {row.actual_scope: row for row in readiness.scope_readiness}
    fresh: list[QueryScope] = []
    warnings: list[GraphRetrievalWarning] = []
    for scope in actual_scopes:
        row = rows_by_scope.get(graph_scope_key(scope))
        freshness = row.freshness if row is not None else "missing"
        if freshness == "fresh":
            fresh.append(scope)
            continue
        warning_code = {
            "empty": "graph_empty",
            "missing": "graph_missing",
            "stale": "graph_stale",
        }.get(freshness, f"graph_{freshness}")
        warnings.append(
            GraphRetrievalWarning(
                code=warning_code,
                message=f"Graph scope is {freshness}; run `vg index` to refresh graph state.",
                severity="warning",
                affected_vault_ids=scope.vault_ids,
                scope_key=graph_scope_key(scope),
            )
        )
    return tuple(fresh), warnings


def _resolve_target(matches: Iterable[GraphEntityMatch]) -> _TargetResolution:
    typed_matches = tuple(matches)
    candidates = tuple(match.entity for match in typed_matches)
    exact_matches = tuple(
        match
        for match in typed_matches
        if match.match_kind in {"entity_id", "canonical_path", "normalized_name", "alias"}
    )
    if not exact_matches:
        return _TargetResolution(
            entity=None,
            candidates=candidates,
            warning=GraphRetrievalWarning(
                code="target_not_found",
                message="Graph target was not found as an exact entity, path, name, or alias match.",
                severity="warning",
                affected_vault_ids=_candidate_vault_ids(candidates),
            ),
        )
    best_rank = min(match.match_rank for match in exact_matches)
    best = tuple(match for match in exact_matches if match.match_rank == best_rank)
    best_entities = tuple(match.entity for match in best)
    if len({(entity.vault_id, entity.entity_id) for entity in best_entities}) != 1:
        return _TargetResolution(
            entity=None,
            candidates=best_entities,
            warning=GraphRetrievalWarning(
                code="ambiguous_graph_target",
                message="Graph target matched multiple equal-rank entities.",
                severity="warning",
                affected_vault_ids=_candidate_vault_ids(best_entities),
            ),
        )
    return _TargetResolution(entity=best_entities[0], candidates=candidates, warning=None)


def _relationship_endpoints(relationship: RelationshipRecord) -> tuple[GraphEntityIdentity, GraphEntityIdentity]:
    return (
        GraphEntityIdentity(relationship.source_vault_id, relationship.source_entity_id),
        GraphEntityIdentity(relationship.target_vault_id, relationship.target_entity_id),
    )


def _resolve_graph_evidence(
    metadata_store: MetadataStore,
    refs: tuple[GraphEvidenceRef, ...],
) -> tuple[EvidenceReference, ...]:
    evidence: list[EvidenceReference] = []
    for ref in refs:
        resolved = metadata_store.resolve_chunk_evidence(
            vault_id=ref.evidence_vault_id,
            document_id=ref.document_id,
            chunk_id=ref.chunk_id,
        )
        if resolved is not None:
            evidence.append(resolved)
    return _dedupe_evidence(tuple(evidence))


def _dedupe_evidence(evidence: tuple[EvidenceReference, ...]) -> tuple[EvidenceReference, ...]:
    deduped: dict[tuple[str, str, str], EvidenceReference] = {}
    for item in evidence:
        deduped.setdefault((item.vault_id, item.document_id, item.chunk_id), item)
    return tuple(deduped.values())


def _projection_node(entity: EntityRecord) -> GraphProjectionNode:
    return GraphProjectionNode(
        vault_id=entity.vault_id,
        entity_id=entity.entity_id,
        type=entity.type,
        name=entity.name,
        normalized_name=entity.normalized_name,
    )


def _projection_edge(relationship: RelationshipRecord) -> GraphProjectionEdge:
    return GraphProjectionEdge(
        source_vault_id=relationship.source_vault_id,
        source_entity_id=relationship.source_entity_id,
        target_vault_id=relationship.target_vault_id,
        target_entity_id=relationship.target_entity_id,
        relationship_id=relationship.relationship_id,
        relationship_type=relationship.type,
        status=relationship.status,
        confidence=relationship.confidence,
        evidence_ref_ids=tuple(ref.evidence_ref_id for ref in relationship.evidence_refs),
        graph_index_revision=relationship.graph_index_revision,
    )


def _empty_related_response(
    *,
    target: str,
    requested_scope: QueryScope,
    actual_scopes: tuple[QueryScope, ...],
    warnings: list[GraphRetrievalWarning],
    target_candidates: tuple[EntityRecord, ...] = (),
) -> RelatedResponse:
    return RelatedResponse(
        target=target,
        resolved_target=None,
        target_candidates=target_candidates,
        requested_scope=requested_scope,
        actual_scopes=actual_scopes,
        projection_build_id=None,
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=0,
        items=(),
        warnings=tuple(warnings),
        store_revisions=(),
        generated_at=datetime.now(UTC).isoformat(),
    )


def _store_revisions(
    *,
    readiness: GraphReadiness,
    projection_build_id: str,
    evidence: tuple[EvidenceReference, ...],
) -> tuple[GraphRetrievalRevision, ...]:
    revisions: list[GraphRetrievalRevision] = []
    for row in readiness.scope_readiness:
        if row.last_graph_revision:
            revisions.append(
                GraphRetrievalRevision(
                    kind="graph",
                    revision=row.last_graph_revision,
                    scope_key=row.actual_scope,
                    vault_id=row.vault_id,
                )
            )
    for item in evidence:
        if item.metadata_index_revision:
            revisions.append(
                GraphRetrievalRevision(
                    kind="metadata",
                    revision=item.metadata_index_revision,
                    scope_key=f"{item.vault_id}:{item.path.split('/', 1)[0]}:local",
                    vault_id=item.vault_id,
                )
            )
    revisions.append(
        GraphRetrievalRevision(kind="projection", revision=projection_build_id, scope_key="projection")
    )
    return tuple(revisions)


def _affected_vault_ids(scopes: tuple[QueryScope, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(vault_id for scope in scopes for vault_id in scope.vault_ids))


def _candidate_vault_ids(candidates: tuple[EntityRecord, ...]) -> tuple[str, ...]:
    vault_ids = tuple(dict.fromkeys(candidate.vault_id for candidate in candidates))
    return vault_ids or ("unknown",)
