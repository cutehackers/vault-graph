from __future__ import annotations

import json
import threading
from collections.abc import Callable
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
    from vault_graph.context.memory.memory_source_reader import MemorySourceReader
    from vault_graph.context.memory.project_memory import ProjectMemoryService
    from vault_graph.context.memory.timeline_memory import TimelineMemoryService
    from vault_graph.context.pack.context_pack_builder import ContextPackBuilder
    from vault_graph.context.pack.context_pack_renderer import ContextPackRenderer
    from vault_graph.indexing.index_service import IndexService
    from vault_graph.operation.diagnostics.health_explorer import HealthExplorerService
    from vault_graph.operation.memory.memory_write_service import MemoryWriteService
    from vault_graph.project.context.project_context_service import ProjectContextService
    from vault_graph.retrieval.graph.graph_resource_service import GraphResourceService
    from vault_graph.retrieval.graph.graph_retrieval_service import GraphRetrievalService
    from vault_graph.retrieval.search.graph_candidates import GraphSearchCandidateProvider
    from vault_graph.retrieval.search.retrieval_service import RetrievalService
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

    def open_memory_write_service(self) -> MemoryWriteService:
        """Open memory writes with the read-only ``vault-map.json``, the page reader and the publish-draft adapter."""

        from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
        from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
        from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
        from vault_graph.operation.memory.memory_write_service import MemoryWriteService

        opening = open_vault_map(vault_map_path(self._vault_map_path))
        return MemoryWriteService(
            vault_map=opening.vault_map,
            writer=VaultPublishCli(),
            page_reader=VaultPageFileReader(),
            vault_map_problem=None if opening.vault_map else opening.warning or f"no vault-map.json at {opening.path}.",
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
        if report.exit_code != 0:
            return False
        bundle.commit_projection(report)
        return True
    finally:
        bundle.close()
