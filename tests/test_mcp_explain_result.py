from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_tool_serialization import make_pack_with_item
from tests.test_mcp_tools import (
    RecordingContextPackBuilder,
    fake_factory,
    fake_services,
)
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_tools import (
    BuildContextPackInput,
    CheckIndexStatusInput,
    DecisionTraceInput,
    ExplainResultInput,
    FindRelatedInput,
    McpToolRegistry,
    SearchVaultInput,
    parse_explain_result_input,
)
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


def make_registry(
    tmp_path: Path,
    *,
    cache: ResultExplanationCache | None = None,
    context_pack_builder: RecordingContextPackBuilder | None = None,
) -> tuple[McpToolRegistry, ResultExplanationCache]:
    result_cache = cache if cache is not None else ResultExplanationCache()
    registry = McpToolRegistry(
        services=fake_services(tmp_path, context_pack_builder=context_pack_builder),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=result_cache,
    )
    return registry, result_cache


def test_search_tool_registers_explanation_records(tmp_path: Path) -> None:
    registry, cache = make_registry(tmp_path)

    body = registry.search_vault(SearchVaultInput(query="GraphRAG"))
    result = cast(list[dict[str, object]], body.payload["results"])[0]

    cached = cache.get(cast(str, result["result_id"]))
    assert cached is not None
    assert cached.record.source_kind == "search_result"


def test_context_pack_tool_registers_explanation_records(tmp_path: Path) -> None:
    builder = RecordingContextPackBuilder(replace(make_pack_with_item(), pack_id="pack-1"))
    registry, cache = make_registry(tmp_path, context_pack_builder=builder)

    registry.build_context_pack(BuildContextPackInput(goal="Implement MCP tools"))

    cached = cache.get("item-1")
    assert cached is not None
    assert cached.record.source_kind == "context_pack_item"


def test_related_tool_registers_explanation_records(tmp_path: Path) -> None:
    registry, cache = make_registry(tmp_path)

    body = registry.find_related(FindRelatedInput(target="GraphRAG"))
    item = cast(list[dict[str, object]], body.payload["items"])[0]

    cached = cache.get(cast(str, item["result_id"]))
    assert cached is not None
    assert cached.record.source_kind == "related_item"


def test_decision_trace_tool_registers_explanation_records(tmp_path: Path) -> None:
    registry, cache = make_registry(tmp_path)

    body = registry.get_decision_trace(DecisionTraceInput(decision_or_topic="Phase 5"))
    step = cast(list[dict[str, object]], body.payload["steps"])[0]

    cached = cache.get(cast(str, step["result_id"]))
    assert cached is not None
    assert cached.record.source_kind == "decision_trace_step"


def test_explain_result_returns_cached_search_record(tmp_path: Path) -> None:
    registry, _cache = make_registry(tmp_path)
    search_body = registry.search_vault(SearchVaultInput(query="GraphRAG"))
    result = cast(list[dict[str, object]], search_body.payload["results"])[0]

    body = registry.explain_result(ExplainResultInput(result_id=cast(str, result["result_id"])))

    assert body.tool_name == "explain_result"
    assert body.payload["result_id"] == result["result_id"]
    assert body.payload["source_kind"] == "search_result"
    assert body.text


def test_explain_result_returns_not_found_for_missing_record(tmp_path: Path) -> None:
    registry, _cache = make_registry(tmp_path)

    with pytest.raises(McpProtocolError) as exc_info:
        registry.explain_result(ExplainResultInput(result_id="missing"))

    assert exc_info.value.kind == "not_found"
    assert exc_info.value.payload.code == "result_explanation_not_found"


def test_explain_result_validation_rejects_blank_result_id() -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_explain_result_input(result_id=" ")

    assert exc_info.value.kind == "invalid_parameter"
    assert exc_info.value.payload.code == "invalid_tool_arguments"


def test_check_index_status_does_not_register_explanation_records(tmp_path: Path) -> None:
    registry, cache = make_registry(tmp_path)

    registry.check_index_status(CheckIndexStatusInput())

    assert len(cache) == 0


def test_failed_tool_response_serialization_does_not_register_explanation_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, cache = make_registry(tmp_path)

    def fail_payload(_: object) -> dict[str, object]:
        raise RuntimeError("payload serialization failed")

    monkeypatch.setattr("vault_graph.mcp.mcp_tool_serialization.search_response_to_payload", fail_payload)

    with pytest.raises(McpProtocolError):
        registry.search_vault(SearchVaultInput(query="GraphRAG"))

    assert len(cache) == 0


def test_explain_result_not_found_after_cache_eviction(tmp_path: Path) -> None:
    registry, _cache = make_registry(tmp_path, cache=ResultExplanationCache(max_entries=1))

    search_body = registry.search_vault(SearchVaultInput(query="GraphRAG"))
    result = cast(list[dict[str, object]], search_body.payload["results"])[0]
    registry.find_related(FindRelatedInput(target="GraphRAG"))

    with pytest.raises(McpProtocolError) as exc_info:
        registry.explain_result(ExplainResultInput(result_id=cast(str, result["result_id"])))

    assert exc_info.value.kind == "not_found"
