"""Refresh the metadata projection of the linked Vaults before session start recall (F1).

A page saved in one session, accepted from review or captured from a transcript must show in the
next session's recall without the user running ``vg index``. ``vg hook session-start`` therefore
re-reads the linked, already indexed Vaults and publishes a new projection generation when a file
changed. The run uses the same metadata indexer, graph indexer and generation publisher as
``vg index``, with these differences:

- Only the changed files. The scan lists changed and deleted files, and only those are read and
  written to metadata (``IndexService.run_apply_paths``). The graph is still reconciled for the
  whole Vault, because publication needs current graph evidence.
- No embeddings. New and changed chunks keep no vector or an old one until the next ``vg index``,
  which search readiness reports as stale vectors. Vectors of chunks removed from the changed files
  are dropped so the published generation passes the same hygiene check as ``vg index``.
- Right after the scan, ``on_scanned`` receives the Vaults that need ``vg index`` (changed, or
  unknown because the scan stopped) and the other linked Vaults, which need it only when
  ``vectors_need_catch_up`` says so. The hook starts the background catch-up from there.
- A time limit. A quick scan compares each file's SHA-256 with the index and checks the limit after
  every file. The limit is checked again before staging and before publishing. A run past the
  limit publishes nothing and recall reads the current index. When another run holds the projection
  lock for more than ``MAX_LOCK_WAIT_S`` seconds, the refresh is skipped the same way. One step after the scan is never
  interrupted, so the scan also stops when more than ``MAX_QUICK_REFRESH_FILES`` files changed.
- A cost check before staging. The graph rebuild and the publication read the whole Vault, so their
  time grows with the indexed document count, not with the changed files. The refresh is skipped
  when the linked Vaults hold more than ``MAX_QUICK_REFRESH_DOCUMENTS`` indexed documents, or when
  the last quick refresh of the same Vaults, scaled to today's document count, took longer than the
  time left. Each quick refresh that staged a generation writes its duration to
  ``logs/quick-refresh-times.json`` in the Graph Home. A record older than
  ``QUICK_REFRESH_RECORD_MAX_AGE`` is ignored, so one slow run does not turn the refresh off for good.
- Nothing changed means nothing is written. Vault files are never written.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Literal

from vault_graph.context.pack.recall import RecallPorts
from vault_graph.indexing.index_service import IndexService
from vault_graph.indexing.publication.projection_generation import (
    ProjectionBundlePublisher,
    ProjectionGenerationManager,
    ProjectionPublishBusyError,
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
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorTombstone
from vault_graph.storage.local.graph_status_store import LocalGraphStatusStore
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

DEFAULT_REFRESH_BUDGET_S = 5.0
# More changed files than this are left to the background `vg index`. p12 measured a whole hook run
# with 500 new files at 1.4 s, so 200 keeps the quick refresh well inside the budget.
MAX_QUICK_REFRESH_FILES = 200
# Longest wait for the projection lock. A `vg index` holding it may run for minutes, and the
# background `vg index` started after the scan brings the changes in anyway.
MAX_LOCK_WAIT_S = 1.0
# More indexed documents than this are left to the background `vg index`. A refresh of one new file
# costs about 1.7 ms per indexed document (graph rebuild, publication and scan read the whole Vault).
# p30 measured 1,475 documents: refresh 2.5 s, whole hook through the launcher 3.1 s, inside the 5 s
# target. At 3,000 documents the graph rebuild alone took 4.3 s.
MAX_QUICK_REFRESH_DOCUMENTS = 1500
QUICK_REFRESH_TIMES = Path("logs") / "quick-refresh-times.json"
QUICK_REFRESH_RECORD_MAX_AGE = timedelta(days=1)

RefreshStatus = Literal["unchanged", "refreshed", "skipped", "failed"]
# Called once after the change scan with (Vaults to index, Vaults to check for stale vectors).
ScanCallback = Callable[[tuple[str, ...], tuple[str, ...]], None]


@dataclass(frozen=True)
class RecallIndexRefresh:
    status: RefreshStatus
    vault_ids: tuple[str, ...] = ()
    changed: int = 0
    deleted: int = 0
    reason: str | None = None
    catch_up_vault_ids: tuple[str, ...] = ()

    @property
    def warning(self) -> str | None:
        """One line for stderr when the index was not brought up to date."""
        if self.status in ("unchanged", "refreshed") or self.reason is None:
            return None
        return " ".join(f"Index refresh {self.status}: {self.reason} Recall uses the existing index.".split())


def refresh_linked_vaults(
    cwd: Path,
    *,
    ports: RecallPorts,
    graph_home_path: Path,
    budget_s: float,
    on_scanned: ScanCallback | None = None,
) -> RecallIndexRefresh:
    """Refresh the indexed Vaults linked to ``cwd``. Never raises: a failure becomes a warning."""
    if budget_s <= 0:
        return RecallIndexRefresh(status="skipped")
    try:
        scope = ports.scope.resolve(cwd)
        vault_ids = tuple(vault_id for vault_id in scope.vault_ids if ports.documents.is_indexed(vault_id))
        if not vault_ids:
            return RecallIndexRefresh(status="skipped")
        return refresh_recall_index(
            graph_home_path=graph_home_path, vault_ids=vault_ids, budget_s=budget_s, on_scanned=on_scanned
        )
    except Exception as exc:  # noqa: BLE001 - the hook must print recall whatever the refresh did
        return RecallIndexRefresh(status="failed", reason=f"{type(exc).__name__}: {exc}.")


def refresh_recall_index(
    *,
    graph_home_path: Path,
    vault_ids: tuple[str, ...],
    budget_s: float,
    on_scanned: ScanCallback | None = None,
) -> RecallIndexRefresh:
    started = monotonic()
    deadline = started + budget_s
    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog = catalog_service.load_catalog()
    scope = catalog.scope_for_vault_ids(vault_ids)
    if active_projection_layout(catalog_service.graph_home_path) is None:
        return RecallIndexRefresh(
            status="skipped", vault_ids=vault_ids, reason="the index was not published by `vg index`."
        )
    scan = _scan_changes(catalog, catalog_service.metadata_path, vault_ids, deadline=deadline)
    if scan is None:
        # The scan did not finish, so any linked Vault may have changed.
        if on_scanned is not None:
            on_scanned(vault_ids, ())
        return RecallIndexRefresh(
            status="skipped", vault_ids=vault_ids, reason=_time_limit(budget_s), catch_up_vault_ids=vault_ids
        )
    changes, documents = scan
    changed = sum(len(paths) for paths, _ in changes.values())
    deleted = sum(len(paths) for _, paths in changes.values())
    changed_vault_ids = tuple(vault_id for vault_id in vault_ids if any(changes[vault_id]))
    if on_scanned is not None:
        on_scanned(changed_vault_ids, tuple(vault_id for vault_id in vault_ids if vault_id not in changed_vault_ids))
    if not changed_vault_ids:
        return RecallIndexRefresh(status="unchanged", vault_ids=vault_ids)

    def outcome(status: RefreshStatus, reason: str | None = None) -> RecallIndexRefresh:
        return RecallIndexRefresh(
            status=status,
            vault_ids=vault_ids,
            changed=changed,
            deleted=deleted,
            reason=reason,
            catch_up_vault_ids=changed_vault_ids,
        )

    if changed + deleted > MAX_QUICK_REFRESH_FILES:
        return outcome(
            "skipped",
            f"{changed + deleted} changed files are more than the {MAX_QUICK_REFRESH_FILES} a session start "
            "indexes. `vg index` runs in the background.",
        )
    if monotonic() > deadline:
        return outcome("skipped", _time_limit(budget_s))
    if documents > MAX_QUICK_REFRESH_DOCUMENTS:
        return outcome(
            "skipped",
            f"{documents} indexed documents are more than the {MAX_QUICK_REFRESH_DOCUMENTS} a session start "
            "refreshes. `vg index` runs in the background.",
        )
    times_path = catalog_service.graph_home_path / QUICK_REFRESH_TIMES
    last = _last_quick_refresh(times_path, vault_ids)
    if last is not None:
        last_seconds, last_documents = last
        estimate = last_seconds * max(documents, 1) / max(last_documents, 1)
        if estimate > deadline - monotonic():
            return outcome(
                "skipped",
                f"the last quick refresh took {last_seconds:.1f} s, more than the time left. "
                "`vg index` runs in the background.",
            )

    try:
        bundle = _open_metadata_bundle(
            catalog_service, catalog, lock_timeout=max(0.0, min(MAX_LOCK_WAIT_S, deadline - monotonic()))
        )
    except ProjectionPublishBusyError as exc:
        return outcome("skipped", f"{exc}.")
    changed_paths = tuple((vault_id, path) for vault_id in vault_ids for path in sorted(changes[vault_id][0]))
    deleted_paths = tuple((vault_id, path) for vault_id in vault_ids for path in sorted(changes[vault_id][1]))
    try:
        staged_metadata = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
        chunks_before = _chunk_keys(staged_metadata, changed_paths + deleted_paths)
        report = bundle.index_service.run_apply_paths(
            scope=scope, changed_paths=changed_paths, deleted_paths=deleted_paths
        )
        if report.exit_code:
            error = getattr(report.graph, "error", None) or "graph index failed."
            return outcome("failed", str(error))
        removed = chunks_before - _chunk_keys(staged_metadata, changed_paths + deleted_paths)
        _drop_vectors_of_removed_chunks(catalog_service, scope, removed)
        if monotonic() > deadline:
            _record_quick_refresh(times_path, vault_ids, seconds=monotonic() - started, documents=documents)
            return outcome("skipped", _time_limit(budget_s))
        bundle.commit_projection(report)
    finally:
        bundle.close()
    _record_quick_refresh(times_path, vault_ids, seconds=monotonic() - started, documents=documents)
    return outcome("refreshed")


def _scan_changes(
    catalog: VaultCatalog, metadata_path: Path, vault_ids: tuple[str, ...], *, deadline: float
) -> tuple[dict[str, tuple[set[str], set[str]]], int] | None:
    """Changed and deleted paths per Vault, by SHA-256 of the file bytes, and the indexed document
    count. None when time ran out.

    Reads the same ``*.md`` files as ``VaultLoader`` but does not parse or chunk them, so the time
    limit can be checked after every file. A change ``vg index`` alone sees (a new parser version)
    is left to ``vg index``.
    """
    states = SQLiteMetadataStore(metadata_path, initialize=False).list_document_states(vault_ids)
    changes: dict[str, tuple[set[str], set[str]]] = {}
    documents = 0
    for vault_id in vault_ids:
        entry = catalog.resolve(vault_id)
        known = {
            state.path: state
            for state in states
            if state.vault_id == vault_id and _in_scopes(state.path, entry.content_scopes)
        }
        seen: set[str] = set()
        changed: set[str] = set()
        for content_scope in entry.content_scopes:
            scope_root = entry.root_path / content_scope
            if not scope_root.exists():
                continue
            for markdown_path in scope_root.rglob("*.md"):
                if monotonic() > deadline:
                    return None
                if markdown_path.is_symlink() or not markdown_path.is_file():
                    continue
                relative = markdown_path.relative_to(entry.root_path).as_posix()
                if relative in seen:
                    continue
                seen.add(relative)
                state = known.get(relative)
                digest = hashlib.sha256(markdown_path.read_bytes()).hexdigest()
                if state is None or state.is_tombstoned or state.raw_sha256 != digest:
                    changed.add(relative)
        deleted = {path for path, state in known.items() if path not in seen and not state.is_tombstoned}
        changes[vault_id] = (changed, deleted)
        documents += sum(1 for state in known.values() if not state.is_tombstoned)
    return changes, documents


def _quick_refresh_key(vault_ids: tuple[str, ...]) -> str:
    return ",".join(sorted(vault_ids))


def _read_quick_refresh_times(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _last_quick_refresh(path: Path, vault_ids: tuple[str, ...]) -> tuple[float, int] | None:
    """(seconds, documents) of the last quick refresh of these Vaults, if recorded recently."""
    record = _read_quick_refresh_times(path).get(_quick_refresh_key(vault_ids))
    if not isinstance(record, dict):
        return None
    try:
        seconds = float(record["seconds"])
        documents = int(record["documents"])
        recorded_at = datetime.fromisoformat(str(record["recorded_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if recorded_at.tzinfo is None or datetime.now(UTC) - recorded_at > QUICK_REFRESH_RECORD_MAX_AGE:
        return None
    return seconds, documents


def _record_quick_refresh(path: Path, vault_ids: tuple[str, ...], *, seconds: float, documents: int) -> None:
    """Write the duration of a quick refresh. A write that fails only loses the estimate."""
    times = _read_quick_refresh_times(path)
    times[_quick_refresh_key(vault_ids)] = {
        "seconds": round(seconds, 3),
        "documents": documents,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(times, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)


def _in_scopes(path: str, content_scopes: tuple[str, ...]) -> bool:
    return any(path == scope or path.startswith(f"{scope}/") for scope in content_scopes)


def _open_metadata_bundle(
    catalog_service: CatalogService, catalog: VaultCatalog, *, lock_timeout: float
) -> LocalIndexServiceBundle:
    """Stage a copy of the active generation and open metadata and graph writers on it, no vectors.

    Raises ``ProjectionPublishBusyError`` when another run holds the projection lock past ``lock_timeout``.
    """
    manager = ProjectionGenerationManager(catalog_service.graph_home_path)
    publisher = ProjectionBundlePublisher(catalog_service.graph_home_path, manager)
    staged = publisher.stage_from_active(lock_timeout=lock_timeout)
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


def _chunk_keys(metadata_store: SQLiteMetadataStore, paths: tuple[tuple[str, str], ...]) -> set[tuple[str, str]]:
    """(vault_id, chunk_id) of the listed files' current chunks."""
    keys: set[tuple[str, str]] = set()
    for vault_id, path in paths:
        state = metadata_store.document_state(vault_id, path)
        if state.document_id is None or state.is_tombstoned:
            continue
        chunks = metadata_store.list_document_chunks(vault_id=vault_id, document_id=state.document_id)
        keys.update((chunk.vault_id, chunk.chunk_id) for chunk in chunks)
    return keys


