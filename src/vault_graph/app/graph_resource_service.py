from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from vault_graph.app.graph_retrieval_service import GraphReadinessChecker
from vault_graph.errors import CatalogError, GraphStoreError
from vault_graph.graph.graph_contracts import EntityRecord, GraphEvidenceRef, RelationshipRecord
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_query import GraphEntityIdentity, GraphEntityQuery, GraphRelationshipQuery
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.query_scope_resolution import actual_query_scopes
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph_retrieval import GraphRetrievalRevision
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore

GraphResourceWarningSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class GraphResourceWarning:
    code: str
    message: str
    severity: GraphResourceWarningSeverity
    affected_vault_ids: tuple[str, ...]
    recovery_hint: str | None = None


@dataclass(frozen=True)
class GraphEntityResource:
    entity: EntityRecord
    evidence: tuple[EvidenceReference, ...]
    related_relationships: tuple[RelationshipRecord, ...]
    warnings: tuple[GraphResourceWarning, ...]
    store_revisions: tuple[GraphRetrievalRevision, ...]


class GraphResourceService:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        graph_readiness: GraphReadinessChecker,
    ) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store
        self._graph_store = graph_store
        self._graph_readiness = graph_readiness

    def get_entity(
        self,
        *,
        vault_id: str,
        entity_id: str,
    ) -> GraphEntityResource:
        actual_scopes, warnings, readiness = self._ready_graph_scopes(vault_id=vault_id)
        entity = self._graph_store.get_entity(vault_id=vault_id, entity_id=entity_id)
        if entity is None or entity.status != "active":
            raise GraphStoreError(f"resource_not_found: graph entity not found: {vault_id}:{entity_id}")
        relationships = self._graph_store.relationships_for_entities(
            GraphRelationshipQuery(
                seeds=(GraphEntityIdentity(vault_id, entity_id),),
                actual_scopes=actual_scopes,
                direction="both",
                statuses=("stated", "inferred", "contested", "deprecated"),
                include_cross_vault=False,
                limit=200,
            )
        )
        evidence, evidence_warnings = self._resolve_evidence(
            entity.evidence_refs + tuple(ref for item in relationships.relationships for ref in item.evidence_refs)
        )
        warnings.extend(evidence_warnings)
        return GraphEntityResource(
            entity=entity,
            evidence=evidence,
            related_relationships=relationships.relationships,
            warnings=tuple(warnings),
            store_revisions=_store_revisions(readiness=readiness, evidence=evidence),
        )

    def find_concept(
        self,
        *,
        vault_id: str,
        name: str,
    ) -> GraphEntityResource:
        actual_scopes, warnings, readiness = self._ready_graph_scopes(vault_id=vault_id)
        result = self._graph_store.find_entities(GraphEntityQuery(text=name, actual_scopes=actual_scopes, limit=20))
        normalized = _normalize_concept_name(name)
        matches = tuple(
            match.entity
            for match in result.matches
            if match.entity.status == "active"
            and (
                match.entity.normalized_name == normalized
                or normalized in {_normalize_concept_name(alias) for alias in match.entity.aliases}
            )
        )
        if not matches:
            raise GraphStoreError(f"resource_not_found: graph concept not found: {name}")
        unique = tuple({(entity.vault_id, entity.entity_id): entity for entity in matches}.values())
        if len(unique) > 1:
            raise GraphStoreError(f"ambiguous_resource: graph concept has multiple exact matches: {name}")
        entity = unique[0]
        relationships = self._graph_store.relationships_for_entities(
            GraphRelationshipQuery(
                seeds=(GraphEntityIdentity(entity.vault_id, entity.entity_id),),
                actual_scopes=actual_scopes,
                direction="both",
                statuses=("stated", "inferred", "contested", "deprecated"),
                include_cross_vault=False,
                limit=200,
            )
        )
        evidence, evidence_warnings = self._resolve_evidence(
            entity.evidence_refs + tuple(ref for item in relationships.relationships for ref in item.evidence_refs)
        )
        warnings.extend(evidence_warnings)
        return GraphEntityResource(
            entity=entity,
            evidence=evidence,
            related_relationships=relationships.relationships,
            warnings=tuple(warnings),
            store_revisions=_store_revisions(readiness=readiness, evidence=evidence),
        )

    def _ready_graph_scopes(
        self,
        *,
        vault_id: str,
    ) -> tuple[tuple[QueryScope, ...], list[GraphResourceWarning], GraphReadiness]:
        entry = self._catalog.resolve(vault_id)
        if not entry.enabled:
            raise CatalogError(f"disabled vault_id: {vault_id}")
        requested_scope = self._catalog.scope_for_vault_ids((vault_id,))
        actual_scopes = actual_query_scopes(catalog=self._catalog, scope=requested_scope)
        readiness = self._graph_readiness.check(requested_scope=requested_scope, actual_scopes=actual_scopes)
        if readiness.freshness in {"incompatible", "unavailable"}:
            raise GraphStoreError(f"graph_{readiness.freshness}: {readiness.recovery_hint}")
        fresh_scopes, warnings = _fresh_scopes_with_warnings(readiness=readiness, actual_scopes=actual_scopes)
        if not fresh_scopes:
            raise GraphStoreError(f"graph_unavailable: {readiness.recovery_hint}")
        return fresh_scopes, warnings, readiness

    def _resolve_evidence(
        self,
        refs: tuple[GraphEvidenceRef, ...],
    ) -> tuple[tuple[EvidenceReference, ...], list[GraphResourceWarning]]:
        evidence: list[EvidenceReference] = []
        warnings: list[GraphResourceWarning] = []
        seen: set[tuple[str, str, str]] = set()
        for ref in refs:
            key = (ref.evidence_vault_id, ref.document_id, ref.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            resolved = self._metadata_store.resolve_chunk_evidence(
                vault_id=ref.evidence_vault_id,
                document_id=ref.document_id,
                chunk_id=ref.chunk_id,
            )
            if resolved is None:
                warnings.append(
                    GraphResourceWarning(
                        code="missing_evidence",
                        message=f"Graph evidence is missing: {ref.evidence_ref_id}",
                        severity="warning",
                        affected_vault_ids=(ref.evidence_vault_id,),
                        recovery_hint="Re-run vg index for the selected Vault.",
                    )
                )
            else:
                evidence.append(resolved)
        return tuple(evidence), warnings


def _fresh_scopes_with_warnings(
    *,
    readiness: GraphReadiness,
    actual_scopes: tuple[QueryScope, ...],
) -> tuple[tuple[QueryScope, ...], list[GraphResourceWarning]]:
    rows_by_scope = {row.actual_scope: row for row in readiness.scope_readiness}
    fresh: list[QueryScope] = []
    warnings: list[GraphResourceWarning] = []
    for scope in actual_scopes:
        row = rows_by_scope.get(graph_scope_key(scope))
        freshness = row.freshness if row is not None else "missing"
        if freshness == "fresh":
            fresh.append(scope)
            continue
        warnings.append(
            GraphResourceWarning(
                code={"empty": "graph_empty", "missing": "graph_missing", "stale": "graph_stale"}.get(
                    freshness,
                    f"graph_{freshness}",
                ),
                message=f"Graph scope is {freshness}; run `vg index` to refresh graph state.",
                severity="warning",
                affected_vault_ids=scope.vault_ids,
                recovery_hint="Run vg index for the selected Vault.",
            )
        )
    return tuple(fresh), warnings


def _store_revisions(
    *,
    readiness: GraphReadiness,
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
    return tuple(revisions)


def _normalize_concept_name(value: str) -> str:
    return " ".join(value.casefold().split())
