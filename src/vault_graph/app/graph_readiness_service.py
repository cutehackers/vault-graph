from __future__ import annotations

from vault_graph.errors import GraphStoreError, GraphStoreUnavailable
from vault_graph.graph.graph_contracts import GraphExtractionSpec, GraphManifest, GraphManifestEvidence, GraphRevision
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.graph.graph_readiness import (
    GraphLineageScope,
    GraphReadiness,
    GraphScopeReadiness,
)
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth


class ReadOnlyGraphReadiness:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        expected_spec: GraphExtractionSpec,
    ) -> None:
        self._metadata_store = metadata_store
        self._graph_store = graph_store
        self._expected_spec = expected_spec

    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        graph_health = self._graph_store.health()
        if not graph_health.ok:
            return self._readiness_from_unhealthy_store(
                graph_health=graph_health,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
            )
        metadata_health = self._metadata_store.health()
        if not metadata_health.ok or not metadata_health.schema_compatible:
            return self._metadata_unavailable_readiness(
                graph_health=graph_health,
                metadata_health=metadata_health,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
            )
        try:
            stored_specs = self._graph_store.stored_specs()
            latest_revisions = self._graph_store.latest_revisions(actual_scopes)
            manifest = self._graph_store.current_manifest(actual_scopes)
        except (GraphStoreUnavailable, GraphStoreError) as exc:
            return self._unavailable_readiness(
                graph_health=graph_health,
                requested_scope=requested_scope,
                actual_scopes=actual_scopes,
                message=str(exc),
            )
        metadata_lineage = self._metadata_lineage(actual_scopes)
        evidence_warnings_by_scope = _evidence_warnings_by_scope(
            metadata_store=self._metadata_store,
            manifest=manifest,
            actual_scopes=actual_scopes,
        )
        spec_compatible = _graph_spec_compatible(
            stored_specs=stored_specs,
            latest_revisions=latest_revisions,
            expected_spec=self._expected_spec,
        )
        scope_readiness = self._scope_readiness(
            actual_scopes=actual_scopes,
            graph_health=graph_health,
            latest_revisions=latest_revisions,
            metadata_lineage=metadata_lineage,
            manifest=manifest,
            evidence_warnings_by_scope=evidence_warnings_by_scope,
            spec_compatible=spec_compatible,
        )
        freshness = _aggregate_freshness(tuple(row.freshness for row in scope_readiness))
        warnings = tuple(dict.fromkeys(warning for row in scope_readiness for warning in row.warnings))
        last_graph_revision = _last_revision(scope_readiness)
        return GraphReadiness(
            backend_name=graph_health.backend,
            backend_available=True,
            schema_version=graph_health.schema_version,
            schema_compatible=graph_health.schema_compatible,
            graph_extraction_spec_version=self._expected_spec.spec_version,
            graph_extraction_spec_digest=self._expected_spec.spec_digest,
            graph_extraction_spec_compatible=spec_compatible,
            freshness=freshness,
            stale_count=sum(row.stale_count for row in scope_readiness),
            tombstone_count=sum(row.tombstone_count for row in scope_readiness),
            last_graph_revision=last_graph_revision,
            affected_vault_ids=requested_scope.vault_ids,
            scope_readiness=scope_readiness,
            warnings=warnings,
            recovery_hint=_recovery_hint(freshness, warnings),
        )

    def _readiness_from_unhealthy_store(
        self,
        *,
        graph_health: StoreHealth,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
    ) -> GraphReadiness:
        if "not initialized" in graph_health.message:
            freshness = "missing"
            recovery_hint = "run `vg index` after graph indexing is available"
        elif not graph_health.schema_compatible:
            freshness = "incompatible"
            recovery_hint = "rebuild graph state after upgrading Vault Graph"
        else:
            freshness = "unavailable"
            recovery_hint = graph_health.message
        return GraphReadiness(
            backend_name=graph_health.backend,
            backend_available=False,
            schema_version=graph_health.schema_version,
            schema_compatible=graph_health.schema_compatible,
            graph_extraction_spec_version=self._expected_spec.spec_version,
            graph_extraction_spec_digest=self._expected_spec.spec_digest,
            graph_extraction_spec_compatible=False,
            freshness=freshness,
            stale_count=0,
            tombstone_count=0,
            last_graph_revision=None,
            affected_vault_ids=requested_scope.vault_ids,
            scope_readiness=tuple(
                GraphScopeReadiness(
                    vault_id=scope.vault_ids[0],
                    actual_scope=graph_scope_key(scope),
                    freshness=freshness,
                    stale_count=0,
                    tombstone_count=0,
                    last_graph_revision=None,
                    warnings=(),
                )
                for scope in actual_scopes
            ),
            warnings=(),
            recovery_hint=recovery_hint,
        )

    def _unavailable_readiness(
        self,
        *,
        graph_health: StoreHealth,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
        message: str,
    ) -> GraphReadiness:
        return GraphReadiness(
            backend_name=graph_health.backend,
            backend_available=False,
            schema_version=graph_health.schema_version,
            schema_compatible=graph_health.schema_compatible,
            graph_extraction_spec_version=self._expected_spec.spec_version,
            graph_extraction_spec_digest=self._expected_spec.spec_digest,
            graph_extraction_spec_compatible=False,
            freshness="unavailable",
            stale_count=0,
            tombstone_count=0,
            last_graph_revision=None,
            affected_vault_ids=requested_scope.vault_ids,
            scope_readiness=tuple(
                GraphScopeReadiness(
                    vault_id=scope.vault_ids[0],
                    actual_scope=graph_scope_key(scope),
                    freshness="unavailable",
                    stale_count=0,
                    tombstone_count=0,
                    last_graph_revision=None,
                    warnings=(message,),
                )
                for scope in actual_scopes
            ),
            warnings=(message,),
            recovery_hint=message,
        )

    def _metadata_unavailable_readiness(
        self,
        *,
        graph_health: StoreHealth,
        metadata_health: StoreHealth,
        requested_scope: QueryScope,
        actual_scopes: tuple[QueryScope, ...],
    ) -> GraphReadiness:
        warning = f"metadata unavailable: {metadata_health.message}"
        return GraphReadiness(
            backend_name=graph_health.backend,
            backend_available=graph_health.ok,
            schema_version=graph_health.schema_version,
            schema_compatible=graph_health.schema_compatible,
            graph_extraction_spec_version=self._expected_spec.spec_version,
            graph_extraction_spec_digest=self._expected_spec.spec_digest,
            graph_extraction_spec_compatible=False,
            freshness="unavailable",
            stale_count=0,
            tombstone_count=0,
            last_graph_revision=None,
            affected_vault_ids=requested_scope.vault_ids,
            scope_readiness=tuple(
                GraphScopeReadiness(
                    vault_id=scope.vault_ids[0],
                    actual_scope=graph_scope_key(scope),
                    freshness="unavailable",
                    stale_count=0,
                    tombstone_count=0,
                    last_graph_revision=None,
                    warnings=(warning,),
                )
                for scope in actual_scopes
            ),
            warnings=(warning,),
            recovery_hint="restore metadata readiness before checking graph freshness",
        )

    def _metadata_lineage(self, actual_scopes: tuple[QueryScope, ...]) -> tuple[GraphLineageScope, ...]:
        metadata_health = self._metadata_store.health()
        lineage: list[GraphLineageScope] = []
        for scope in actual_scopes:
            chunks = self._metadata_store.list_chunks(scope)
            documents = tuple(
                document
                for document in self._metadata_store.list_document_states(scope.vault_ids)
                if _path_in_content_scope(path=document.path, content_scopes=scope.content_scopes)
            )
            lineage.append(
                GraphLineageScope(
                    vault_id=scope.vault_ids[0],
                    actual_scope=graph_scope_key(scope),
                    metadata_index_revision=_revision_from_values(
                        tuple(chunk.index_revision for chunk in chunks),
                        fallback=f"empty:{metadata_health.schema_version}",
                    ),
                    parser_version=_revision_from_values(
                        tuple(document.parser_version for document in documents if not document.is_tombstoned),
                        fallback="unknown",
                    ),
                    chunker_version=_revision_from_values(
                        tuple(chunk.chunker_version for chunk in chunks),
                        fallback="empty",
                    ),
                )
            )
        return tuple(lineage)

    def _scope_readiness(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        graph_health: StoreHealth,
        latest_revisions: tuple[GraphRevision, ...],
        metadata_lineage: tuple[GraphLineageScope, ...],
        manifest: GraphManifest,
        evidence_warnings_by_scope: dict[str, tuple[str, ...]],
        spec_compatible: bool,
    ) -> tuple[GraphScopeReadiness, ...]:
        revisions_by_scope = {revision.actual_scope: revision for revision in latest_revisions}
        lineage_by_scope = {lineage.actual_scope: lineage for lineage in metadata_lineage}
        tombstones_by_scope = _tombstone_counts_by_scope(manifest)
        readiness: list[GraphScopeReadiness] = []
        for scope in actual_scopes:
            scope_key = graph_scope_key(scope)
            revision = revisions_by_scope.get(scope_key)
            lineage = lineage_by_scope[scope_key]
            warnings: list[str] = []
            if revision is None:
                freshness = "empty"
            elif not spec_compatible:
                freshness = "incompatible"
            elif revision.graph_store_schema_version != graph_health.schema_version:
                freshness = "stale"
                warnings.append("stale graph schema lineage")
            elif revision.graph_extraction_spec_digest != self._expected_spec.spec_digest:
                freshness = "stale"
                warnings.append("stale graph extraction spec")
            elif (
                revision.metadata_index_revision != lineage.metadata_index_revision
                or revision.parser_version != lineage.parser_version
                or revision.chunker_version != lineage.chunker_version
            ):
                freshness = "stale"
                warnings.append("stale graph metadata lineage")
            elif evidence_warnings_by_scope.get(scope_key):
                freshness = "stale"
                warnings.extend(evidence_warnings_by_scope[scope_key])
            else:
                freshness = "fresh"
            stale_count = len(warnings) + (revision.stale_count if revision is not None else 0)
            readiness.append(
                GraphScopeReadiness(
                    vault_id=scope.vault_ids[0],
                    actual_scope=scope_key,
                    freshness=freshness,
                    stale_count=stale_count,
                    tombstone_count=tombstones_by_scope.get(scope_key, 0)
                    + (revision.tombstone_count if revision is not None else 0),
                    last_graph_revision=revision.graph_index_revision if revision is not None else None,
                    warnings=tuple(warnings),
                )
            )
        return tuple(readiness)


