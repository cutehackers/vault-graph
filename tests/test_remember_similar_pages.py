"""``remember`` lists similar existing pages and takes ``summary`` and ``aliases`` at the MCP tool.

Source: backlog MEMORY-01 (``remember`` lists up to 3 similar existing pages, retired ones with their
status, and never blocks the write) and spec 2026-11-11 §4.3.1, A-9. The Vault, the Graph Home and the
vault map are temporary folders. A stand-in writer plays publish-draft.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_mcp_tools import RecordingToolServer
from tests.test_memory_write_service import TODAY, RecordingWriter
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.temporary_draft_files import TemporaryDraftFiles
from vault_graph.interface.composition.adapters.vault_page_reader import VaultPageFileReader
from vault_graph.interface.composition.memory_candidate_sources import ProjectSimilarPages
from vault_graph.interface.mcp.mcp_errors import McpProtocolError
from vault_graph.interface.mcp.mcp_memory_tools import (
    parse_remember_input,
    parse_update_memory_input,
    register_memory_tools,
)
from vault_graph.interface.mcp.mcp_tool_serialization import memory_write_result_to_payload
from vault_graph.operation.integration.vault_map import open_vault_map
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import MemoryWriteResult, RememberRequest, SimilarMemoryPage
from vault_graph.operation.memory.memory_write_service import (
    NO_SUMMARY_WARNING,
    SIMILAR_PAGES_MESSAGE,
    MemoryWriteService,
)

runner = CliRunner()
TITLE = "파서 선택"
BODY = "tree-sitter 파서를 쓴다. 정규식 파서는 쓰지 않는다."
RETIRED_PAGE = (
    "---\ntitle: 옛 파서 선택\ntype: decision\nstatus: retired\nretired_reason: 파서를 바꿈\n---\n"
    "# 옛 파서 선택\n\ntree-sitter 파서를 쓴다. 정규식 파서는 쓰지 않는다.\n"
)


class PagePublishingWriter(RecordingWriter):
    """Stands in for publish-draft: writes the draft's title, type, status and body as the target page."""

    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        super().publish(vault_root, draft_path, timeout_s=timeout_s)
        draft = self.drafts[-1]
        frontmatter = cast(dict[str, Any], draft["frontmatter"])
        target = vault_root / str(draft["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        head = "".join(f"{name}: {frontmatter[name]}\n" for name in ("title", "type", "status"))
        target.write_text(f"---\n{head}---\n{draft['body']}", encoding="utf-8")
        return WriteOutcome(status="published", written_paths=(str(draft["path"]),))


class _Project:
    def __init__(self, tmp_path: Path) -> None:
        self.repo = tmp_path / "repo"
        self.repo.mkdir()
        # The vault map finds a project by its git repository root.
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        self.vault = tmp_path / "vault"
        (self.vault / "wiki" / "decisions").mkdir(parents=True)
        (self.vault / "wiki" / "decisions" / "old-parser.md").write_text(RETIRED_PAGE, encoding="utf-8")
        self.map_file = tmp_path / "vault-map.json"
        self.map_file.write_text(
            json.dumps(
                {
                    "version": 2,
                    "vaults": {"demo-vault": {"path": str(self.vault), "role": "project"}},
                    "projects": {"demo": {"root": str(self.repo), "vaults": ["demo-vault"]}},
                }
            ),
            encoding="utf-8",
        )
        self.graph_home = tmp_path / "state"
        self.writer = PagePublishingWriter()
        temp_root = tmp_path / "os-temp"
        temp_root.mkdir()
        self.service = MemoryWriteService(
            vault_map=open_vault_map(self.map_file).vault_map,
            writer=self.writer,
            page_reader=VaultPageFileReader(),
            today=lambda: TODAY,
            drafts=TemporaryDraftFiles(temp_root=temp_root),
            similar_pages=ProjectSimilarPages(graph_home=self.graph_home, vault_map_file=self.map_file),
        )

    def vg(self, *command: str) -> None:
        result = runner.invoke(app, [*command, "--graph-home", str(self.graph_home)])
        assert result.exit_code == 0, (command, result.output)

    def remember(self, **overrides: object) -> MemoryWriteResult:
        values: dict[str, object] = {
            "title": TITLE,
            "kind": "decision",
            "body": BODY,
            "evidence": ("사용자가 2026-11-12 세션에서 말함.",),
            "basis": "stated",
            "cwd": str(self.repo),
            "vault": "demo-vault",
            "summary": "파서는 tree-sitter로 정했다.",
        }
        values.update(overrides)
        return self.service.remember(RememberRequest(**values))  # type: ignore[arg-type]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: MonkeyPatch) -> _Project:
    from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
    from tests.test_vector_indexer import SPEC

    def embeddings(*_: object, **__: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _ConfiguredDeterministicTextEmbeddings(SPEC)

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", embeddings)
    monkeypatch.setattr("vault_graph.interface.composition.adapters.text_embeddings.text_embeddings_for", embeddings)
    built = _Project(tmp_path)
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(built.map_file))
    return built


def test_second_remember_of_the_same_title_and_body_returns_the_first_page_as_similar(project: _Project) -> None:
    project.vg("init", "--vault-id", "demo-vault", "--vault", str(project.vault))

    first = project.remember()

    assert first.status == "published"
    assert first.written_paths == ("wiki/decisions/파서-선택.md",)
    # No index yet: the write succeeds with no similar pages listed.
    assert first.similar_pages == ()
    assert SIMILAR_PAGES_MESSAGE not in first.messages

    project.vg("index")
    second = project.remember()

    listed = {page.path: page for page in second.similar_pages}
    assert "wiki/decisions/파서-선택.md" in listed
    assert listed["wiki/decisions/파서-선택.md"].status == "active"
    # A retired page is listed with its status and reason.
    assert listed["wiki/decisions/old-parser.md"].status == "retired"
    assert listed["wiki/decisions/old-parser.md"].retired_reason == "파서를 바꿈"
    assert len(second.similar_pages) <= 3
    assert SIMILAR_PAGES_MESSAGE in second.messages
    # The same title is the same page path, which remember refuses for its own reason. The list did not cause it.
    assert second.status == "rejected"
    assert any("already exists" in message for message in second.messages)


def test_similar_pages_never_block_a_new_page(project: _Project) -> None:
    project.vg("init", "--vault-id", "demo-vault", "--vault", str(project.vault))
    project.remember()
    project.vg("index")

    again = project.remember(title="파서 선택 다시")

    assert again.status == "published"
    assert "wiki/decisions/파서-선택.md" in {page.path for page in again.similar_pages}
    assert len(project.writer.calls) == 2


def test_remember_without_a_graph_home_publishes_with_no_similar_pages(project: _Project) -> None:
    result = project.remember()

    assert result.status == "published"
    assert result.similar_pages == ()
    assert not project.graph_home.exists()


def test_remember_outside_a_map_project_lists_no_similar_pages(project: _Project, tmp_path: Path) -> None:
    project.vg("init", "--vault-id", "demo-vault", "--vault", str(project.vault))
    project.vg("index")
    lookup = ProjectSimilarPages(graph_home=project.graph_home, vault_map_file=project.map_file)

    assert lookup.find(tmp_path / "elsewhere", f"{TITLE}\n\n{BODY}", limit=3) == ()
    assert lookup.find(None, f"{TITLE}\n\n{BODY}", limit=3) == ()


# MCP tool arguments, payload and guidance


def test_parse_remember_and_update_inputs_take_summary_and_aliases() -> None:
    remembered = parse_remember_input(
        title="Use SQLite",
        kind="decision",
        body="Body.",
        evidence=["e"],
        basis="stated",
        summary="색인은 SQLite에 둔다.",
        aliases=["SQLite 색인", "sqlite index"],
    )
    assert (remembered.summary, remembered.aliases) == ("색인은 SQLite에 둔다.", ("SQLite 색인", "sqlite index"))
    assert parse_remember_input(title="t", kind="decision", body="b", evidence=["e"], basis="stated").aliases == ()

    kept = parse_update_memory_input(path="wiki/decisions/a.md", body="b", evidence=["e"], basis="stated")
    assert (kept.summary, kept.aliases) == (None, None)
    cleared = parse_update_memory_input(
        path="wiki/decisions/a.md", body="b", evidence=["e"], basis="stated", aliases=[]
    )
    assert cleared.aliases == ()


@pytest.mark.parametrize("bad", [{"summary": 3}, {"aliases": "one"}, {"aliases": ["ok", 3]}])
def test_wrong_summary_or_aliases_types_are_invalid_arguments(bad: dict[str, Any]) -> None:
    with pytest.raises(McpProtocolError):
        parse_remember_input(title="t", kind="decision", body="b", evidence=["e"], basis="stated", **bad)
    with pytest.raises(McpProtocolError):
        parse_update_memory_input(path="wiki/decisions/a.md", body="b", evidence=["e"], basis="stated", **bad)


def test_payload_has_warnings_and_similar_pages_only_when_set() -> None:
    plain = memory_write_result_to_payload(MemoryWriteResult("published", "main", ("wiki/decisions/a.md",), ()))
    assert "warnings" not in plain and "similar_pages" not in plain

    page = SimilarMemoryPage(
        vault_id="demo-vault", path="wiki/decisions/old.md", title="Old", status="retired", retired_reason="replaced"
    )
    payload = memory_write_result_to_payload(
        MemoryWriteResult(
            "published", "main", ("wiki/decisions/a.md",), (), warnings=(NO_SUMMARY_WARNING,), similar_pages=(page,)
        )
    )
    assert payload["warnings"] == [NO_SUMMARY_WARNING]
    assert payload["similar_pages"] == [
        {
            "vault_id": "demo-vault",
            "path": "wiki/decisions/old.md",
            "title": "Old",
            "status": "retired",
            "superseded_by": None,
            "retired_reason": "replaced",
        }
    ]


def test_tool_descriptions_ask_for_summary_and_aliases_in_the_users_language() -> None:
    server = RecordingToolServer()
    register_memory_tools(server, cast(Any, object()))

    for name in ("remember", "update_memory"):
        description = server.tools[name].__doc__ or ""
        assert "``summary``" in description and "``aliases``" in description
        assert "language the user asks in" in description
        assert "Korean" in description
        assert "never makes them up" in description
    remember = server.tools["remember"].__doc__ or ""
    assert "similar_pages" in remember and "retire_memory(replaced_by=...)" in remember
