"""MCP tools stay inside the project of the server working folder (spec 2026-11-02 V2, V3, 결정12, 결정13).

Post-review fixes:
- F7: ``remember``, ``update_memory`` and ``retire_memory`` default ``cwd`` to the server working folder.
- F4: ``find_related``, ``get_decision_trace``, ``summarize_project_memory``, ``get_open_questions`` and
  ``get_recent_changes`` accept ``cwd`` and use the project's Vaults when no scope is named.
- F1: a ``published`` write starts a background index of that one Vault.
- F8: the write tool schemas list the allowed ``basis``, ``kind`` and ``memory_kind`` values.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any, cast, get_args

import pytest

from tests.test_mcp_tool_serialization import make_search_response
from tests.test_mcp_tools import (
    RecordingFactory,
    RecordingMemoryWriteService,
    RecordingRetrievalService,
    RecordingToolServer,
    fake_factory,
    fake_services,
    project_setup,
)
from tests.test_memory_write_service import DiskPageReader, RecordingWriter
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_service_factory import McpServices
from vault_graph.interface.mcp.mcp_tools import (
    DecisionTraceInput,
    FindRelatedInput,
    GetOpenQuestionsInput,
    GetRecentChangesInput,
    McpToolRegistry,
    MemoryBasis,
    MemoryKind,
    PageKind,
    RememberInput,
    SummarizeProjectMemoryInput,
    register_mcp_tools,
)
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import BASES, MEMORY_KINDS, REMEMBER_KINDS, MemoryWriteResult
from vault_graph.operation.memory.memory_write_service import NEXT_INDEX_MESSAGE, MemoryWriteService
from vault_graph.operation.scope.vault_catalog import QueryScope

PAGE = "wiki/decisions/use-sqlite.md"


def _registry(services: McpServices, factory: RecordingFactory) -> McpToolRegistry:
    return McpToolRegistry(
        services=services,
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )


def _write_page(vault_root: Path, path: str = PAGE) -> None:
    target = vault_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("---\ntitle: Use SQLite\ntype: decision\n---\n\n# Use SQLite\n\nBody.\n", encoding="utf-8")


def _real_write_service(writer: RecordingWriter) -> MemoryWriteService:
    opening = open_vault_map(vault_map_path())
    assert opening.vault_map is not None
    return MemoryWriteService(
        vault_map=opening.vault_map, writer=writer, page_reader=DiskPageReader(), today=lambda: date(2026, 11, 2)
    )


# --- F7: write tools without cwd use the server working folder's project ---


def test_remember_without_cwd_offers_only_the_project_vaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    writer = RecordingWriter()
    factory = fake_factory()
    factory.memory_write_service = _real_write_service(writer)

    body = _registry(services, factory).remember(
        RememberInput(title="Use SQLite", kind="decision", body="B", evidence=("E",), basis="stated")
    )

    assert body.payload["status"] == "vault_required"
    candidates = cast(list[dict[str, object]], body.payload["candidates"])
    assert [candidate["name"] for candidate in candidates] == ["personal", "team"]
    assert writer.calls == []


def test_remember_without_cwd_refuses_a_vault_of_another_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    writer = RecordingWriter()
    factory = fake_factory()
    factory.memory_write_service = _real_write_service(writer)

    body = _registry(services, factory).remember(
        RememberInput(
            title="Use SQLite", kind="decision", body="B", evidence=("E",), basis="stated", vault="main-vault"
        )
    )

    assert body.payload["status"] == "rejected"
    assert "not linked to project repo" in " ".join(cast(list[str], body.payload["messages"]))
    assert writer.calls == []


def test_remember_without_cwd_publishes_into_a_named_project_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    writer = RecordingWriter()
    factory = fake_factory()
    factory.memory_write_service = _real_write_service(writer)

    body = _registry(services, factory).remember(
        RememberInput(title="Use SQLite", kind="decision", body="B", evidence=("E",), basis="stated", vault="personal")
    )

    assert body.payload["status"] == "published"
    assert body.payload["vault"] == "personal"
    assert writer.calls[0][0] == (tmp_path / "personal").resolve()


@pytest.mark.parametrize("tool_name", ["update_memory", "retire_memory"])
def test_page_tools_without_cwd_look_only_in_the_project_vaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    _write_page(tmp_path / "personal")
    _write_page(tmp_path / "vault")  # main-vault, not linked to the project
    monkeypatch.chdir(repo)
    writer = RecordingWriter()
    factory = fake_factory()
    factory.memory_write_service = _real_write_service(writer)
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=services,
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    kwargs: dict[str, object] = (
        {"path": PAGE, "body": "New body.", "evidence": ["E"], "basis": "stated"}
        if tool_name == "update_memory"
        else {"path": PAGE, "reason": "Replaced", "basis": "stated"}
    )

    body = cast(dict[str, Any], server.tools[tool_name](**kwargs))

    assert body["payload"]["status"] == "published"
    assert body["payload"]["vault"] == "personal"


def test_write_tools_pass_the_server_working_folder_as_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    factory = fake_factory()
    factory.memory_write_service = RecordingMemoryWriteService(MemoryWriteResult("rejected", None, (), ("x",)))
    registry = _registry(fake_services(tmp_path), factory)

    registry.remember(RememberInput(title="A", kind="decision", body="B", evidence=("E",), basis="stated"))
    registry.remember(
        RememberInput(title="A", kind="decision", body="B", evidence=("E",), basis="stated", cwd="/elsewhere")
    )

    requests = factory.memory_write_service.requests
    assert [request.cwd for request in requests] == [str(Path.cwd()), "/elsewhere"]


# --- F4: graph and memory projection tools use the project's Vaults ---


def _call_read_tool(registry: McpToolRegistry, tool_name: str, *, cwd: str | None, scope: Any = None) -> object:
    if tool_name == "find_related":
        return registry.find_related(FindRelatedInput(target="GraphRAG", scope=scope, cwd=cwd))
    if tool_name == "get_decision_trace":
        return registry.get_decision_trace(DecisionTraceInput(decision_or_topic="Phase 5", scope=scope, cwd=cwd))
    if tool_name == "summarize_project_memory":
        return registry.summarize_project_memory(SummarizeProjectMemoryInput(scope=scope, cwd=cwd))
    if tool_name == "get_open_questions":
        return registry.get_open_questions(GetOpenQuestionsInput(scope=scope, cwd=cwd))
    return registry.get_recent_changes(GetRecentChangesInput(scope=scope, cwd=cwd))


class RecordingTimelineService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def recent_changes(self, **kwargs: object) -> object:
        from tests.test_mcp_memory_tools import make_recent_changes_projection

        self.calls.append(kwargs)
        return make_recent_changes_projection()


def _scope_factory() -> tuple[RecordingFactory, Callable[[str], QueryScope]]:
    factory = fake_factory()
    timeline = RecordingTimelineService()
    cast(Any, factory).open_timeline_memory_service = lambda: timeline

    def requested_scope(tool_name: str) -> QueryScope:
        calls: list[dict[str, object]] = {
            "find_related": factory.graph_retrieval_service.related_calls,
            "get_decision_trace": factory.graph_retrieval_service.decision_trace_calls,
            "summarize_project_memory": factory.project_memory_service.calls,
            "get_open_questions": factory.issue_memory_service.calls,
            "get_recent_changes": timeline.calls,
        }[tool_name]
        return cast(QueryScope, calls[-1]["requested_scope"])

    return factory, requested_scope


PROJECT_READ_TOOLS = (
    "find_related",
    "get_decision_trace",
    "summarize_project_memory",
    "get_open_questions",
    "get_recent_changes",
)


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_read_tool_with_cwd_uses_the_project_vaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    factory, requested_scope = _scope_factory()

    _call_read_tool(_registry(services, factory), tool_name, cwd=str(repo))

    assert requested_scope(tool_name).vault_ids == ("p-id", "t-id")


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_read_tool_without_cwd_uses_the_server_working_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    factory, requested_scope = _scope_factory()

    _call_read_tool(_registry(services, factory), tool_name, cwd=None)

    assert requested_scope(tool_name).vault_ids == ("p-id", "t-id")


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_read_tool_explicit_scope_and_outside_a_project_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    from vault_graph.interface.mcp.mcp_scope import McpScopeInput

    repo, services = project_setup(tmp_path, monkeypatch)
    factory, requested_scope = _scope_factory()
    registry = _registry(services, factory)

    _call_read_tool(registry, tool_name, cwd=str(repo), scope=McpScopeInput(vault_ids=("main",)))
    assert requested_scope(tool_name).vault_ids == ("main",)

    _call_read_tool(registry, tool_name, cwd=str(tmp_path / "team"))
    assert requested_scope(tool_name).vault_ids == ("main",)


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_read_tool_for_a_project_without_registered_vault_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool_name: str
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch, project_vaults=("unregistered",))
    factory, _ = _scope_factory()

    with pytest.raises(McpProtocolError) as exc_info:
        _call_read_tool(_registry(services, factory), tool_name, cwd=str(repo))

    assert "vg setup" in exc_info.value.payload.message
    assert factory.graph_calls == 0
    assert factory.project_memory_calls == 0
    assert factory.issue_memory_calls == 0


def test_find_related_cross_vault_works_over_the_project_vaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, services = project_setup(tmp_path, monkeypatch)
    factory, requested_scope = _scope_factory()
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=services,
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    server.tools["find_related"](target="GraphRAG", include_cross_vault=True, cwd=str(repo))

    assert requested_scope("find_related").vault_ids == ("p-id", "t-id")
    assert factory.graph_retrieval_service.related_calls[0]["include_cross_vault"] is True


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_read_tools_reject_a_bad_cwd(tmp_path: Path, tool_name: str) -> None:
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    required_inputs: dict[str, dict[str, object]] = {
        "find_related": {"target": "t"},
        "get_decision_trace": {"decision_or_topic": "t"},
    }
    required = required_inputs.get(tool_name, {})

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools[tool_name](**required, cwd="  ")

    assert exc_info.value.payload.code == "invalid_tool_arguments"


# --- F1: a published write starts a background index of that Vault ---


class IndexingFactory(RecordingFactory):
    def __init__(self, *, started: str | None = "p-id", fail: bool = False) -> None:
        super().__init__()
        self.started = started
        self.fail = fail
        self.index_requests: list[str] = []
        self.on_finished: Callable[[bool], None] | None = None
        self.read_only_opened = 0
        self.fresh_services: object | None = None

    def start_background_index(self, vault_name: str, *, on_finished: Callable[[bool], None]) -> str | None:
        self.index_requests.append(vault_name)
        self.on_finished = on_finished
        if self.fail:
            raise RuntimeError("index cannot start")
        return self.started

    def open_read_only(self) -> object:
        self.read_only_opened += 1
        return self.fresh_services


PUBLISHED = MemoryWriteResult(
    "published",
    "personal",
    (PAGE,),
    ("Applied draft: wiki/decisions/use-sqlite.md", NEXT_INDEX_MESSAGE),
    vault_role="personal",
)


def _remember(registry: McpToolRegistry) -> dict[str, object]:
    return registry.remember(
        RememberInput(title="Use SQLite", kind="decision", body="B", evidence=("E",), basis="stated")
    ).payload


def test_published_write_starts_a_background_index_and_says_so(tmp_path: Path) -> None:
    factory = IndexingFactory()
    factory.memory_write_service = RecordingMemoryWriteService(PUBLISHED)

    payload = _remember(_registry(fake_services(tmp_path), factory))

    assert factory.index_requests == ["personal"]
    messages = cast(list[str], payload["messages"])
    assert NEXT_INDEX_MESSAGE not in messages
    assert messages[0] == "Applied draft: wiki/decisions/use-sqlite.md"
    assert "background" in messages[1] and "personal" in messages[1]
    assert payload["status"] == "published"


@pytest.mark.parametrize("factory_kwargs", [{"started": None}, {"fail": True}])
def test_unavailable_background_index_keeps_the_result_and_the_old_message(
    tmp_path: Path, factory_kwargs: dict[str, Any]
) -> None:
    factory = IndexingFactory(**factory_kwargs)
    factory.memory_write_service = RecordingMemoryWriteService(PUBLISHED)

    payload = _remember(_registry(fake_services(tmp_path), factory))

    assert payload["status"] == "published"
    assert payload["messages"] == list(PUBLISHED.messages)


def test_factory_without_background_index_keeps_the_old_message(tmp_path: Path) -> None:
    factory = fake_factory()
    factory.memory_write_service = RecordingMemoryWriteService(PUBLISHED)

    payload = _remember(_registry(fake_services(tmp_path), factory))

    assert payload["messages"] == list(PUBLISHED.messages)


@pytest.mark.parametrize(
    "result",
    [
        MemoryWriteResult("proposed", "personal", (), ("queued",), review_path="scratch/review/a.md"),
        MemoryWriteResult("rejected", "personal", (), ("bad",)),
        MemoryWriteResult("error", None, (), ("failed",)),
    ],
)
def test_only_published_writes_start_an_index(tmp_path: Path, result: MemoryWriteResult) -> None:
    factory = IndexingFactory()
    factory.memory_write_service = RecordingMemoryWriteService(result)

    _remember(_registry(fake_services(tmp_path), factory))

    assert factory.index_requests == []


def test_finished_background_index_refreshes_the_search_services(tmp_path: Path) -> None:
    fresh_retrieval = RecordingRetrievalService(make_search_response())
    factory = IndexingFactory()
    (tmp_path / "fresh").mkdir()
    factory.fresh_services = fake_services(tmp_path / "fresh", retrieval_service=fresh_retrieval)
    factory.memory_write_service = RecordingMemoryWriteService(PUBLISHED)
    stale_retrieval = RecordingRetrievalService(make_search_response())
    registry = _registry(fake_services(tmp_path, retrieval_service=stale_retrieval), factory)
    _remember(registry)
    assert factory.on_finished is not None

    factory.on_finished(False)
    assert factory.read_only_opened == 0
    factory.on_finished(True)

    from vault_graph.interface.mcp.mcp_tools import SearchVaultInput

    registry.search_vault(SearchVaultInput(query="GraphRAG"))
    assert factory.read_only_opened == 1
    assert len(fresh_retrieval.calls) == 1
    assert stale_retrieval.calls == []


# --- F1: McpServiceFactory.start_background_index ---


def _graph_home_with_vault_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    import json

    from typer.testing import CliRunner

    from vault_graph.interface.cli.main import app
    from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV

    vault_root = tmp_path / "personal"
    (vault_root / "wiki").mkdir(parents=True)
    graph_home = tmp_path / "state"
    result = CliRunner().invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output
    (tmp_path / "unregistered").mkdir()
    map_file = tmp_path / "vault-map.json"
    map_file.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "personal": {"path": str(vault_root), "role": "personal"},
                    "unregistered": {"path": str(tmp_path / "unregistered"), "role": "team"},
                },
                "projects": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(VAULT_MAP_ENV, str(map_file))
    return graph_home, vault_root


def test_factory_indexes_the_registered_vault_in_a_background_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory

    graph_home, _ = _graph_home_with_vault_map(tmp_path, monkeypatch)
    release = threading.Event()
    finished = threading.Event()
    runs: list[tuple[Path, str, str]] = []
    outcomes: list[bool] = []

    def runner(graph_home_path: Path, vault_id: str) -> bool:
        release.wait(5)
        runs.append((graph_home_path, vault_id, threading.current_thread().name))
        return True

    def on_finished(succeeded: bool) -> None:
        outcomes.append(succeeded)
        finished.set()

    factory = McpServiceFactory(graph_home_path=graph_home, index_runner=runner)
    vault_id = factory.start_background_index("personal", on_finished=on_finished)

    assert vault_id == "default"
    assert runs == []  # The tool result does not wait for the index run.
    release.set()
    assert finished.wait(5)
    assert runs[0][:2] == (graph_home, "default")
    assert runs[0][2] != threading.current_thread().name
    assert outcomes == [True]


@pytest.mark.parametrize("vault_name", ["unregistered", "missing"])
def test_factory_does_not_index_a_vault_it_cannot_map_to_the_graph_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vault_name: str
) -> None:
    from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory

    graph_home, _ = _graph_home_with_vault_map(tmp_path, monkeypatch)
    runs: list[str] = []

    def runner(graph_home_path: Path, vault_id: str) -> bool:
        runs.append(vault_id)
        return True

    factory = McpServiceFactory(graph_home_path=graph_home, index_runner=runner)

    assert factory.start_background_index(vault_name, on_finished=lambda _: None) is None
    assert runs == []


def test_factory_reports_a_failed_index_run_without_raising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory

    graph_home, vault_root = _graph_home_with_vault_map(tmp_path, monkeypatch)
    finished = threading.Event()
    outcomes: list[bool] = []

    def runner(graph_home_path: Path, vault_id: str) -> bool:
        raise RuntimeError("embedding model missing")

    def on_finished(succeeded: bool) -> None:
        outcomes.append(succeeded)
        finished.set()

    before = sorted(path.relative_to(vault_root) for path in vault_root.rglob("*"))
    factory = McpServiceFactory(graph_home_path=graph_home, index_runner=runner)

    assert factory.start_background_index("personal", on_finished=on_finished) == "default"
    assert finished.wait(5)
    assert outcomes == [False]
    assert sorted(path.relative_to(vault_root) for path in vault_root.rglob("*")) == before


# --- F8: the write tool schemas list the allowed values ---


def test_literal_types_match_the_validated_values() -> None:
    assert get_args(MemoryBasis) == BASES
    assert get_args(PageKind) == REMEMBER_KINDS
    assert get_args(MemoryKind) == MEMORY_KINDS


def _fastmcp_tools(tmp_path: Path) -> dict[str, Any]:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("schema-check")
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, fake_factory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    return {tool.name: tool for tool in asyncio.run(server.list_tools())}


def _enum(property_schema: dict[str, Any]) -> list[str]:
    if "enum" in property_schema:
        return list(property_schema["enum"])
    for option in property_schema.get("anyOf", ()):
        if "enum" in option:
            return list(option["enum"])
    raise AssertionError(f"no enum in {property_schema}")


def test_write_tool_schemas_show_enums(tmp_path: Path) -> None:
    tools = _fastmcp_tools(tmp_path)

    remember = tools["remember"].inputSchema["properties"]
    assert _enum(remember["basis"]) == ["stated", "inferred"]
    assert _enum(remember["kind"]) == ["decision", "system"]
    assert _enum(remember["memory_kind"]) == ["rule", "correction", "decision", "preference"]
    update = tools["update_memory"].inputSchema["properties"]
    assert _enum(update["basis"]) == ["stated", "inferred"]
    assert _enum(update["memory_kind"]) == ["rule", "correction", "decision", "preference"]
    assert _enum(tools["retire_memory"].inputSchema["properties"]["basis"]) == ["stated", "inferred"]


@pytest.mark.parametrize("tool_name", ["remember", "update_memory", "retire_memory"])
def test_write_tool_descriptions_explain_the_fields(tmp_path: Path, tool_name: str) -> None:
    description = _fastmcp_tools(tmp_path)[tool_name].description or ""

    for text in ("basis", "stated", "inferred", "vault_required", "cwd"):
        assert text in description, text
    if tool_name == "remember":
        for text in ("kind", "memory_kind", "decision", "system", "rule", "correction", "preference"):
            assert text in description, text
    else:
        assert "wiki/" in description and ".md" in description


@pytest.mark.parametrize("tool_name", PROJECT_READ_TOOLS)
def test_project_read_tool_descriptions_explain_cwd(tmp_path: Path, tool_name: str) -> None:
    description = _fastmcp_tools(tmp_path)[tool_name].description or ""

    assert "cwd" in description
    assert "scope" in description


def test_published_page_outcome_from_writer_is_unchanged_by_index_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end with the real write service: the index message replaces only NEXT_INDEX_MESSAGE."""
    repo, services = project_setup(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)
    writer = RecordingWriter(WriteOutcome("published", written_paths=(PAGE,), messages=("Applied draft",)))
    factory = IndexingFactory()
    factory.memory_write_service = _real_write_service(writer)

    payload = (
        _registry(services, factory)
        .remember(
            RememberInput(
                title="Use SQLite", kind="decision", body="B", evidence=("E",), basis="stated", vault="personal"
            )
        )
        .payload
    )

    assert payload["written_paths"] == [PAGE]
    assert cast(list[str], payload["messages"])[0] == "Applied draft"
    assert factory.index_requests == ["personal"]


