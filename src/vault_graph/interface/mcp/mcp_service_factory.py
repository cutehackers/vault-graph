from __future__ import annotations

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
    from vault_graph.operation.integration.remember_service import RememberService
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


class McpServiceFactory:
    def __init__(self, *, graph_home_path: Path, vault_map_path: Path | None = None) -> None:
        self._graph_home_path = graph_home_path
        self._vault_map_path = vault_map_path
        self._read_only_factory = ReadOnlyServiceFactory(graph_home_path=graph_home_path)

    def open_read_only(self) -> McpServices:
        services = self._read_only_factory.open_read_only()
        return McpServices(
            catalog_service=services.catalog_service,
            catalog=services.catalog,
            metadata_store=services.metadata_store,
            retrieval_service=services.retrieval_service,
            context_pack_builder=services.context_pack_builder,
            context_pack_renderer=services.context_pack_renderer,
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

    def open_remember_service(self) -> RememberService:
        """Open remember with the read-only ``vault-map.json`` and the publish-draft subprocess adapter."""

        from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
        from vault_graph.operation.integration.remember_service import RememberService
        from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path

        opening = open_vault_map(vault_map_path(self._vault_map_path))
        return RememberService(
            vault_map=opening.vault_map,
            publisher=VaultPublishCli(),
            vault_map_problem=None if opening.vault_map else opening.warning or f"no vault-map.json at {opening.path}.",
        )

    def open_project_context_service(self) -> ProjectContextService:
        """Open code projection services only when project exploration is requested."""

        from vault_graph.interface.composition.code_index_factory import CodeIndexFactory

        return CodeIndexFactory(graph_home_path=self._graph_home_path).open_project_context_service()
