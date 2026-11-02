"""Refresh the metadata projection of the linked Vaults before session start recall (F1).

A page saved in one session, accepted from review or captured from a transcript must show in the
next session's recall without the user running ``vg index``. ``vg hook session-start`` therefore
re-reads the linked, already indexed Vaults and publishes a new projection generation when a file
changed. The run uses the same metadata indexer, graph indexer and generation publisher as
``vg index``, with these differences:

- No embeddings. New and changed chunks keep no vector or an old one until the next ``vg index``,
  which search readiness reports as stale vectors. Vectors of chunks that no longer exist are
  removed so the published generation passes the same hygiene check as ``vg index``.
- A time limit. The limit is checked before staging and again before publishing. A run past the
  limit publishes nothing and recall reads the current index. One step is never interrupted.
- Nothing changed means nothing is written. Vault files are never written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Literal

from vault_graph.context.pack.recall import RecallPorts
from vault_graph.indexing.index_service import IndexService
from vault_graph.indexing.metadata_indexer import MetadataIndexer
from vault_graph.indexing.publication.projection_generation import (
    ProjectionBundlePublisher,
    ProjectionGenerationManager,
)
from vault_graph.interface.composition.graph_store_factory import (
    document_store_path,
    open_graph_store,
    selected_graph_backend,
)
from vault_graph.interface.composition.local_index_service_factory import LocalIndexServiceBundle
from vault_graph.operation.scope.active_projection import active_projection_layout
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.storage.interfaces.vector_store import VectorTombstone
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

DEFAULT_REFRESH_BUDGET_S = 5.0

RefreshStatus = Literal["unchanged", "refreshed", "skipped", "failed"]


@dataclass(frozen=True)
class RecallIndexRefresh:
    status: RefreshStatus
    vault_ids: tuple[str, ...] = ()
    changed: int = 0
    deleted: int = 0
    reason: str | None = None

    @property
    def warning(self) -> str | None:
        """One line for stderr when the index was not brought up to date."""
        if self.status in ("unchanged", "refreshed") or self.reason is None:
            return None
        return " ".join(f"Index refresh {self.status}: {self.reason} Recall uses the existing index.".split())


def refresh_linked_vaults(
    cwd: Path, *, ports: RecallPorts, graph_home_path: Path, budget_s: float
) -> RecallIndexRefresh:
    """Refresh the indexed Vaults linked to ``cwd``. Never raises: a failure becomes a warning."""
    if budget_s <= 0:
        return RecallIndexRefresh(status="skipped")
    try:
        scope = ports.scope.resolve(cwd)
        vault_ids = tuple(vault_id for vault_id in scope.vault_ids if ports.documents.is_indexed(vault_id))
        if not vault_ids:
            return RecallIndexRefresh(status="skipped")
        return refresh_recall_index(graph_home_path=graph_home_path, vault_ids=vault_ids, budget_s=budget_s)
    except Exception as exc:  # noqa: BLE001 - the hook must print recall whatever the refresh did
        return RecallIndexRefresh(status="failed", reason=f"{type(exc).__name__}: {exc}.")


def refresh_recall_index(*, graph_home_path: Path, vault_ids: tuple[str, ...], budget_s: float) -> RecallIndexRefresh:
    started = monotonic()
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog = catalog_service.load_catalog()
    scope = catalog.scope_for_vault_ids(vault_ids)
    if active_projection_layout(catalog_service.graph_home_path) is None:
        return RecallIndexRefresh(
            status="skipped", vault_ids=vault_ids, reason="the index was not published by `vg index`."
        )
    plan = MetadataIndexer(
        catalog=catalog,
        metadata_store=SQLiteMetadataStore(catalog_service.metadata_path, initialize=False),
    ).plan(scope=scope)
    if not plan.changed_paths and not plan.deleted_paths:
        return RecallIndexRefresh(status="unchanged", vault_ids=vault_ids)

    def outcome(status: RefreshStatus, reason: str | None = None) -> RecallIndexRefresh:
        return RecallIndexRefresh(
            status=status,
            vault_ids=vault_ids,
            changed=len(plan.changed_paths),
            deleted=len(plan.deleted_paths),
            reason=reason,
        )

    if monotonic() - started > budget_s:
        return outcome("skipped", _time_limit(budget_s))

    bundle = _open_metadata_bundle(catalog_service, catalog)
    try:
        report = bundle.index_service.run_apply(scope=scope)
        if report.exit_code:
            error = getattr(report.graph, "error", None) or "graph index failed."
            return outcome("failed", str(error))
        _drop_vectors_of_removed_chunks(catalog_service, scope)
        if monotonic() - started > budget_s:
            return outcome("skipped", _time_limit(budget_s))
        bundle.commit_projection(report)
    finally:
        bundle.close()
    return outcome("refreshed")


def _open_metadata_bundle(catalog_service: CatalogService, catalog: VaultCatalog) -> LocalIndexServiceBundle:
    """Stage a copy of the active generation and open metadata and graph writers on it, no vectors."""
    manager = ProjectionGenerationManager(catalog_service.graph_home_path)
    publisher = ProjectionBundlePublisher(catalog_service.graph_home_path, manager)
    staged = publisher.stage_from_active()
    catalog_service.metadata_path = staged.root_path / "metadata" / "metadata.sqlite3"
    catalog_service.vector_path = staged.root_path / "vector" / "chroma"
    catalog_service.graph_path = staged.root_path / "graph" / "graph.sqlite3"
    graph_store = None
    try:
        for target in (
            catalog_service.metadata_path,
            catalog_service.vector_path,
            catalog_service.graph_path,
            document_store_path(catalog_service),
            catalog_service.graph_status_path,
        ):
            catalog_service.assert_graph_home_write_target_safe(target_path=target, catalog=catalog)
        metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=True)
        graph_store = open_graph_store(
            catalog_service,
            metadata_store=metadata_store,
            writable=True,
            backend=selected_graph_backend(catalog_service),
        )
        index_service = IndexService(
            catalog=catalog,
            metadata_store=metadata_store,
            graph_store=graph_store,
            graph_extraction_spec=current_graph_extraction_spec(),
            graph_status_store=LocalGraphStatusStore(catalog_service.graph_status_path),
        )
    except Exception:
        close = getattr(graph_store, "close", None)
        if callable(close):
            close()
        publisher.discard(staged)
        raise
    return LocalIndexServiceBundle(
        catalog_service=catalog_service,
        catalog=catalog,
        index_service=index_service,
        generation_manager=manager,
        bundle_publisher=publisher,
        staged_generation=staged,
    )


def _drop_vectors_of_removed_chunks(catalog_service: CatalogService, scope: QueryScope) -> None:
    """Remove staged vectors whose chunk is gone. Needs no embedding model."""
    if not catalog_service.vector_path.exists():
        return
    from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore

    chunks = {
        (chunk.vault_id, chunk.chunk_id)
        for chunk in SQLiteMetadataStore(catalog_service.metadata_path, initialize=False).list_chunks(scope)
    }
    vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False)
    try:
        removed = tuple(
            VectorTombstone(
                vector_id=row.vector_id,
                vault_id=row.vault_id,
                chunk_id=row.chunk_id,
                embedding_spec=row.embedding_spec,
            )
            for row in vector_store.export_manifest(scope)
            if (row.vault_id, row.chunk_id) not in chunks
        )
        if removed:
            vector_store.apply_vector_revision(
                vector_index_revision=f"vector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                records=(),
                tombstones=removed,
            )
    finally:
        close = getattr(vector_store, "close", None)
        if callable(close):
            close()


def _time_limit(budget_s: float) -> str:
    return f"the {budget_s:g} s time limit was reached."


__all__ = [
    "DEFAULT_REFRESH_BUDGET_S",
    "RecallIndexRefresh",
    "refresh_linked_vaults",
    "refresh_recall_index",
]
