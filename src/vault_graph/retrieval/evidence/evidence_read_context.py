"""Assemble evidence reads over already selected, read-only projection handles."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from typing import Protocol, cast

from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.evidence.evidence_linking import EvidenceLinker, EvidenceSourceRevision
from vault_graph.retrieval.graph.graph_identity import graph_scope_key
from vault_graph.retrieval.graph.graph_readiness import GraphReadiness
from vault_graph.storage.interfaces.evidence_owner_lookup import EvidenceOwnerLookup
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore


class EvidenceReadiness(Protocol):
    def check(self, *, requested_scope: QueryScope, actual_scopes: tuple[QueryScope, ...]) -> GraphReadiness: ...


def build_evidence_linker(
    *,
    metadata_store: MetadataStore,
    graph_store: GraphStore,
    readiness: EvidenceReadiness,
    read_context_id: str,
) -> EvidenceLinker:
    """No stores are opened here. Factories pin the selected projection paths."""

    def check(scopes: tuple[QueryScope, ...]) -> GraphReadiness:
        return readiness.check(
            requested_scope=QueryScope(
                vault_ids=tuple(dict.fromkeys(scope.vault_ids[0] for scope in scopes)),
                content_scopes=tuple(dict.fromkeys(prefix for scope in scopes for prefix in scope.content_scopes)),
            ),
            actual_scopes=scopes,
        )

    def revisions(scopes: tuple[QueryScope, ...]) -> tuple[EvidenceSourceRevision, ...]:
        # Full lineage/readiness cost is separate from the bounded owner lookup.
        rows = [EvidenceSourceRevision("generation", read_context_id)]
        for scope in scopes:
            chunks = metadata_store.list_chunks(scope)
            scope_key = graph_scope_key(scope)
            fingerprint = hashlib.sha256(
                repr(
                    sorted(
                        (chunk.vault_id, chunk.document_id, chunk.chunk_id, chunk.index_revision, chunk.content_hash)
                        for chunk in chunks
                    )
                ).encode()
            ).hexdigest()
            rows.append(EvidenceSourceRevision("metadata_fingerprint", fingerprint, scope_key))
            rows.extend(
                EvidenceSourceRevision("metadata", value, scope_key)
                for value in sorted({chunk.index_revision for chunk in chunks if chunk.index_revision})
            )
        rows.extend(
            EvidenceSourceRevision("graph", row.graph_index_revision, row.actual_scope)
            for row in graph_store.latest_revisions(
                tuple(
                    dict.fromkeys(
                        candidate
                        for scope in scopes
                        for candidate in (scope, replace(scope, include_cross_vault=False))
                    )
                )
            )
        )
        native_revisions = getattr(graph_store, "evidence_lookup_revisions", None)
        if callable(native_revisions):
            rows.extend(
                EvidenceSourceRevision("graph_document", str(revision), str(scope))
                for scope, revision in native_revisions()
            )
        return tuple(rows)

    lookup = (
        cast(EvidenceOwnerLookup, graph_store)
        if callable(getattr(graph_store, "lookup_evidence_owners", None))
        else None
    )
    return EvidenceLinker(
        metadata_store=metadata_store,
        owner_lookup=lookup,
        readiness=check,
        revision_reader=revisions,
    )
