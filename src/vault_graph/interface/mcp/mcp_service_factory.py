from __future__ import annotations

import json
import threading
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.vault_catalog import VaultCatalog
from vault_graph.storage.interfaces.metadata_store import MetadataStore

if TYPE_CHECKING:
    from vault_graph.context.answer.answer_service import AnswerService
    from vault_graph.context.memory.decision_memory import DecisionMemoryService
    from vault_graph.context.memory.issue_memory import IssueMemoryService
    from vault_graph.context.memory.memory_candidates import CandidateKind
    from vault_graph.context.memory.memory_source_reader import MemorySourceReader
    from vault_graph.context.memory.project_memory import ProjectMemoryService
    from vault_graph.context.memory.timeline_memory import TimelineMemoryService
    from vault_graph.context.pack.context_pack_builder import ContextPackBuilder
    from vault_graph.context.pack.context_pack_renderer import ContextPackRenderer
    from vault_graph.indexing.index_service import IndexService
    from vault_graph.interface.composition.memory_candidate_sources import MemoryCandidatePackage
    from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService
    from vault_graph.operation.memory.memory_write_service import MemoryWriteService
    from vault_graph.project.context.project_context_service import ProjectContextService
    from vault_graph.retrieval.graph.graph_resource_service import GraphResourceService
    from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService
    from vault_graph.retrieval.search.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.search.retrieval_service import RetrievalService
    from vault_graph.storage.local.reviewed_log import JsonlReviewedLog
    from vault_graph.storage.local.usage_log import JsonlUsageLog


@dataclass(frozen=True)
class McpServices:
    catalog_service: CatalogService
    catalog: VaultCatalog
    metadata_store: MetadataStore
    retrieval_service: RetrievalService
    context_pack_builder: ContextPackBuilder
    context_pack_renderer: ContextPackRenderer
    generation_id: str | None = None
    """The active projection generation when these services were opened. None before the first index."""


class CurrentMcpServices:
    """Read services on the active index generation, shared by MCP tools and resources (발견2, 발견7).

    A hook, ``vg index`` or a background index can publish a new generation while the server runs,
    and old generations are pruned. ``get`` compares the active generation id with the one the
    services were opened on and reopens them when it changed. When the id cannot be read or the
    services cannot be reopened, the current services are kept.
    """

    def __init__(self, *, services: McpServices, service_factory: McpServiceFactory) -> None:
        self._services = services
        self._service_factory = service_factory
        self._lock = threading.Lock()

    def get(self) -> McpServices:
        with self._lock:
            try:
                generation_id = self._service_factory.active_generation_id()
            except Exception:  # noqa: BLE001 - an unreadable manifest must not fail a read.
                return self._services
            if generation_id != self._services.generation_id:
                self._reopen_locked()
            return self._services

    def reopen(self) -> None:
        """Reopen the services now, for example after this process published a generation."""
        with self._lock:
            self._reopen_locked()

    def _reopen_locked(self) -> None:
        try:
            self._services = self._service_factory.open_read_only()
        except Exception:  # noqa: BLE001 - keep serving from the previous services.
            return


IndexRunner = Callable[[Path, str], bool]
"""Index one Vault id in a Graph Home and publish the result. Returns True when the run succeeded."""

# One background index run at a time per process. Index runs stage and publish a whole projection
# generation of the Graph Home, so two runs must not overlap.
_BACKGROUND_INDEX_LOCK = threading.Lock()


