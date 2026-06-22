from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_read_only_boundary import file_bytes
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


def initialized_state(tmp_path: Path, vault_root: Path) -> Path:
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    return state_path


def seed_metadata(state_path: Path) -> None:
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path, chunk_id="chunk-1", text="Indexed body")
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])


def test_successful_document_resource_read_does_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_metadata(state_path)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki%2Fpage.md"))

    assert body.text == "Indexed body"
    assert file_bytes(vault_root) == before


def test_missing_document_resource_read_does_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_metadata(state_path)
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError):
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki%2Fmissing.md"))

    assert file_bytes(vault_root) == before


def test_invalid_uri_fails_before_metadata_store_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    def fail_lookup(*args: object, **kwargs: object) -> object:
        raise AssertionError("metadata lookup should not happen")

    monkeypatch.setattr(registered.services.metadata_store, "document_state", fail_lookup)

    with pytest.raises(McpProtocolError) as exc_info:
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki/page.md"))

    assert exc_info.value.payload.code == "invalid_resource_uri"


def test_resource_reads_do_not_create_missing_derived_state_directories(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    for uri in ("vault://context/packs/missing", "vault://default/documents/wiki/page.md"):
        with pytest.raises(McpProtocolError):
            registered.resource_registry.read(McpResourceRequest(uri=uri))

    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_resource_reads_do_not_call_vault_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_metadata(state_path)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    def fail_load_documents(*args: object, **kwargs: object) -> object:
        raise AssertionError("VaultLoader must not be called by MCP resource reads")

    monkeypatch.setattr("vault_graph.ingestion.vault_loader.VaultLoader.load_documents", fail_load_documents)

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/documents/wiki%2Fpage.md"))

    assert body.text == "Indexed body"


def test_timeline_recent_resource_does_not_mutate_vault_or_create_memory_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nVault body\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_metadata(state_path)
    before = file_bytes(vault_root)
    missing_status_paths = (
        state_path / "vector" / "status.json",
        state_path / "graph" / "status.json",
    )
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert file_bytes(vault_root) == before
    assert not (state_path / "memory").exists()
    assert not (state_path / "data" / "memory").exists()
    assert all(not path.exists() for path in missing_status_paths)