def _drop_vectors_of_removed_chunks(
    catalog_service: CatalogService, scope: QueryScope, removed: set[tuple[str, str]]
) -> None:
    """Remove staged vectors of chunks the changed files no longer have. Needs no embedding model.

    The active generation passed the hygiene check, so vectors without a chunk can only come from
    the changed files. A new file removes nothing and the vector store is not opened.
    """
    if not removed or not catalog_service.vector_path.exists():
        return
    from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore

    vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False)
    try:
        tombstones = tuple(
            VectorTombstone(
                vector_id=row.vector_id,
                vault_id=row.vault_id,
                chunk_id=row.chunk_id,
                embedding_spec=row.embedding_spec,
            )
            for row in vector_store.export_manifest(scope)
            if (row.vault_id, row.chunk_id) in removed
        )
        if tombstones:
            vector_store.apply_vector_revision(
                vector_index_revision=f"vector-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}",
                records=(),
                tombstones=tombstones,
            )
    finally:
        close = getattr(vector_store, "close", None)
        if callable(close):
            close()


def vectors_need_catch_up(graph_home_path: Path, vault_id: str) -> bool:
    """True when the active index has chunks of the Vault without a current vector, or stray vectors.

    Used by the background catch-up so a ``vg index`` that was killed is run again. It reads the
    whole Vault's chunks and vectors (about 2 s for 10,000 files), so it never runs in the hook.
    An unknown Vault, a Graph Home without a published index, or a vector store whose health check
    fails returns False, so a problem ``vg index`` cannot fix does not start it at every session.
    """
    from vault_graph.interface.composition.read_only_service_factory import VectorIndexerStaleCounter
    from vault_graph.operation.scope.catalog_query_scopes import actual_query_scopes
    from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore

    catalog_service = CatalogService(graph_home_path=graph_home_path)
    catalog = catalog_service.load_catalog()
    if active_projection_layout(catalog_service.graph_home_path) is None:
        return False
    try:
        scope = catalog.scope_for_vault_ids((vault_id,))
    except Exception:  # noqa: BLE001 - an unknown or disabled Vault has nothing to catch up
        return False
    if not catalog_service.vector_path.exists():
        return True
    metadata_store = SQLiteMetadataStore(catalog_service.metadata_path, initialize=False)
    vector_store = ChromaVectorStore(catalog_service.vector_path, initialize=False, read_only=True)
    try:
        health = vector_store.health()
        if not health.ok or not health.schema_compatible:
            return False
        counter = VectorIndexerStaleCounter(
            metadata_store=metadata_store,
            vector_store=vector_store,
            text_embeddings=_catch_up_text_embeddings(catalog_service),
        )
        return any(
            (counter.stale_count(scope=actual) or 0) > 0 for actual in actual_query_scopes(catalog=catalog, scope=scope)
        )
    finally:
        close = getattr(vector_store, "close", None)
        if callable(close):
            close()


def _catch_up_text_embeddings(catalog_service: CatalogService) -> TextEmbeddings:
    """The embedding model spec ``vg index`` uses. Only its spec is read, nothing is downloaded."""
    from vault_graph.interface.composition.adapters.text_embeddings import (
        FastEmbedTextEmbeddings,
        FastEmbedTextEmbeddingsConfig,
    )

    return FastEmbedTextEmbeddings(
        config=FastEmbedTextEmbeddingsConfig(cache_dir=catalog_service.embedding_cache_path, local_files_only=True)
    )


def _time_limit(budget_s: float) -> str:
    return f"the {budget_s:g} s time limit was reached."


__all__ = [
    "DEFAULT_REFRESH_BUDGET_S",
    "MAX_QUICK_REFRESH_DOCUMENTS",
    "MAX_QUICK_REFRESH_FILES",
    "RecallIndexRefresh",
    "ScanCallback",
    "refresh_linked_vaults",
    "refresh_recall_index",
    "vectors_need_catch_up",
]
