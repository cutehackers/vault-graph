"""The MCP read tools follow the active index generation (finding 발견2).

A hook or ``vg index`` in another process can publish a new projection generation while the
server runs. Before each read tool call the registry compares the active generation id with the
one its read services were opened on, and reopens them when it changed.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_tool_serialization import make_search_response
from tests.test_mcp_tools import RecordingFactory, RecordingRetrievalService, fake_services
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory, McpServices
from vault_graph.interface.mcp.mcp_tools import (
    AskVaultInput,
    BuildContextPackInput,
    CheckIndexStatusInput,
    DecisionTraceInput,
    ExplainResultInput,
    ExploreProjectInput,
    FindRelatedInput,
    GetOpenQuestionsInput,
    GetRecentChangesInput,
    McpToolRegistry,
    SearchVaultInput,
    SummarizeProjectMemoryInput,
)
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache


class GenerationFactory(RecordingFactory):
    """A factory whose active generation id the test moves, like another process publishing an index."""

    def __init__(self, fresh_services: McpServices) -> None:
        super().__init__()
        self.generation: str | None = "g1"
        self.fresh_services = fresh_services
        self.read_only_opened = 0
        self.generation_reads = 0

    def active_generation_id(self) -> str | None:
        self.generation_reads += 1
        return self.generation

    def open_read_only(self) -> McpServices:
        self.read_only_opened += 1
        return replace(self.fresh_services, generation_id=self.generation)


def _setup(
    tmp_path: Path,
) -> tuple[McpToolRegistry, GenerationFactory, RecordingRetrievalService, RecordingRetrievalService]:
    stale = RecordingRetrievalService(make_search_response())
    fresh = RecordingRetrievalService(make_search_response())
    (tmp_path / "fresh").mkdir()
    factory = GenerationFactory(fake_services(tmp_path / "fresh", retrieval_service=fresh))
    services = replace(fake_services(tmp_path, retrieval_service=stale), generation_id="g1")
    registry = McpToolRegistry(
        services=services,
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    return registry, factory, stale, fresh


def _search(registry: McpToolRegistry, tmp_path: Path) -> None:
    registry.search_vault(SearchVaultInput(query="GraphRAG", cwd=str(tmp_path)))


def test_search_keeps_its_services_while_the_generation_is_unchanged(tmp_path: Path) -> None:
    registry, factory, stale, fresh = _setup(tmp_path)

    _search(registry, tmp_path)
    _search(registry, tmp_path)

    assert factory.read_only_opened == 0
    assert factory.generation_reads == 2
    assert len(stale.calls) == 2 and fresh.calls == []


def test_search_reopens_services_once_after_another_process_publishes(tmp_path: Path) -> None:
    registry, factory, stale, fresh = _setup(tmp_path)
    _search(registry, tmp_path)

    factory.generation = "g2"
    _search(registry, tmp_path)
    _search(registry, tmp_path)

    assert factory.read_only_opened == 1
    assert len(stale.calls) == 1
    assert len(fresh.calls) == 2


def test_unreadable_generation_keeps_the_current_services(tmp_path: Path) -> None:
    registry, factory, stale, _ = _setup(tmp_path)

    def broken() -> str | None:
        raise OSError("active.json is being replaced")

    factory.active_generation_id = broken  # type: ignore[method-assign]
    _search(registry, tmp_path)

    assert factory.read_only_opened == 0
    assert len(stale.calls) == 1


def test_failed_reopen_keeps_the_current_services(tmp_path: Path) -> None:
    registry, factory, stale, _ = _setup(tmp_path)

    def broken_open() -> McpServices:
        raise RuntimeError("generation folder vanished")

    factory.open_read_only = broken_open  # type: ignore[method-assign]
    factory.generation = "g2"
    _search(registry, tmp_path)

    assert len(stale.calls) == 1


READ_TOOL_CALLS: dict[str, Callable[[McpToolRegistry, str], object]] = {
    "ask_vault": lambda r, cwd: r.ask_vault(AskVaultInput(question="why?", cwd=cwd)),
    "search_vault": lambda r, cwd: r.search_vault(SearchVaultInput(query="q", cwd=cwd)),
    "build_context_pack": lambda r, cwd: r.build_context_pack(BuildContextPackInput(goal="g", cwd=cwd)),
    "find_related": lambda r, cwd: r.find_related(FindRelatedInput(target="t", cwd=cwd)),
    "get_decision_trace": lambda r, cwd: r.get_decision_trace(DecisionTraceInput(decision_or_topic="t", cwd=cwd)),
    "summarize_project_memory": lambda r, cwd: r.summarize_project_memory(SummarizeProjectMemoryInput(cwd=cwd)),
    "get_open_questions": lambda r, cwd: r.get_open_questions(GetOpenQuestionsInput(cwd=cwd)),
    "get_recent_changes": lambda r, cwd: r.get_recent_changes(GetRecentChangesInput(cwd=cwd)),
    "explore_project": lambda r, cwd: r.explore_project(ExploreProjectInput(task="t", project_path=cwd)),
    "check_index_status": lambda r, cwd: r.check_index_status(CheckIndexStatusInput()),
    "explain_result": lambda r, cwd: r.explain_result(ExplainResultInput(result_id="missing")),
}


@pytest.mark.parametrize("tool_name", sorted(READ_TOOL_CALLS))
def test_every_read_tool_checks_the_generation_first(tmp_path: Path, tool_name: str) -> None:
    registry, factory, _, _ = _setup(tmp_path)
    factory.generation = "g2"

    try:
        READ_TOOL_CALLS[tool_name](registry, str(tmp_path))
    except McpProtocolError:
        pass  # Some fakes cannot serve the tool. The generation check runs before the tool body.

    assert factory.generation_reads == 1
    assert factory.read_only_opened == 1


def test_concurrent_calls_reopen_the_services_once(tmp_path: Path) -> None:
    registry, factory, _, _ = _setup(tmp_path)
    factory.generation = "g2"
    opened = threading.Event()
    real_open = factory.open_read_only

    def slow_open() -> McpServices:
        opened.wait(0.2)
        return real_open()

    factory.open_read_only = slow_open  # type: ignore[method-assign]
    threads = [threading.Thread(target=_search, args=(registry, tmp_path)) for _ in range(4)]
    for thread in threads:
        thread.start()
    opened.set()
    for thread in threads:
        thread.join(5)

    assert factory.read_only_opened == 1


# --- McpServiceFactory reads the generation id from projections/active.json ---


def test_factory_reads_the_active_generation_id(tmp_path: Path) -> None:
    factory = McpServiceFactory(graph_home_path=tmp_path)
    assert factory.active_generation_id() is None

    (tmp_path / "projections").mkdir()
    (tmp_path / "projections" / "active.json").write_text(
        json.dumps({"generation_id": "gen-2", "generation_path": "projections/generations/gen-2"}),
        encoding="utf-8",
    )

    assert factory.active_generation_id() == "gen-2"


def test_factory_records_the_generation_its_services_were_opened_on(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from vault_graph.interface.cli.main import app

    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    graph_home = tmp_path / "state"
    result = CliRunner().invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    factory = McpServiceFactory(graph_home_path=graph_home)

    services = factory.open_read_only()

    assert services.generation_id == factory.active_generation_id()
