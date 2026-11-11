"""Refresh the metadata projection of the linked Vaults before session start recall (F1).

A page saved in one session, accepted from review or captured from a transcript must show in the
next session's recall without the user running ``vg index``. ``vg hook session-start`` therefore
re-reads the linked, already indexed Vaults and publishes a new projection generation when a file
changed. The run uses the same metadata indexer, graph indexer and generation publisher as
``vg index``, with these differences:

- Only the changed files. The scan (``indexing.change_scan``) lists changed and deleted files, and
  only those are read and written to metadata (``IndexService.run_apply_paths``). The graph is
  still reconciled for the whole Vault, because publication needs current graph evidence.
- No embeddings. New and changed chunks keep no vector or an old one until the next ``vg index``,
  which search readiness reports as stale vectors. ``IndexService.run_apply_paths`` drops vectors of
  chunks removed from the changed files so the published generation passes the same hygiene check
  as ``vg index``. This module only opens the stores; it reads and writes none of them itself.
- Right after the scan, ``on_scanned`` receives the Vaults that need ``vg index`` (changed, or
  unknown because the scan stopped), the other linked Vaults, which need it only when
  ``vectors_need_catch_up`` says so. The hook starts the background catch-up from there. Vaults
  without an index are never refreshed. When none of the linked Vaults has an index, as at the first
  session start after install, there is no scan and ``on_scanned`` receives them as the third
  argument, so the catch-up builds their first index (spec 2026-11-11 §4.4.2). When some linked
  Vaults have an index, the others stay unindexed until ``vg index`` (spec 2026-11-05 A-7).
- A time limit. The scan compares each file's SHA-256 with the index and checks the limit after
  every file. The limit is checked again before staging and before publishing. A run past the
  limit publishes nothing and recall reads the current index. When another run holds the projection
  lock for more than ``MAX_LOCK_WAIT_S`` seconds, the refresh is skipped the same way. One step after the scan is never
  interrupted, so the scan also stops when more than ``MAX_QUICK_REFRESH_FILES`` files changed.
- A cost check before staging. The graph rebuild and the publication read the whole Vault, so their
  time grows with the indexed document count, not with the changed files. The refresh is skipped
  when the linked Vaults hold more than ``MAX_QUICK_REFRESH_DOCUMENTS`` indexed documents, or when
  each of the last ``SLOW_RUNS_TO_SKIP`` quick refreshes of the same Vaults, scaled to today's
  document count, took longer than the time left. Each quick refresh that staged a generation adds
  its duration to ``logs/quick-refresh-times.json`` in the Graph Home, which keeps the last
  ``SLOW_RUNS_TO_SKIP`` runs per Vault set. One slow run, such as the first one after ``vg setup``,
  does not skip the next (2026-11-03 발견12). A run older than ``QUICK_REFRESH_RECORD_MAX_AGE`` is
  ignored, so slow runs do not turn the refresh off for good.
- Nothing changed means nothing is written. Vault files are never written.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import Literal

from vault_graph.context.pack.recall import RecallPorts
from vault_graph.errors import TextEmbeddingsError
from vault_graph.indexing.change_scan import scan_changes
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
from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.retrieval.graph.graph_contracts import current_graph_extraction_spec
from vault_graph.storage.interfaces.text_embeddings import TextEmbeddings
from vault_graph.storage.interfaces.vector_store import VectorStore
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
# Slow runs in a row that skip the next quick refresh. One slow run can be a cold start.
SLOW_RUNS_TO_SKIP = 2

RefreshStatus = Literal["unchanged", "refreshed", "skipped", "failed"]
# Called once after the change scan with (Vaults to index, Vaults to check for stale vectors,
# Vaults without any index, which get a keyword index before their vectors).
ScanCallback = Callable[[tuple[str, ...], tuple[str, ...], tuple[str, ...]], None]


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
            if scope.vault_ids and on_scanned is not None:
                # No linked Vault has an index yet: the catch-up builds a keyword index first.
                on_scanned((), (), tuple(scope.vault_ids))
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
    scan = scan_changes(
        catalog, SQLiteMetadataStore(catalog_service.metadata_path, initialize=False), vault_ids, deadline=deadline
    )
    if scan is None:
        # The scan did not finish, so any linked Vault may have changed.
        if on_scanned is not None:
            on_scanned(vault_ids, (), ())
        return RecallIndexRefresh(
            status="skipped", vault_ids=vault_ids, reason=_time_limit(budget_s), catch_up_vault_ids=vault_ids
        )
    changes, documents = scan.changes, scan.documents
    changed = sum(len(paths) for paths, _ in changes.values())
    deleted = sum(len(paths) for _, paths in changes.values())
    changed_vault_ids = tuple(vault_id for vault_id in vault_ids if any(changes[vault_id]))
    if on_scanned is not None:
        on_scanned(
            changed_vault_ids, tuple(vault_id for vault_id in vault_ids if vault_id not in changed_vault_ids), ()
        )
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
    recent = _recent_quick_refreshes(times_path, vault_ids)
    time_left = deadline - monotonic()
    if len(recent) >= SLOW_RUNS_TO_SKIP and all(
        seconds * max(documents, 1) / max(run_documents, 1) > time_left for seconds, run_documents in recent
    ):
        took = ", ".join(f"{seconds:.1f} s" for seconds, _ in recent)
        return outcome(
            "skipped",
            f"the last two quick refreshes took {took}, more than the time left. `vg index` runs in the background.",
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
        report = bundle.index_service.run_apply_paths(
            scope=scope,
            changed_paths=changed_paths,
            deleted_paths=deleted_paths,
            open_vector_store=lambda: _open_staged_vector_store(catalog_service),
        )
        if report.exit_code:
            error = getattr(report.graph, "error", None) or "graph index failed."
            return outcome("failed", str(error))
        if monotonic() > deadline:
            _record_quick_refresh(times_path, vault_ids, seconds=monotonic() - started, documents=documents)
            return outcome("skipped", _time_limit(budget_s))
        bundle.commit_projection(report)
    finally:
        bundle.close()
    _record_quick_refresh(times_path, vault_ids, seconds=monotonic() - started, documents=documents)
    return outcome("refreshed")


def _quick_refresh_key(vault_ids: tuple[str, ...]) -> str:
    return ",".join(sorted(vault_ids))


def _read_quick_refresh_times(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _recent_quick_refreshes(path: Path, vault_ids: tuple[str, ...]) -> list[tuple[float, int]]:
    """(seconds, documents) of the recent quick refreshes of these Vaults, oldest first.

    A record written before 발견12 holds one run without ``runs`` and counts as that one run.
    """
    record = _read_quick_refresh_times(path).get(_quick_refresh_key(vault_ids))
    if not isinstance(record, dict):
        return []
    runs = record.get("runs", [record])
    recent: list[tuple[float, int]] = []
    for run in runs if isinstance(runs, list) else []:
        parsed = _parse_run(run)
        if parsed is not None:
            recent.append(parsed)
    return recent[-SLOW_RUNS_TO_SKIP:]


def _parse_run(run: object) -> tuple[float, int] | None:
    if not isinstance(run, dict):
        return None
    try:
        seconds = float(run["seconds"])
        documents = int(run["documents"])
        recorded_at = datetime.fromisoformat(str(run["recorded_at"]))
    except (KeyError, TypeError, ValueError):
        return None
    if recorded_at.tzinfo is None or datetime.now(UTC) - recorded_at > QUICK_REFRESH_RECORD_MAX_AGE:
        return None
    return seconds, documents


def _record_quick_refresh(path: Path, vault_ids: tuple[str, ...], *, seconds: float, documents: int) -> None:
    """Add the duration of a quick refresh, keeping the last runs. A write that fails only loses the estimate."""
    times = _read_quick_refresh_times(path)
    key = _quick_refresh_key(vault_ids)
    previous = times.get(key)
    runs = previous.get("runs", [previous]) if isinstance(previous, dict) else []
    run = {"seconds": round(seconds, 3), "documents": documents, "recorded_at": datetime.now(UTC).isoformat()}
    kept = [item for item in (runs if isinstance(runs, list) else []) if _parse_run(item) is not None]
    times[key] = {"runs": [*kept, run][-SLOW_RUNS_TO_SKIP:]}
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(times, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        temporary.unlink(missing_ok=True)


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


def _open_staged_vector_store(catalog_service: CatalogService) -> VectorStore | None:
    """The staged generation's vector store, opened without an embedding model. None when it has none."""
    if not catalog_service.vector_path.exists():
        return None
    from vault_graph.interface.composition.local_index_service_factory import manifest_tracked
    from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore

    # Drops go through the manifest table too, so the next `vg index` does not rebuild it.
    return manifest_tracked(
        ChromaVectorStore(catalog_service.vector_path, initialize=False), catalog_service.vector_path
    )


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
        try:
            text_embeddings = _catch_up_text_embeddings(catalog_service)
        except TextEmbeddingsError as exc:
            # The catch-up process sends stderr to <graph home>/logs/session-start-index.log.
            print(f"vector catch-up skipped: {exc}", file=sys.stderr)
            return False
        counter = VectorIndexerStaleCounter(
            metadata_store=metadata_store,
            vector_store=vector_store,
            text_embeddings=text_embeddings,
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
    from vault_graph.interface.composition.adapters.text_embeddings import text_embeddings_for

    return text_embeddings_for(catalog_service, local_files_only=True)


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
