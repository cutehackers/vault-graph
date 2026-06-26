from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory, ReadOnlyServices

if TYPE_CHECKING:
    from vault_graph.app.answer_service import AnswerService
    from vault_graph.app.graph_retrieval_service import GraphRetrievalService
    from vault_graph.app.index_service import IndexService
    from vault_graph.context.context_pack_builder import ContextPackBuilder
    from vault_graph.memory.issue_memory import IssueMemoryService
    from vault_graph.memory.project_memory import ProjectMemoryService
    from vault_graph.memory.timeline_memory import TimelineMemoryService
    from vault_graph.retrieval.retrieval_service import RetrievalService


class HttpServiceFactory:
    def __init__(self, *, state_path: Path, read_only_factory: ReadOnlyServiceFactory | None = None) -> None:
        self._read_only_factory = read_only_factory or ReadOnlyServiceFactory(state_path=state_path)

    def open_read_only(self) -> ReadOnlyServices:
        return self._read_only_factory.open_read_only()

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

    def open_project_memory_service(self) -> ProjectMemoryService:
        return self._read_only_factory.open_project_memory_service()

    def open_issue_memory_service(self) -> IssueMemoryService:
        return self._read_only_factory.open_issue_memory_service()

    def open_timeline_memory_service(self) -> TimelineMemoryService:
        return self._read_only_factory.open_timeline_memory_service()