def test_index_one_vault_adds_a_new_page_like_vg_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The default runner indexes one Vault incrementally and publishes it. Vault files are not written."""
    from typer.testing import CliRunner

    from tests.test_cli_search import _deterministic_text_embeddings, write_page
    from vault_graph.interface.cli.main import app
    from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory, index_one_vault

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr(
        "vault_graph.interface.composition.local_index_service_factory._default_text_embeddings",
        _deterministic_text_embeddings,
    )
    vault_root = tmp_path / "first"
    other_root = tmp_path / "second"
    write_page(vault_root, "wiki/old.md", "# Old\nOld page\n")
    write_page(other_root, "wiki/other.md", "# Other\nOther page\n")
    graph_home = tmp_path / "state"
    cli = CliRunner()
    init = ["init", "--vault-id", "first", "--vault", str(vault_root), "--graph-home", str(graph_home)]
    assert cli.invoke(app, init).exit_code == 0
    add = ["vault", "add", "second", "--path", str(other_root), "--graph-home", str(graph_home)]
    assert cli.invoke(app, add).exit_code == 0
    assert cli.invoke(app, ["index", "--graph-home", str(graph_home), "--vault-id", "first"]).exit_code == 0
    write_page(vault_root, "wiki/decisions/new.md", "# New\nNew page\n")
    before = sorted(path.relative_to(vault_root) for path in vault_root.rglob("*"))

    assert index_one_vault(graph_home, "first") is True

    metadata = McpServiceFactory(graph_home_path=graph_home).open_read_only().metadata_store
    paths = {state.path for state in metadata.list_document_states(("first",))}
    assert {"wiki/old.md", "wiki/decisions/new.md"} <= paths
    assert not any(state.document_id for state in metadata.list_document_states(("second",)))
    assert sorted(path.relative_to(vault_root) for path in vault_root.rglob("*")) == before