def _evidence_warnings_by_scope(
    *,
    metadata_store: MetadataStore,
    manifest: GraphManifest,
    actual_scopes: tuple[QueryScope, ...],
) -> dict[str, tuple[str, ...]]:
    scope_by_vault_id = {scope.vault_ids[0]: graph_scope_key(scope) for scope in actual_scopes}
    evidence_ids_by_scope: dict[str, set[str]] = {graph_scope_key(scope): set() for scope in actual_scopes}
    for entity in manifest.entity_rows:
        scope_key = scope_by_vault_id.get(entity.vault_id)
        if scope_key is not None:
            evidence_ids_by_scope[scope_key].update(entity.evidence_ref_ids)
    for relationship in manifest.relationship_rows:
        scope_key = scope_by_vault_id.get(relationship.source_vault_id)
        if scope_key is not None:
            evidence_ids_by_scope[scope_key].update(relationship.evidence_ref_ids)

    evidence_by_id = {evidence.evidence_ref_id: evidence for evidence in manifest.evidence_rows}
    warnings_by_scope: dict[str, tuple[str, ...]] = {}
    for scope_key, evidence_ids in evidence_ids_by_scope.items():
        warnings: list[str] = []
        for evidence_id in sorted(evidence_ids):
            evidence = evidence_by_id.get(evidence_id)
            if evidence is None:
                continue
            warning = _evidence_warning(metadata_store=metadata_store, evidence=evidence)
            if warning is not None:
                warnings.append(warning)
        warnings_by_scope[scope_key] = tuple(dict.fromkeys(warnings))
    return warnings_by_scope


