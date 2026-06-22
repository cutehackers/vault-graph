from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from tests.test_mcp_tool_serialization import make_pack_with_item, make_search_response
from tests.test_read_only_boundary import file_bytes
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.mcp.mcp_tools import (
    BuildContextPackInput,
    CheckIndexStatusInput,
    ExplainResultInput,
    GetOpenQuestionsInput,
    GetRecentChangesInput,
    SearchVaultInput,
    SummarizeProjectMemoryInput,
)
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


def initialized_state(tmp_path: Path, vault_root: Path) -> Path:
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    return state_path


def seed_search_indexes(state_path: Path) -> None:
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path, chunk_id="chunk-1", text="Indexed body")
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])


def test_invalid_tool_arguments_do_not_create_missing_state_or_open_graph(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError):
        registered.tool_registry.search_vault(SearchVaultInput(query="", include_graph=True))

    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_successful_context_pack_tool_does_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_search_indexes(state_path)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    try:
        registered.tool_registry.build_context_pack(BuildContextPackInput(goal="Build MCP context"))
    except McpProtocolError:
        pass

    assert file_bytes(vault_root) == before


def test_search_then_explain_result_does_not_mutate_vault_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    monkeypatch.setattr(registered.services.retrieval_service, "search", lambda **_: make_search_response())

    search_body = registered.tool_registry.search_vault(SearchVaultInput(query="GraphRAG"))
    result = cast(list[dict[str, object]], search_body.payload["results"])[0]
    registered.tool_registry.explain_result(ExplainResultInput(result_id=cast(str, result["result_id"])))

    assert file_bytes(vault_root) == before


def test_context_pack_then_explain_result_does_not_mutate_vault_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))
    pack = replace(make_pack_with_item(), pack_id="pack-1")

    monkeypatch.setattr(registered.services.context_pack_builder, "build", lambda _: pack)

    registered.tool_registry.build_context_pack(BuildContextPackInput(goal="Build MCP context"))
    registered.tool_registry.explain_result(ExplainResultInput(result_id="item-1"))

    assert file_bytes(vault_root) == before


def test_explain_result_cache_miss_does_not_create_state_paths(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError):
        registered.tool_registry.explain_result(ExplainResultInput(result_id="missing"))

    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_memory_tools_do_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "docs").mkdir(parents=True)
    (vault_root / "docs" / "status.md").write_text("# Status\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_search_indexes(state_path)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.tool_registry.summarize_project_memory(SummarizeProjectMemoryInput())
    registered.tool_registry.get_open_questions(GetOpenQuestionsInput())

    assert file_bytes(vault_root) == before


def test_memory_tool_metadata_error_does_not_create_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError):
        registered.tool_registry.summarize_project_memory(SummarizeProjectMemoryInput())

    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()


def test_get_recent_changes_does_not_mutate_vault_or_create_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_search_indexes(state_path)
    before = file_bytes(vault_root)
    missing_status_paths = (
        state_path / "vector" / "status.json",
        state_path / "graph" / "status.json",
    )
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.tool_registry.get_recent_changes(GetRecentChangesInput())

    assert file_bytes(vault_root) == before
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
    assert all(not path.exists() for path in missing_status_paths)


def test_check_index_status_health_explorer_does_not_create_status_or_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.tool_registry.check_index_status(CheckIndexStatusInput())

    assert not (state_path / "vector" / "status.json").exists()
    assert not (state_path / "graph" / "status.json").exists()
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
