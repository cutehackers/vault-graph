from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_context_pack_contract import make_pack
from tests.test_graph_retrieval_contract import make_metadata_evidence_from_graph_ref
from tests.test_graph_store_contract import make_entity, make_relationship
from tests.test_mcp_memory_tools import make_open_questions_projection, make_project_projection
from tests.test_mcp_tool_serialization import make_search_response
from vault_graph.app.index_service import StatusReport
from vault_graph.context import ContextPack, ContextPackRequest, DefaultContextPackRenderer
from vault_graph.errors import MemoryProjectionError
from vault_graph.graph.graph_readiness import GraphReadiness
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_service_factory import McpServices
from vault_graph.mcp.mcp_tools import (
    BuildContextPackInput,
    CheckIndexStatusInput,
    DecisionTraceInput,
    FindRelatedInput,
    GetOpenQuestionsInput,
    McpToolRegistry,
    SearchVaultInput,
    SummarizeProjectMemoryInput,
    register_mcp_tools,
)
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    DecisionTraceStep,
    RelatedItem,
    RelatedResponse,
)
from vault_graph.retrieval.search_response import SearchResponse


class RecordingToolServer:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., object]] = {}
        self.structured_output: dict[str, bool | None] = {}

    def tool(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: object | None = None,
        icons: list[object] | None = None,
        meta: dict[str, object] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        del title, description, annotations, icons, meta

        def decorator(func: Callable[..., object]) -> Callable[..., object]:
            assert name is not None
            self.tools[name] = func
            self.structured_output[name] = structured_output
            return func

        return decorator


class RecordingRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> SearchResponse:
        self.calls.append(kwargs)
        return self.response


class RecordingContextPackBuilder:
    def __init__(self, pack: ContextPack) -> None:
        self.pack = pack
        self.requests: list[ContextPackRequest] = []

    def build(self, request: ContextPackRequest) -> ContextPack:
        self.requests.append(request)
        return self.pack


class RecordingStatusService:
    def __init__(self, report: StatusReport) -> None:
        self.report = report
        self.calls: list[QueryScope | None] = []

    def status(self, *, scope: QueryScope | None = None) -> StatusReport:
        self.calls.append(scope)
        return self.report


class RecordingGraphRetrievalService:
    def __init__(
        self,
        *,
        related_response: RelatedResponse | None = None,
        decision_trace_response: DecisionTraceResponse | None = None,
    ) -> None:
        self.related_response = related_response or make_related_response()
        self.decision_trace_response = decision_trace_response or make_decision_trace_response()
        self.related_calls: list[dict[str, object]] = []
        self.decision_trace_calls: list[dict[str, object]] = []

    def related(self, **kwargs: object) -> RelatedResponse:
        self.related_calls.append(kwargs)
        return self.related_response

    def decision_trace(self, **kwargs: object) -> DecisionTraceResponse:
        self.decision_trace_calls.append(kwargs)
        return self.decision_trace_response


class RecordingProjectMemoryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = make_project_projection()

    def summarize(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RecordingIssueMemoryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = make_open_questions_projection()

    def open_questions(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RecordingFactory:
    def __init__(
        self,
        *,
        status_report: StatusReport | None = None,
        graph_retrieval_service: RecordingGraphRetrievalService | None = None,
        retrieval_service: RecordingRetrievalService | None = None,
        context_pack_builder: RecordingContextPackBuilder | None = None,
    ) -> None:
        self.status_service = RecordingStatusService(status_report or make_status_report())
        self.graph_retrieval_service = graph_retrieval_service or RecordingGraphRetrievalService()
        self.retrieval_service = retrieval_service or RecordingRetrievalService(make_search_response())
        self.context_pack_builder = context_pack_builder or RecordingContextPackBuilder(make_pack())
        self.project_memory_service = RecordingProjectMemoryService()
        self.issue_memory_service = RecordingIssueMemoryService()
        self.status_calls = 0
        self.graph_calls = 0
        self.retrieval_calls = 0
        self.context_builder_calls = 0
        self.project_memory_calls = 0
        self.issue_memory_calls = 0

    def open_status_service(self) -> RecordingStatusService:
        self.status_calls += 1
        return self.status_service

    def open_graph_retrieval_service(self) -> RecordingGraphRetrievalService:
        self.graph_calls += 1
        return self.graph_retrieval_service

    def open_retrieval_service(self, *, include_graph: bool = False) -> RecordingRetrievalService:
        assert include_graph is True
        self.retrieval_calls += 1
        return self.retrieval_service

    def open_context_pack_builder(self, *, include_graph: bool = False) -> RecordingContextPackBuilder:
        assert include_graph is True
        self.context_builder_calls += 1
        return self.context_pack_builder

    def open_project_memory_service(self) -> RecordingProjectMemoryService:
        self.project_memory_calls += 1
        return self.project_memory_service

    def open_issue_memory_service(self) -> RecordingIssueMemoryService:
        self.issue_memory_calls += 1
        return self.issue_memory_service


def test_register_mcp_tools_registers_exact_phase_6b_tools(tmp_path: Path) -> None:
    server = RecordingToolServer()

    registry = register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert registry.tool_names == (
        "search_vault",
        "build_context_pack",
        "find_related",
        "get_decision_trace",
        "check_index_status",
        "explain_result",
        "summarize_project_memory",
        "get_open_questions",
    )
    assert tuple(server.tools) == registry.tool_names
    assert all(server.structured_output[name] is True for name in registry.tool_names)
    assert "ask_vault" not in server.tools
    assert "get_recent_changes" not in server.tools


@pytest.mark.parametrize(
    ("tool_name", "kwargs"),
    [
        ("search_vault", {"query": "   "}),
        ("build_context_pack", {"goal": ""}),
        ("find_related", {"target": "", "depth": 1}),
        ("get_decision_trace", {"decision_or_topic": ""}),
        ("summarize_project_memory", {"limit": 0}),
        ("get_open_questions", {"limit": 51}),
        ("search_vault", {"query": "q", "limit": 51}),
        ("build_context_pack", {"goal": "g", "max_tokens": 0}),
        ("search_vault", {"query": "q", "include_cross_vault": True, "scope": {"include_cross_vault": False}}),
    ],
)
def test_tool_validation_errors_are_structured(
    tmp_path: Path,
    tool_name: str,
    kwargs: dict[str, object],
) -> None:
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools[tool_name](**kwargs)

    assert exc_info.value.kind == "invalid_parameter"
    assert exc_info.value.payload.code == "invalid_tool_arguments"


def test_search_vault_uses_base_retrieval_service_when_graph_false(tmp_path: Path) -> None:
    response = make_search_response(path="wiki/page.md")
    retrieval = RecordingRetrievalService(response)
    services = fake_services(tmp_path, retrieval_service=retrieval)
    registry = McpToolRegistry(
        services=services,
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.search_vault(SearchVaultInput(query="GraphRAG", limit=3))

    assert retrieval.calls[0]["query_text"] == "GraphRAG"
    assert retrieval.calls[0]["limit"] == 3
    assert retrieval.calls[0]["include_graph"] is False
    assert body.tool_name == "search_vault"
    assert body.payload["result_count"] == 1
    assert any(link.uri.startswith("vault://main/documents/") for link in body.resource_links)


def test_build_context_pack_renders_and_caches_pack_json(tmp_path: Path) -> None:
    pack = replace(make_pack(), pack_id="pack-1")
    cache = ContextPackResourceCache()
    builder = RecordingContextPackBuilder(pack)
    services = fake_services(tmp_path, context_pack_builder=builder)
    registry = McpToolRegistry(
        services=services,
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=cache,
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.build_context_pack(BuildContextPackInput(goal="Implement MCP tools"))

    assert cache.get("pack-1") is not None
    assert any(link.uri == "vault://context/packs/pack-1" for link in body.resource_links)
    assert body.payload["pack_id"] == "pack-1"


def test_check_index_status_uses_status_service_without_indexing(tmp_path: Path) -> None:
    factory = fake_factory(status_report=make_status_report())
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.check_index_status(CheckIndexStatusInput())

    assert factory.status_calls == 1
    metadata = cast(dict[str, object], body.payload["metadata"])
    embedding = cast(dict[str, object], body.payload["embedding"])
    assert metadata["ok"] is True
    assert embedding["embedding_batch_size"] == 8


def test_find_related_opens_graph_service_after_validation(tmp_path: Path) -> None:
    graph_service = RecordingGraphRetrievalService(related_response=make_related_response())
    factory = fake_factory(graph_retrieval_service=graph_service)
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.find_related(FindRelatedInput(target="GraphRAG", depth=1, kinds=("depends_on",), limit=5))

    assert factory.graph_calls == 1
    assert graph_service.related_calls[0]["target"] == "GraphRAG"
    assert graph_service.related_calls[0]["relationship_types"] == ("depends_on",)
    assert body.tool_name == "find_related"
    assert body.payload["result_count"] == 1


def test_decision_trace_opens_graph_service_after_validation(tmp_path: Path) -> None:
    graph_service = RecordingGraphRetrievalService(decision_trace_response=make_decision_trace_response())
    factory = fake_factory(graph_retrieval_service=graph_service)
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.get_decision_trace(DecisionTraceInput(decision_or_topic="Phase 5"))

    assert factory.graph_calls == 1
    assert graph_service.decision_trace_calls[0]["topic"] == "Phase 5"
    assert body.tool_name == "get_decision_trace"


def test_summarize_project_memory_uses_project_memory_service(tmp_path: Path) -> None:
    factory = fake_factory()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.summarize_project_memory(SummarizeProjectMemoryInput(limit=7))

    assert factory.project_memory_calls == 1
    assert factory.project_memory_service.calls[0]["limit"] == 7
    assert body.tool_name == "summarize_project_memory"
    assert body.payload["vaults"]


def test_get_open_questions_uses_issue_memory_service(tmp_path: Path) -> None:
    factory = fake_factory()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.get_open_questions(GetOpenQuestionsInput(limit=11))

    assert factory.issue_memory_calls == 1
    assert factory.issue_memory_service.calls[0]["limit"] == 11
    assert body.tool_name == "get_open_questions"
    assert body.payload["vaults"]


def test_memory_tools_support_active_vault_explicit_vault_ids_and_all_vaults(tmp_path: Path) -> None:
    server = RecordingToolServer()
    factory = fake_factory()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    server.tools["summarize_project_memory"]()
    server.tools["summarize_project_memory"](scope={"vault_ids": ["main"]})
    server.tools["summarize_project_memory"](scope={"all_vaults": True})

    assert factory.project_memory_calls == 3


def test_memory_tools_reject_include_cross_vault_scope(tmp_path: Path) -> None:
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools["summarize_project_memory"](scope={"include_cross_vault": True})

    assert exc_info.value.kind == "invalid_parameter"


def test_memory_tool_errors_map_memory_projection_error(tmp_path: Path) -> None:
    class FailingProjectMemoryService:
        def summarize(self, **kwargs: object) -> object:
            del kwargs
            raise MemoryProjectionError("metadata_unavailable: not initialized")

    factory = fake_factory()
    factory.project_memory_service = cast(Any, FailingProjectMemoryService())
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        registry.summarize_project_memory(SummarizeProjectMemoryInput())

    assert exc_info.value.kind == "execution"
    assert exc_info.value.payload.code == "metadata_unavailable"


def test_invalid_graph_tool_arguments_fail_before_opening_graph_service(tmp_path: Path) -> None:
    factory = fake_factory()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError):
        registry.find_related(FindRelatedInput(target="", depth=1))

    assert factory.graph_calls == 0


def fake_catalog(tmp_path: Path) -> VaultCatalog:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    return VaultCatalog.from_entries(
        entries=(VaultCatalogEntry.from_root(vault_id="main", root_path=vault_root, display_name="Main"),),
        active_vault_id="main",
    )


def fake_services(
    tmp_path: Path,
    *,
    retrieval_service: RecordingRetrievalService | None = None,
    context_pack_builder: RecordingContextPackBuilder | None = None,
) -> McpServices:
    return McpServices(
        catalog_service=cast(Any, object()),
        catalog=fake_catalog(tmp_path),
        metadata_store=cast(Any, object()),
        retrieval_service=cast(Any, retrieval_service or RecordingRetrievalService(make_search_response())),
        context_pack_builder=cast(Any, context_pack_builder or RecordingContextPackBuilder(make_pack())),
        context_pack_renderer=DefaultContextPackRenderer(),
    )


def fake_factory(
    *,
    status_report: StatusReport | None = None,
    graph_retrieval_service: RecordingGraphRetrievalService | None = None,
) -> RecordingFactory:
    return RecordingFactory(status_report=status_report, graph_retrieval_service=graph_retrieval_service)


def make_related_response() -> RelatedResponse:
    source = make_entity("main")
    target = make_entity("main", name="Search")
    relationship = make_relationship(source, target)
    evidence = make_metadata_evidence_from_graph_ref(relationship.evidence_refs[0])
    item = RelatedItem(
        rank=1,
        entity=target,
        relationship_path=(relationship,),
        evidence=(evidence,),
        score=0.9,
        explanation="GraphRAG depends_on Search",
    )
    return RelatedResponse(
        target="GraphRAG",
        resolved_target=source,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        projection_build_id="projection-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=1,
        items=(item,),
        warnings=(),
        store_revisions=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def make_decision_trace_response() -> DecisionTraceResponse:
    entity = make_entity("main", name="Phase 5")
    step = DecisionTraceStep(
        rank=1,
        role="decision",
        entity=entity,
        relationship_path=(),
        evidence=(make_metadata_evidence_from_graph_ref(entity.evidence_refs[0]),),
        relationship_status="not_applicable",
        explanation="resolved decision",
    )
    return DecisionTraceResponse(
        topic="Phase 5",
        trace_kind="decision",
        resolved_target=entity,
        target_candidates=(),
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        projection_build_id=None,
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        steps=(step,),
        warnings=(),
        store_revisions=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def make_status_report() -> StatusReport:
    return StatusReport(
        active_vault_id="main",
        vaults=(("main", "/vault"),),
        metadata_ok=True,
        metadata_schema_compatible=True,
        metadata_message="ok",
        vector_ok=True,
        vector_backend="chroma",
        vector_schema_compatible=True,
        vector_message="ok",
        embedding_model="deterministic",
        embedding_model_version="test",
        embedding_dimensions=4,
        embedding_spec_version="embedding-spec-v1",
        embedding_batch_size=8,
        embedding_parallelism=None,
        embedding_lazy_load=True,
        vector_revision="vector-1",
        vector_stale_count=0,
        vector_last_error=None,
        vector_status_scope="main:wiki",
        graph_readiness=GraphReadiness(
            backend_name="sqlite",
            backend_available=True,
            schema_version="graph-store-v1",
            schema_compatible=True,
            graph_extraction_spec_version="graph-extraction-spec-v2",
            graph_extraction_spec_digest="0" * 64,
            graph_extraction_spec_compatible=True,
            freshness="fresh",
            stale_count=0,
            tombstone_count=0,
            last_graph_revision="graph-1",
            affected_vault_ids=("main",),
            scope_readiness=(),
            warnings=(),
            recovery_hint="",
        ),
        graph_status_scope="main:wiki",
        graph_last_error=None,
    )
