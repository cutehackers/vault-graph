from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_memory_tools import make_recent_changes_projection
from tests.test_mcp_tools import RecordingFactory, RecordingToolServer, fake_services
from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_service_factory import McpServices
from vault_graph.mcp.mcp_tools import (
    GetRecentChangesInput,
    McpToolRegistry,
    parse_get_recent_changes_input,
    register_mcp_tools,
)
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


class RecordingTimelineMemoryService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response = make_recent_changes_projection()

    def recent_changes(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class RecentChangesFactory(RecordingFactory):
    def __init__(self) -> None:
        super().__init__()
        self.timeline_memory_service: object = RecordingTimelineMemoryService()
        self.timeline_calls = 0

    def open_timeline_memory_service(self) -> object:
        self.timeline_calls += 1
        return self.timeline_memory_service


class FailingTimelineMemoryService:
    def recent_changes(self, **kwargs: object) -> object:
        del kwargs
        raise MemoryProjectionError("metadata_unavailable: not initialized")


def test_parse_get_recent_changes_input_validates_limit_since_and_scope() -> None:
    request = parse_get_recent_changes_input(
        since="2026-06-18T00:00:00",
        scope={"vault_ids": ["main"]},
        limit=20,
    )

    assert request.since == "2026-06-18T00:00:00+00:00"
    assert request.limit == 20
    assert request.scope is not None

    with pytest.raises(McpProtocolError, match="since"):
        parse_get_recent_changes_input(since="not-a-date", limit=20)

    with pytest.raises(McpProtocolError, match="limit"):
        parse_get_recent_changes_input(limit=51)

    with pytest.raises(McpProtocolError):
        parse_get_recent_changes_input(scope={"include_cross_vault": True})


def test_get_recent_changes_uses_timeline_service_and_returns_tool_body(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.get_recent_changes(GetRecentChangesInput(limit=7))

    timeline_service = cast(RecordingTimelineMemoryService, factory.timeline_memory_service)
    assert factory.timeline_calls == 1
    assert timeline_service.calls[0]["limit"] == 7
    assert body.tool_name == "get_recent_changes"
    assert body.payload["vaults"]
    assert body.resource_links[0].uri == "vault://main/documents/wiki%2Fpage.md"
    assert body.warnings


def test_register_mcp_tools_includes_phase_6c_tool(tmp_path: Path) -> None:
    server = RecordingToolServer()
    registry = register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, RecentChangesFactory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert "get_recent_changes" in registry.tool_names
    assert "get_recent_changes" in server.tools


def test_get_recent_changes_supports_all_vaults_scope(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_multi_vault_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    server.tools["get_recent_changes"](scope={"all_vaults": True})

    timeline_service = cast(RecordingTimelineMemoryService, factory.timeline_memory_service)
    requested_scope = timeline_service.calls[0]["requested_scope"]
    assert isinstance(requested_scope, QueryScope)
    assert requested_scope.vault_ids == ("main", "work")


def test_get_recent_changes_maps_metadata_errors_with_scope_and_recovery_hint(tmp_path: Path) -> None:
    factory = RecentChangesFactory()
    factory.timeline_memory_service = cast(Any, FailingTimelineMemoryService())
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    with pytest.raises(McpProtocolError) as exc_info:
        registry.get_recent_changes(GetRecentChangesInput())

    assert exc_info.value.payload.code == "metadata_unavailable"
    assert exc_info.value.payload.affected_vault_ids == ("main",)
    assert exc_info.value.payload.recovery_hint == "Run vg index, then vg status for the selected Vault."


def fake_multi_vault_services(tmp_path: Path) -> McpServices:
    services = fake_services(tmp_path)
    main_root = tmp_path / "main"
    work_root = tmp_path / "work"
    main_root.mkdir()
    work_root.mkdir()
    catalog = VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=main_root, display_name="Main"),
            VaultCatalogEntry.from_root(vault_id="work", root_path=work_root, display_name="Work"),
        ),
        active_vault_id="main",
    )
    return replace(services, catalog=catalog)
