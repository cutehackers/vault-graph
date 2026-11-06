"""The five cleanup tools and ``candidate_key`` on the write tools (spec 2026-11-05 §4.4.4, §4.4.5, §4.4.12,
§4.4.13, §6, A-23, A-31, A-32).

``list_memory_candidates`` returns the cleanup bundle and starts a new cleanup, so the inferred proposal
count of the server process goes back to zero. ``mark_candidates_reviewed`` appends ``outcome: skipped``
records to the Graph Home ``memory/reviewed.jsonl``. ``import_auto_memory``, ``supersede_claim`` and
``restore_memory`` run through the M18 write service like the other write tools, and every write tool
takes an optional ``candidate_key``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from tests.test_mcp_tools import RecordingFactory, RecordingToolServer, fake_services
from tests.test_memory_write_boundary import PAGE, sha256_by_file
from vault_graph.context.memory.memory_candidates import ComparisonPage, MemoryCandidate
from vault_graph.interface.composition.adapters.vault_import_cli import VaultImportCli
from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
from vault_graph.interface.composition.memory_candidate_sources import MemoryCandidatePackage
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory
from vault_graph.interface.mcp.mcp_tools import (
    ListMemoryCandidatesInput,
    McpToolRegistry,
    RememberInput,
    register_mcp_tools,
)
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import (
    ImportRequest,
    MemoryWriteResult,
    RememberRequest,
    RestoreRequest,
    RetireRequest,
    SupersedeClaimRequest,
    UpdateRequest,
)
from vault_graph.operation.memory.memory_write_service import INFERRED_PROPOSAL_LIMIT, PROPOSAL_LIMIT_MESSAGE

NEW_TOOLS = (
    "list_memory_candidates",
    "mark_candidates_reviewed",
    "import_auto_memory",
    "supersede_claim",
    "restore_memory",
)
KEY = "session:11111111-1111-4111-8111-111111111111:u-001"
LOCATION = "raw/sessions/claude-code/2026-11-01-demo.md L12-L40"
RETIRED = ComparisonPage(
    vault_id="demo-vault",
    path="wiki/concepts/old-parser.md",
    title="옛 파서",
    status="retired",
    superseded_by=None,
    retired_reason="파서를 바꿈",
    evidence_date="2026-10-01",
)
CURRENT = ComparisonPage(
    vault_id="demo-vault",
    path="wiki/decisions/parser.md",
    title="파서 선택",
    status="active",
    superseded_by="wiki/decisions/parser-v2.md",
    retired_reason=None,
    evidence_date=None,
)
PACKAGE = MemoryCandidatePackage(
    project_id="demo",
    candidates=(
        MemoryCandidate(
            key=KEY,
            kind="session_exchange",
            location=LOCATION,
            comparison=(RETIRED, CURRENT),
            signal="correction",
            started_at=datetime(2026, 11, 1, 10, 0, tzinfo=UTC),
        ),
        MemoryCandidate(
            key="retire:wiki/concepts/quiet.md",
            kind="retire",
            location="wiki/concepts/quiet.md",
            comparison=(),
            retire_signals=("unused",),
            reasons=("90일 동안 회상에 주입만 되고 열리지 않음",),
        ),
    ),
    warnings=("The embedding model is not downloaded, so no merge candidates. Run `vg index`.",),
)


class RecordingWriteService:
    def __init__(self, result: MemoryWriteResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def _record(self, request: object) -> MemoryWriteResult:
        self.requests.append(request)
        return self.result

    remember = update = retire = supersede_claim = restore = import_auto_memory = _record


@dataclass
class RecordingReviewedLog:
    records: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def append(self, candidate_keys: Any, *, outcome: str) -> None:
        self.records.append((tuple(candidate_keys), outcome))


class CurationFactory(RecordingFactory):
    def __init__(self, package: MemoryCandidatePackage = PACKAGE) -> None:
        super().__init__()
        self.package = package
        self.package_calls: list[dict[str, object]] = []
        self.curation_starts = 0
        self.reviewed_log = RecordingReviewedLog()

    def memory_candidate_package(self, cwd: Path, **kwargs: object) -> MemoryCandidatePackage:
        self.package_calls.append({"cwd": cwd, **kwargs})
        return self.package

    def start_curation(self) -> None:
        self.curation_starts += 1

    def open_reviewed_log(self) -> RecordingReviewedLog:
        return self.reviewed_log


def registered(tmp_path: Path, factory: RecordingFactory) -> RecordingToolServer:
    server = RecordingToolServer()
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, factory),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    return server


def payload(body: object) -> dict[str, Any]:
    return cast(dict[str, Any], cast(dict[str, Any], body)["payload"])


# Registration -----------------------------------------------------------------------------------


def test_nineteen_tools_are_registered_with_the_five_new_ones(tmp_path: Path) -> None:
    server = registered(tmp_path, CurationFactory())

    assert len(server.tools) == 19
    assert set(NEW_TOOLS) <= set(server.tools)
    assert all(server.structured_output[name] is True for name in NEW_TOOLS)


# Spec 2026-11-05 §4.4.4, §4.4.5, §4.4.13: (required inputs, optional inputs with their defaults).
NEW_TOOL_INPUTS: dict[str, tuple[tuple[str, ...], dict[str, object]]] = {
    "list_memory_candidates": ((), {"cwd": None, "kinds": None, "limit": 20}),
    "mark_candidates_reviewed": (("keys",), {"cwd": None}),
    "import_auto_memory": (("note",), {"cwd": None, "vault": None, "candidate_key": None}),
    "supersede_claim": (
        ("path", "claim", "new_claim", "evidence", "basis"),
        {"cwd": None, "vault": None, "candidate_key": None},
    ),
    "restore_memory": (("path", "reason", "basis"), {"cwd": None, "vault": None, "candidate_key": None}),
}


def test_new_tool_input_schemas_follow_the_spec_signatures(tmp_path: Path) -> None:
    import asyncio

    from mcp.server.fastmcp import FastMCP

    server = FastMCP("schema-check")
    register_mcp_tools(
        server,
        services=fake_services(tmp_path),
        service_factory=cast(Any, CurationFactory()),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    for name, (required, optional) in NEW_TOOL_INPUTS.items():
        schema = tools[name].inputSchema
        assert schema.get("required", []) == list(required), name
        assert set(schema["properties"]) == set(required) | set(optional), name
        assert {field: schema["properties"][field]["default"] for field in optional} == optional, name
    kinds = tools["list_memory_candidates"].inputSchema["properties"]["kinds"]
    assert kinds["anyOf"][0]["items"]["enum"] == ["l1_note", "session_exchange", "merge", "retire"]


# list_memory_candidates -------------------------------------------------------------------------


def test_list_memory_candidates_returns_keys_locations_and_comparison_material(tmp_path: Path) -> None:
    factory = CurationFactory()
    server = registered(tmp_path, factory)

    body = cast(
        dict[str, Any], server.tools["list_memory_candidates"](cwd="/repo", kinds=["session_exchange"], limit=5)
    )

    assert factory.package_calls == [{"cwd": Path("/repo"), "kinds": ("session_exchange",), "limit": 5}]
    assert body["tool_name"] == "list_memory_candidates"
    result = payload(body)
    assert result["project_id"] == "demo"
    assert result["reason"] is None
    first, second = result["candidates"]
    assert first["key"] == KEY
    assert first["kind"] == "session_exchange"
    assert first["location"] == LOCATION
    assert first["signal"] == "correction"
    assert first["started_at"] == "2026-11-01T10:00:00+00:00"
    assert first["comparison"] == [
        {
            "vault_id": "demo-vault",
            "path": "wiki/concepts/old-parser.md",
            "title": "옛 파서",
            "status": "retired",
            "superseded_by": None,
            "retired_reason": "파서를 바꿈",
            "evidence_date": "2026-10-01",
            "label": "폐기됨: 파서를 바꿈",
        },
        {
            "vault_id": "demo-vault",
            "path": "wiki/decisions/parser.md",
            "title": "파서 선택",
            "status": "active",
            "superseded_by": "wiki/decisions/parser-v2.md",
            "retired_reason": None,
            "evidence_date": None,
            "label": None,
        },
    ]
    assert second["key"] == "retire:wiki/concepts/quiet.md"
    assert second["retire_signals"] == ["unused"]
    assert second["reasons"] == ["90일 동안 회상에 주입만 되고 열리지 않음"]
    assert [warning["message"] for warning in body["warnings"]] == list(PACKAGE.warnings)


def test_list_memory_candidates_defaults_and_empty_bundle_reason(tmp_path: Path) -> None:
    factory = CurationFactory(MemoryCandidatePackage(None, (), reason="프로젝트를 찾지 못함"))
    server = registered(tmp_path, factory)

    result = payload(server.tools["list_memory_candidates"]())

    # Without cwd the server working folder picks the project, like the other tools.
    assert factory.package_calls == [{"cwd": Path.cwd(), "kinds": None, "limit": 20}]
    assert result == {"project_id": None, "candidates": [], "reason": "프로젝트를 찾지 못함"}


def test_every_list_call_starts_a_new_cleanup(tmp_path: Path) -> None:
    factory = CurationFactory()
    server = registered(tmp_path, factory)

    server.tools["list_memory_candidates"]()
    server.tools["list_memory_candidates"]()

    assert factory.curation_starts == 2


@pytest.mark.parametrize(
    "arguments",
    [
        {"kinds": ["brief"]},
        {"kinds": "session_exchange"},
        {"limit": 0},
        {"limit": 51},
        {"cwd": ""},
    ],
)
def test_list_memory_candidates_rejects_bad_arguments(tmp_path: Path, arguments: dict[str, object]) -> None:
    factory = CurationFactory()
    server = registered(tmp_path, factory)

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools["list_memory_candidates"](**arguments)

    assert exc_info.value.payload.code == "invalid_tool_arguments"
    assert factory.package_calls == []


# mark_candidates_reviewed -----------------------------------------------------------------------


def test_mark_candidates_reviewed_appends_skipped_records(tmp_path: Path) -> None:
    factory = CurationFactory()
    server = registered(tmp_path, factory)

    body = cast(dict[str, Any], server.tools["mark_candidates_reviewed"](keys=[KEY, " l1:abc "], cwd="/repo"))

    assert factory.reviewed_log.records == [((KEY, "l1:abc"), "skipped")]
    assert body["tool_name"] == "mark_candidates_reviewed"
    assert payload(body) == {"recorded": [KEY, "l1:abc"], "outcome": "skipped"}


@pytest.mark.parametrize("keys", [[], [""], ["a\nb"], "session:x", [1]])
def test_mark_candidates_reviewed_rejects_bad_keys(tmp_path: Path, keys: object) -> None:
    factory = CurationFactory()
    server = registered(tmp_path, factory)

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools["mark_candidates_reviewed"](keys=keys)

    assert exc_info.value.payload.code == "invalid_tool_arguments"
    assert factory.reviewed_log.records == []


def test_mark_candidates_reviewed_writes_only_the_graph_home_review_log(tmp_path: Path) -> None:
    graph_home = tmp_path / "state"
    graph_home.mkdir()
    registry = McpToolRegistry(
        services=cast(Any, None),
        service_factory=McpServiceFactory(graph_home_path=graph_home, vault_map_path=tmp_path / "none.json"),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    from vault_graph.interface.mcp.mcp_tools import parse_mark_candidates_reviewed_input

    registry.mark_candidates_reviewed(parse_mark_candidates_reviewed_input(keys=["retire:wiki/a.md"]))

    files = sorted(path.relative_to(graph_home).as_posix() for path in graph_home.rglob("*") if path.is_file())
    assert files == ["memory/reviewed.jsonl"]
    record = json.loads((graph_home / "memory" / "reviewed.jsonl").read_text(encoding="utf-8"))
    assert record["candidate_key"] == "retire:wiki/a.md"
    assert record["outcome"] == "skipped"


# Write tools ------------------------------------------------------------------------------------

PUBLISHED = MemoryWriteResult("published", "main", ("wiki/systems/a.md",), ("ok",), vault_role="project")


def write_server(tmp_path: Path, result: MemoryWriteResult = PUBLISHED) -> tuple[RecordingToolServer, Any]:
    factory = CurationFactory()
    factory.memory_write_service = RecordingWriteService(result)
    return registered(tmp_path, factory), factory.memory_write_service


def test_supersede_claim_tool_passes_fields_and_candidate_key(tmp_path: Path) -> None:
    server, service = write_server(tmp_path)

    body = server.tools["supersede_claim"](
        path="wiki/systems/a.md",
        claim="Old claim",
        new_claim="New claim",
        evidence=LOCATION,
        basis="stated",
        cwd="/repo",
        vault="main",
        candidate_key=KEY,
    )

    assert service.requests == [
        SupersedeClaimRequest(
            path="wiki/systems/a.md",
            claim="Old claim",
            new_claim="New claim",
            evidence=LOCATION,
            basis="stated",
            vault="main",
            cwd="/repo",
            candidate_key=KEY,
        )
    ]
    assert cast(dict[str, Any], body)["tool_name"] == "supersede_claim"
    assert payload(body)["status"] == "published"


def test_restore_memory_tool_passes_fields_and_candidate_key(tmp_path: Path) -> None:
    server, service = write_server(tmp_path)

    body = server.tools["restore_memory"](
        path="wiki/decisions/a.md", reason="True again", basis="inferred", candidate_key="retire:wiki/decisions/a.md"
    )

    assert service.requests == [
        RestoreRequest(
            path="wiki/decisions/a.md",
            reason="True again",
            basis="inferred",
            cwd=str(Path.cwd()),
            candidate_key="retire:wiki/decisions/a.md",
        )
    ]
    assert cast(dict[str, Any], body)["tool_name"] == "restore_memory"


def test_import_auto_memory_tool_returns_the_raw_copy_and_source_page(tmp_path: Path) -> None:
    imported = MemoryWriteResult(
        "published",
        "main",
        ("raw/imports/claude-memory/feedback_a.md", "wiki/sources/feedback-a.md"),
        ("Imported.",),
        vault_role="project",
        raw_path="raw/imports/claude-memory/feedback_a.md",
        source_page="wiki/sources/feedback-a.md",
    )
    server, service = write_server(tmp_path, imported)

    body = server.tools["import_auto_memory"](note="/claude/memory/feedback_a.md", vault="main", candidate_key="l1:abc")

    assert service.requests == [
        ImportRequest(note="/claude/memory/feedback_a.md", cwd=str(Path.cwd()), vault="main", candidate_key="l1:abc")
    ]
    result = payload(body)
    assert result["raw_path"] == "raw/imports/claude-memory/feedback_a.md"
    assert result["source_page"] == "wiki/sources/feedback-a.md"


def test_existing_write_tools_pass_candidate_key(tmp_path: Path) -> None:
    server, service = write_server(tmp_path)

    server.tools["remember"](
        title="A", kind="decision", body="B", evidence=["E"], basis="stated", vault="main", candidate_key=KEY
    )
    server.tools["update_memory"](
        path="wiki/decisions/a.md", body="B", evidence=["E"], basis="stated", candidate_key=KEY
    )
    server.tools["retire_memory"](path="wiki/decisions/a.md", reason="Old", basis="stated", candidate_key=KEY)

    first, second, third = service.requests
    assert isinstance(first, RememberRequest) and first.candidate_key == KEY
    assert isinstance(second, UpdateRequest) and second.candidate_key == KEY
    assert isinstance(third, RetireRequest) and third.candidate_key == KEY


def test_write_payload_has_no_import_fields_when_not_set(tmp_path: Path) -> None:
    server, _ = write_server(tmp_path)

    result = payload(server.tools["remember"](title="A", kind="decision", body="B", evidence=["E"], basis="stated"))

    assert "raw_path" not in result
    assert "source_page" not in result


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("supersede_claim", {"path": "p", "claim": "c", "new_claim": "n", "evidence": ["e"], "basis": "stated"}),
        ("restore_memory", {"path": "p", "reason": 3, "basis": "stated"}),
        ("import_auto_memory", {"note": None}),
        (
            "remember",
            {"title": "A", "kind": "decision", "body": "B", "evidence": ["E"], "basis": "stated", "candidate_key": 1},
        ),
    ],
)
def test_write_tools_check_argument_types(tmp_path: Path, tool: str, arguments: dict[str, object]) -> None:
    server, service = write_server(tmp_path)

    with pytest.raises(McpProtocolError) as exc_info:
        server.tools[tool](**arguments)

    assert exc_info.value.payload.code == "invalid_tool_arguments"
    assert service.requests == []


# One cleanup through the real composition ------------------------------------------------------


@pytest.fixture
def composed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[McpToolRegistry, Path, list[str], Path]:
    vault = tmp_path / "vault"
    (vault / "wiki" / "decisions").mkdir(parents=True)
    (vault / "wiki" / "decisions" / "use-sqlite.md").write_text(PAGE, encoding="utf-8")
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"main": {"path": str(vault), "role": "project"}}, "projects": {}}),
        encoding="utf-8",
    )
    graph_home = tmp_path / "state"
    graph_home.mkdir()
    proposals: list[str] = []

    def stand_in_propose(
        self: VaultPublishCli, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float
    ) -> WriteOutcome:
        proposals.append(summary)
        return WriteOutcome(status="proposed", review_path=f"scratch/review/memory-{len(proposals):04d}.md")

    def stand_in_import(self: VaultImportCli, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
        return WriteOutcome(
            status="published",
            written_paths=("raw/imports/claude-memory/note.md",),
            raw_path="raw/imports/claude-memory/note.md",
            source_page="wiki/sources/note.md",
        )

    monkeypatch.setattr(VaultPublishCli, "propose", stand_in_propose)
    monkeypatch.setattr(VaultImportCli, "import_source", stand_in_import)
    registry = McpToolRegistry(
        services=cast(Any, None),
        service_factory=McpServiceFactory(graph_home_path=graph_home, vault_map_path=vault_map),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    return registry, vault, proposals, graph_home


def _inferred(registry: McpToolRegistry, index: int, *, candidate_key: str | None = None) -> str:
    body = registry.remember(
        RememberInput(
            title=f"Inferred fact {index}",
            kind="decision",
            body="B",
            evidence=("E",),
            basis="inferred",
            vault="main",
            candidate_key=candidate_key,
        )
    )
    return cast(str, body.payload["status"])


def test_eleventh_inferred_proposal_of_one_cleanup_is_rejected_until_the_next_list_call(
    composed: tuple[McpToolRegistry, Path, list[str], Path],
) -> None:
    registry, vault, proposals, _ = composed
    before = sha256_by_file(vault)

    registry.list_memory_candidates(ListMemoryCandidatesInput())
    statuses = [_inferred(registry, index) for index in range(INFERRED_PROPOSAL_LIMIT + 1)]
    eleventh = registry.remember(
        RememberInput(title="One more", kind="decision", body="B", evidence=("E",), basis="inferred", vault="main")
    )
    registry.list_memory_candidates(ListMemoryCandidatesInput())
    after_next_list = _inferred(registry, 99)

    assert statuses == ["proposed"] * INFERRED_PROPOSAL_LIMIT + ["rejected"]
    assert eleventh.payload["status"] == "rejected"
    assert PROPOSAL_LIMIT_MESSAGE in cast(list[str], eleventh.payload["messages"])
    assert after_next_list == "proposed"
    assert len(proposals) == INFERRED_PROPOSAL_LIMIT + 1
    assert sha256_by_file(vault) == before


def test_write_with_candidate_key_is_recorded_only_when_proposed_or_published(
    composed: tuple[McpToolRegistry, Path, list[str], Path], tmp_path: Path
) -> None:
    registry, vault, _, graph_home = composed
    note = tmp_path / "l1" / "note.md"
    note.parent.mkdir()
    note.write_text("note\n", encoding="utf-8")
    from vault_graph.interface.mcp.mcp_memory_tools import ImportAutoMemoryInput, RestoreMemoryInput

    proposed = _inferred(registry, 1, candidate_key="session:proposed")
    rejected = registry.restore_memory(
        RestoreMemoryInput(
            path="wiki/decisions/use-sqlite.md", reason="r", basis="stated", vault="main", candidate_key="retire:x"
        )
    )
    imported = registry.import_auto_memory(ImportAutoMemoryInput(note=str(note), vault="main", candidate_key="l1:note"))

    assert proposed == "proposed"
    assert rejected.payload["status"] == "rejected"  # the page is not retired
    assert imported.payload["status"] == "published"
    assert imported.payload["raw_path"] == "raw/imports/claude-memory/note.md"
    records = [
        json.loads(line) for line in (graph_home / "memory" / "reviewed.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [(record["candidate_key"], record["outcome"]) for record in records] == [
        ("session:proposed", "proposed"),
        ("l1:note", "published"),
    ]
    assert note.read_text(encoding="utf-8") == "note\n"
