from __future__ import annotations

import threading
from collections.abc import Callable, Hashable, Sequence
from pathlib import Path
from typing import Protocol

from vault_graph.operation.readiness.search_readiness import (
    SearchReadinessReport,
    SearchScopeReadiness,
    SearchStoreRevision,
)
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.keyword_index import KeywordIndex
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.interfaces.store_health import StoreHealth
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore


class VectorStaleCounter(Protocol):
    """Counts vector records that differ from the metadata chunks of one scope."""

    def stale_count(self, *, scope: QueryScope) -> int | None: ...


# Spec 2026-11-11 §4.2.6: the stale counts and store revisions of the scopes last checked, keyed by the store files'
# signature. Module level, so services opened again in one process (an MCP tool call) reuse it.
_ScopeResult = tuple[tuple[SearchScopeReadiness, ...], tuple[SearchStoreRevision, ...]]
_SCOPE_RESULTS: dict[Hashable, dict[tuple[str, ...], _ScopeResult]] = {}
_SCOPE_RESULTS_LOCK = threading.Lock()


def sqlite_files_signature(paths: Sequence[Path]) -> Hashable:
    """Path, inode, size and modification time of each SQLite file and its `-wal` file. Any committed write changes
    one of them."""
    entries: list[tuple[str, tuple[int, int, int] | None]] = []
    for path in paths:
        for candidate in (path, path.with_name(f"{path.name}-wal")):
            try:
                stat = candidate.stat()
            except OSError:
                entries.append((str(candidate), None))
                continue
            entries.append((str(candidate), (stat.st_ino, stat.st_size, stat.st_mtime_ns)))
    return tuple(entries)


