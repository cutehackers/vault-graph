from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_tools import RecordingToolServer, fake_services
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_tool_serialization import resource_links_for_project_context
from vault_graph.mcp.mcp_tools import (
    ExploreProjectInput,
    McpToolRegistry,
    parse_explore_project_input,
    register_mcp_tools,
)
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.project_context import (
    ProjectAuthorityFreshness,
    ProjectBinding,
    ProjectContext,
    ProjectContextBudget,
    ProjectEvidence,
)


def _context() -> ProjectContext:
    return ProjectContext(
        task="Trace the request flow",
        repository_id="demo",
        binding=ProjectBinding("demo", ("main",), ("wiki",)),
        freshness="fresh",
        code_evidence=(
            ProjectEvidence(
                evidence_id="code:symbol-1",
                authority="code",
                title="run",
                summary="def run()",
                relationship_status="stated",
                revision="git-1",
                freshness="fresh",
                source_uri="vg-source://demo/src%2Fdemo.py#L3-L5",
                repository_id="demo",
                relative_path="src/demo.py",
                start_line=3,
                end_line=5,
            ),
        ),
        vault_evidence=(
            ProjectEvidence(
                evidence_id="vault:main:doc-1:chunk-1",
                authority="vault",
                title="Decision",
                summary="Keep boundaries",
                relationship_status="stated",
                revision="vault-1",
                freshness="fresh",
                source_uri="vault://main/wiki/decision.md",
                vault_id="main",
            ),
        ),
        relations=(),
        authority_freshness=(
            ProjectAuthorityFreshness("code", "demo", "fresh", revision="git-1"),
            ProjectAuthorityFreshness("vault", "main", "fresh", revision="vault-1"),
        ),
        warnings=(),
        budget=ProjectContextBudget(max_tokens=4000, used_tokens=1),
    )


@dataclass
class _ProjectService:
    context: ProjectContext
    requests: list[object]

    def build(self, request: object) -> ProjectContext:
        self.requests.append(request)
        return self.context


class _Factory:
    def __init__(self, service: _ProjectService) -> None:
        self.service = service
        self.project_context_calls = 0

    def open_project_context_service(self) -> _ProjectService:
        self.project_context_calls += 1
        return self.service


def test_parse_explore_project_input_defaults_to_bounded_project_context_contract() -> None:
    request = parse_explore_project_input(task="Trace the request flow", repository_id="demo")

    assert request == ExploreProjectInput(task="Trace the request flow", repository_id="demo")


@pytest.mark.parametrize(
    "kwargs",
    (
        {"task": "   "},
        {"task": "x" * 4097},
        {"task": "x", "depth": 9},
        {"task": "x", "limit": 101},
        {"task": "x", "max_tokens": 16001},
        {"task": "x", "project_path": "/private/repository", "repository_id": "demo"},
    ),
)
def test_parse_explore_project_input_rejects_invalid_or_ambiguous_scope_without_path_leakage(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(McpProtocolError) as exc_info:
        parse_explore_project_input(**cast(Any, kwargs))

    assert exc_info.value.kind == "invalid_parameter"
    assert "/private/repository" not in exc_info.value.payload.message


def test_explore_project_is_a_thin_service_adapter_with_compact_evidence_links(tmp_path: Path) -> None:
    service = _ProjectService(_context(), [])
    factory = _Factory(service)
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    body = registry.explore_project(ExploreProjectInput(task="Trace the request flow", repository_id="demo"))

    assert factory.project_context_calls == 1
    assert service.requests == [
        ExploreProjectInput(task="Trace the request flow", repository_id="demo").to_project_context_request()
    ]
    assert body.tool_name == "explore_project"
    assert body.payload["repository_id"] == "demo"
    assert "source_lines" not in repr(body.payload)
    assert {link.uri for link in body.resource_links} == {
        "vg-source://demo/src%2Fdemo.py#L3-L5",
        "vault://main/wiki/decision.md",
    }
    assert all("/private/" not in link.uri for link in body.resource_links)
    assert "Repository: demo" in body.text


def test_register_mcp_tools_registers_explore_project_once(tmp_path: Path) -> None:
    server = RecordingToolServer()
    service = _ProjectService(_context(), [])
    registry = register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, _Factory(service)),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    assert registry.tool_names.count("explore_project") == 1
    assert "explore_project" in server.tools


def test_project_context_serializer_drops_unsafe_repository_source_links() -> None:
    context = _context()
    unsafe = replace(context.code_evidence[0], source_uri="file:///private/repository/demo.py")

    assert resource_links_for_project_context(replace(context, code_evidence=(unsafe,))) == (
        resource_links_for_project_context(replace(context, code_evidence=()))[0],
    )
