from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tests.test_answer_response_contract import make_response
from tests.test_mcp_tools import RecordingToolServer, fake_factory, fake_services
from vault_graph.answer.answer_plan import AnswerRequest
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_tools import AskVaultInput, McpToolRegistry, register_mcp_tools
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


class RecordingAnswerService:
    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []

    def ask(self, request: AnswerRequest) -> object:
        self.requests.append(request)
        return make_response()


def test_register_mcp_tools_registers_ask_vault(tmp_path: Path) -> None:
    server = RecordingToolServer()

    registry = register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert "ask_vault" in registry.tool_names
    assert "ask_vault" in server.tools
    assert server.structured_output["ask_vault"] is True


def test_ask_vault_uses_answer_service_and_returns_payload(tmp_path: Path) -> None:
    service = RecordingAnswerService()
    factory = fake_factory()
    factory.answer_service = service
    cache = ResultExplanationCache()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=cache,
    )

    body = registry.ask_vault(AskVaultInput(question="Why GraphRAG?", limit=3))

    assert service.requests[0].question == "Why GraphRAG?"
    assert service.requests[0].retrieval_limit == 3
    assert body.tool_name == "ask_vault"
    assert body.payload["answer_status"] == "supported"
    assert any(link.uri.startswith("vault://main/documents/") for link in body.resource_links)
    assert len(cache) == 1


def test_ask_vault_registered_function_accepts_scope(tmp_path: Path) -> None:
    service = RecordingAnswerService()
    factory = fake_factory()
    factory.answer_service = service
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    result = server.tools["ask_vault"](question="Why GraphRAG?", scope={"vault_ids": ["main"]})

    assert result["tool_name"] == "ask_vault"  # type: ignore[index]
    assert service.requests[0].requested_scope.vault_ids == ("main",)