class ReadOnlySearchReadiness:
    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        keyword_index: KeywordIndex,
        vector_store: VectorStore | None = None,
        text_embeddings: TextEmbeddings | None = None,
        vector_stale_counter: VectorStaleCounter | None = None,
        store_signature: Callable[[], Hashable] | None = None,
    ) -> None:
        """``store_signature`` returns a value that changes whenever the stores change. With it, the stale counts and
        store revisions are computed again only when it changes. Without it they are computed on every check."""
        self._metadata_store = metadata_store
        self._keyword_index = keyword_index
        self._vector_store = vector_store
        self._text_embeddings = text_embeddings
        self._vector_stale_counter = vector_stale_counter
        self._store_signature = store_signature

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        metadata_health = self._metadata_store.health()
        keyword_health = self._keyword_index.health()
        vector_health = self._vector_store.health() if self._vector_store is not None else None
        if not metadata_health.ok or not metadata_health.schema_compatible:
            return SearchReadinessReport(
                metadata_health=metadata_health,
                keyword_health=keyword_health,
                vector_health=vector_health,
                vector_stale_count=None,
                can_embed_without_download=False,
                store_revisions=(),
                scope_readiness=(),
            )
        if not keyword_health.ok or not keyword_health.schema_compatible:
            return SearchReadinessReport(
                metadata_health=metadata_health,
                keyword_health=keyword_health,
                vector_health=vector_health,
                vector_stale_count=None,
                can_embed_without_download=False,
                store_revisions=(),
                scope_readiness=(),
            )
        can_embed = self._text_embeddings.can_embed_without_download() if self._text_embeddings is not None else False
        scope_readiness, store_revisions = self._scope_results(actual_scopes=actual_scopes, vector_health=vector_health)
        stale_counts = tuple(item.vector_stale_count for item in scope_readiness if item.vector_stale_count is not None)
        stale_count = sum(stale_counts) if stale_counts else None
        return SearchReadinessReport(
            metadata_health=metadata_health,
            keyword_health=keyword_health,
            vector_health=vector_health,
            vector_stale_count=stale_count,
            can_embed_without_download=can_embed,
            store_revisions=store_revisions,
            scope_readiness=scope_readiness,
        )

    def _scope_results(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> _ScopeResult:
        if self._store_signature is None:
            return self._compute_scope_results(actual_scopes=actual_scopes, vector_health=vector_health)
        # Read before computing, so a write during the computation changes the signature for the next check.
        signature = self._store_signature()
        # Vector health and the embedding model are part of the key: stale counts depend on both.
        model = repr(self._text_embeddings.model_spec()) if self._text_embeddings is not None else "none"
        scopes_key = (
            *(_scope_key(scope) for scope in actual_scopes),
            f"vector_ok:{_vector_usable(vector_health)}",
            f"model:{model}",
        )
        with _SCOPE_RESULTS_LOCK:
            cached = _SCOPE_RESULTS.get(signature, {}).get(scopes_key)
        if cached is not None:
            return cached
        result = self._compute_scope_results(actual_scopes=actual_scopes, vector_health=vector_health)
        with _SCOPE_RESULTS_LOCK:
            if signature not in _SCOPE_RESULTS:
                _SCOPE_RESULTS.clear()
            _SCOPE_RESULTS.setdefault(signature, {})[scopes_key] = result
        return result

    def _compute_scope_results(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> _ScopeResult:
        return (
            self._scope_readiness(actual_scopes=actual_scopes, vector_health=vector_health),
            self._store_revisions(actual_scopes=actual_scopes, vector_health=vector_health),
        )

    def _scope_readiness(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> tuple[SearchScopeReadiness, ...]:
        readiness: list[SearchScopeReadiness] = []
        for scope in actual_scopes:
            stale_count = self._vector_stale_count(scope=scope, vector_health=vector_health)
            readiness.append(
                SearchScopeReadiness(
                    scope_key=_scope_key(scope),
                    vault_ids=scope.vault_ids,
                    vector_stale_count=stale_count,
                )
            )
        return tuple(readiness)

    def _vector_stale_count(self, *, scope: QueryScope, vector_health: StoreHealth | None) -> int | None:
        if self._vector_store is None or self._text_embeddings is None or vector_health is None:
            return None
        if not vector_health.ok or not vector_health.schema_compatible:
            return None
        if self._vector_stale_counter is None:
            return None
        return self._vector_stale_counter.stale_count(scope=scope)

    def _store_revisions(
        self,
        *,
        actual_scopes: tuple[QueryScope, ...],
        vector_health: StoreHealth | None,
    ) -> tuple[SearchStoreRevision, ...]:
        revisions: list[SearchStoreRevision] = []
        for scope in actual_scopes:
            scope_key = _scope_key(scope)
            chunks = self._metadata_store.list_chunks(scope)
            metadata_revision = _revision_from_values(
                tuple(chunk.index_revision for chunk in chunks),
                fallback=f"empty:{self._metadata_store.health().schema_version}",
            )
            vault_id = scope.vault_ids[0] if len(scope.vault_ids) == 1 else None
            revisions.append(
                SearchStoreRevision(kind="metadata", revision=metadata_revision, scope_key=scope_key, vault_id=vault_id)
            )
            revisions.append(
                SearchStoreRevision(
                    kind="keyword",
                    revision=self._keyword_index.index_revision(scope),
                    scope_key=scope_key,
                    vault_id=vault_id,
                )
            )
            if self._vector_store is not None and vector_health is not None and vector_health.ok:
                manifest = self._vector_store.export_manifest(scope)
                vector_revision = _revision_from_values(
                    tuple(row.vector_index_revision for row in manifest),
                    fallback=f"empty:{vector_health.schema_version}",
                )
                revisions.append(
                    SearchStoreRevision(
                        kind="vector",
                        revision=vector_revision,
                        scope_key=scope_key,
                        vault_id=vault_id,
                    )
                )
        return tuple(revisions)


def _vector_usable(vector_health: StoreHealth | None) -> bool:
    return vector_health is not None and vector_health.ok and vector_health.schema_compatible


def _scope_key(scope: QueryScope) -> str:
    return f"{','.join(scope.vault_ids)}:{','.join(scope.content_scopes)}"


def _revision_from_values(values: tuple[str | None, ...], *, fallback: str) -> str:
    revisions = tuple(sorted({value for value in values if value}))
    return ",".join(revisions) if revisions else fallback