def _evidence_warning(*, metadata_store: MetadataStore, evidence: GraphManifestEvidence) -> str | None:
    resolved = metadata_store.resolve_chunk_evidence(
        vault_id=evidence.evidence_vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
    )
    if resolved is None:
        return f"unresolved graph evidence: {evidence.evidence_vault_id}:{evidence.document_id}:{evidence.chunk_id}"
    if resolved.content_hash != evidence.content_hash:
        return f"stale graph evidence: {evidence.evidence_vault_id}:{evidence.document_id}:{evidence.chunk_id}"
    return None


def _tombstone_counts_by_scope(manifest: GraphManifest) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tombstone in manifest.tombstone_rows:
        counts[tombstone.actual_scope] = counts.get(tombstone.actual_scope, 0) + 1
    return counts


def _graph_spec_compatible(
    *,
    stored_specs: tuple[GraphExtractionSpec, ...],
    latest_revisions: tuple[GraphRevision, ...],
    expected_spec: GraphExtractionSpec,
) -> bool:
    if any(
        revision.graph_extraction_spec_version != expected_spec.spec_version
        or revision.graph_extraction_spec_digest != expected_spec.spec_digest
        for revision in latest_revisions
    ):
        return False
    return not any(
        spec.spec_version == expected_spec.spec_version and spec.spec_digest != expected_spec.spec_digest
        for spec in stored_specs
    )


def _aggregate_freshness(values: tuple[str, ...]) -> str:
    severity = ("unavailable", "incompatible", "stale", "empty", "missing", "fresh")
    for status in severity:
        if status in values:
            return status
    return "empty"


def _last_revision(scope_readiness: tuple[GraphScopeReadiness, ...]) -> str | None:
    revisions = tuple(row.last_graph_revision for row in scope_readiness if row.last_graph_revision is not None)
    return revisions[-1] if revisions else None


def _recovery_hint(freshness: str, warnings: tuple[str, ...]) -> str:
    if freshness == "missing":
        return "run `vg index` after graph indexing is available"
    if freshness == "empty":
        return "run `vg index` after graph indexing is available"
    if freshness == "incompatible":
        return "rebuild graph state after upgrading Vault Graph"
    if freshness == "stale" and any("graph evidence" in warning for warning in warnings):
        return "rerun metadata indexing, then graph indexing"
    if freshness == "stale":
        return "rerun `vg index` after metadata changes"
    if freshness == "unavailable":
        return "inspect graph state and rerun `vg status`"
    return "ok"


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback


def _path_in_content_scope(*, path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == content_scope or path.startswith(f"{content_scope}/") for content_scope in content_scopes)