class McpServiceFactory:
    def __init__(
        self,
        *,
        graph_home_path: Path,
        vault_map_path: Path | None = None,
        index_runner: IndexRunner | None = None,
    ) -> None:
        self._graph_home_path = graph_home_path
        self._vault_map_path = vault_map_path
        self._index_runner = index_runner or index_one_vault
        self._read_only_factory = ReadOnlyServiceFactory(graph_home_path=graph_home_path)
        self._active_manifest = graph_home_path.expanduser().resolve() / "projections" / "active.json"
        from vault_graph.operation.memory.memory_write_service import InferredProposalBudget

        # One budget per server process: a cleanup runs from one list_memory_candidates call to the next
        # (spec 2026-11-05 §6 "한 정리"), while each write tool call opens a new write service.
        self._proposal_budget = InferredProposalBudget()

    def active_generation_id(self) -> str | None:
        """Read the active generation id from ``projections/active.json``. None when nothing was published.

        One small file read, cheap enough to run before every read tool call. Raises OSError or
        ValueError when the file cannot be read or parsed.
        """

        try:
            text = self._active_manifest.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        generation_id = json.loads(text).get("generation_id")
        return generation_id if isinstance(generation_id, str) and generation_id else None

    def open_read_only(self) -> McpServices:
        # Read the id before opening: if a publish lands in between, the next call sees a newer id and reopens.
        try:
            generation_id = self.active_generation_id()
        except (OSError, ValueError):
            generation_id = None
        services = self._read_only_factory.open_read_only()
        return McpServices(
            catalog_service=services.catalog_service,
            catalog=services.catalog,
            metadata_store=services.metadata_store,
            retrieval_service=services.retrieval_service,
            context_pack_builder=services.context_pack_builder,
            context_pack_renderer=services.context_pack_renderer,
            generation_id=generation_id,
        )

    def open_retrieval_service(self, *, include_graph: bool = False) -> RetrievalService:
        return self._read_only_factory.open_retrieval_service(include_graph=include_graph)

    def open_context_pack_builder(self, *, include_graph: bool = False) -> ContextPackBuilder:
        return self._read_only_factory.open_context_pack_builder(include_graph=include_graph)

    def open_answer_service(self, *, include_graph: bool = False) -> AnswerService:
        return self._read_only_factory.open_answer_service(include_graph=include_graph)

    def open_status_service(self) -> IndexService:
        return self._read_only_factory.open_status_service()

    def open_graph_retrieval_service(self) -> GraphRetrievalService:
        return self._read_only_factory.open_graph_retrieval_service()

    def open_graph_resource_service(self) -> GraphResourceService:
        return self._read_only_factory.open_graph_resource_service()

    def open_graph_search_candidate_provider(self) -> GraphSearchCandidateProvider:
        return self._read_only_factory.open_graph_search_candidate_provider()

    def open_memory_source_reader(self) -> MemorySourceReader:
        return self._read_only_factory.open_memory_source_reader()

    def open_decision_memory_service(self) -> DecisionMemoryService:
        return self._read_only_factory.open_decision_memory_service()

    def open_issue_memory_service(self) -> IssueMemoryService:
        return self._read_only_factory.open_issue_memory_service()

    def open_project_memory_service(self) -> ProjectMemoryService:
        return self._read_only_factory.open_project_memory_service()

    def open_timeline_memory_service(self) -> TimelineMemoryService:
        return self._read_only_factory.open_timeline_memory_service()

    def open_health_explorer_service(self) -> HealthExplorerService:
        return self._read_only_factory.open_health_explorer_service()

    def open_usage_log(self) -> JsonlUsageLog:
        """Open the Graph Home ``usage/`` log. Nothing is created until an event is appended."""

        from vault_graph.operation.scope.graph_home import GraphHomeResolver
        from vault_graph.storage.local.usage_log import JsonlUsageLog

        return JsonlUsageLog(GraphHomeResolver().resolve(self._graph_home_path).root_path)

    def open_reviewed_log(self) -> JsonlReviewedLog:
        """Open the Graph Home ``memory/reviewed.jsonl`` cleanup record. Nothing is created until a record is added."""

        from vault_graph.operation.scope.graph_home import GraphHomeResolver
        from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

        return JsonlReviewedLog(GraphHomeResolver().resolve(self._graph_home_path).root_path)

    def memory_candidate_package(
        self, cwd: Path, *, kinds: Collection[CandidateKind] | None = None, limit: int | None = None
    ) -> MemoryCandidatePackage:
        """The cleanup bundle of the ``cwd`` map project (spec 2026-11-05 §4.4.4). Reads only."""

        from vault_graph.interface.composition.memory_candidate_sources import memory_candidate_package

        return memory_candidate_package(
            self._graph_home_path, cwd, kinds=kinds, limit=limit, vault_map_file=self._vault_map_path
        )

    def start_curation(self) -> None:
        """Start a new cleanup: the inferred proposal count of this server process goes back to zero."""
        self._proposal_budget.start_curation()

    def open_memory_write_service(self) -> MemoryWriteService:
        """Open memory writes with the read-only ``vault-map.json``, the page reader, the temporary draft
        files, the publish-draft and import-source adapters, the Graph Home review log, the shared
        inferred proposal budget and the index lookup of similar existing pages."""

        from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
        from vault_graph.interface.composition.adapters.vault_import_cli import VaultImportCli
        from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
        from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
        from vault_graph.interface.composition.memory_candidate_sources import ProjectSimilarPages
        from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
        from vault_graph.operation.memory.memory_write_service import MemoryWriteService

        opening = open_vault_map(vault_map_path(self._vault_map_path))
        return MemoryWriteService(
            vault_map=opening.vault_map,
            writer=VaultPublishCli(),
            page_reader=VaultPageFileReader(),
            drafts=TemporaryDraftFiles(),
            vault_map_problem=None if opening.vault_map else opening.warning or f"no vault-map.json at {opening.path}.",
            importer=VaultImportCli(),
            reviewed_log=self.open_reviewed_log(),
            proposal_budget=self._proposal_budget,
            similar_pages=ProjectSimilarPages(graph_home=self._graph_home_path, vault_map_file=self._vault_map_path),
        )

    def start_background_index(self, vault_name: str, *, on_finished: Callable[[bool], None]) -> str | None:
        """Start an incremental index of one ``vault-map.json`` Vault in a daemon thread (finding F1).

        Returns the Graph Home Vault id being indexed, or None when the name is not in the map or its
        folder is not a registered, enabled Vault. Nothing is written to the Vault. ``on_finished``
        receives True after the run published a new index, False after any failure.
        """

        from vault_graph.interface.composition.query_scope_resolution import registered_vault_ids
        from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path

        vault_map = open_vault_map(vault_map_path(self._vault_map_path)).vault_map
        if vault_map is None:
            return None
        mapped = next((vault for vault in vault_map.vaults if vault.name == vault_name), None)
        if mapped is None:
            return None
        catalog = CatalogService(graph_home_path=self._graph_home_path).load_catalog()
        vault_ids, _ = registered_vault_ids((mapped,), catalog)
        if not vault_ids or not catalog.resolve(vault_ids[0]).enabled:
            return None
        vault_id = vault_ids[0]
        runner = self._index_runner
        graph_home_path = self._graph_home_path

        def run() -> None:
            try:
                with _BACKGROUND_INDEX_LOCK:
                    succeeded = runner(graph_home_path, vault_id)
            except Exception:  # noqa: BLE001 - a failed background run only means the page waits for vg index.
                succeeded = False
            try:
                on_finished(succeeded)
            except Exception:  # noqa: BLE001 - the callback must not end the server thread with a traceback.
                pass

        threading.Thread(target=run, name=f"vault-graph-index-{vault_id}", daemon=True).start()
        return vault_id

    def open_project_context_service(self) -> ProjectContextService:
        """Open code projection services only when project exploration is requested."""

        from vault_graph.interface.composition.code_index_factory import CodeIndexFactory

        return CodeIndexFactory(graph_home_path=self._graph_home_path).open_project_context_service()


def index_one_vault(graph_home_path: Path, vault_id: str) -> bool:
    """Run what ``vg index --vault-id <vault_id>`` runs: an incremental index, published only on success."""

    from vault_graph.interface.composition.local_index_service_factory import LocalIndexServiceFactory

    scope = CatalogService(graph_home_path=graph_home_path).load_catalog().scope_for_vault_ids([vault_id])
    bundle = LocalIndexServiceFactory().open(
        graph_home_path=graph_home_path,
        initialize_store=True,
        transactional=True,
        full=False,
        requested_scope=scope,
    )
    try:
        report = bundle.index_service.run_apply(scope=scope, full=False)
        # A vector plan failure still publishes metadata and graph (spec 2026-11-05 §4.3.1).
        if not report.publishable:
            return False
        bundle.commit_projection(report)
        return report.exit_code == 0
    finally:
        bundle.close()
