from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import anyio
import pytest
from typer.testing import CliRunner

from tests.test_context_pack_contract import make_pack
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app
from vault_graph.context import DefaultContextPackRenderer
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, RegisteredMcpServer, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()

EXPECTED_RESOURCE_TEMPLATES = {
    "vault://{vault_id}/documents/{path}",
    "vault://{vault_id}/pages/{path}",
    "vault://{vault_id}/sources/{id}",
    "vault://{vault_id}/concepts/{name}",
    "vault://{vault_id}/decisions/{id}",
    "vault://{vault_id}/issues/{id}",
    "vault://{vault_id}/timeline/recent",
    "vault://{vault_id}/context/current",
    "vault://{vault_id}/graph/entities/{id}",
    "vault://context/packs/{pack_id}",
}


def initialized_state(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(
        app,
        ["init", "--vault", str(vault_root), "--state", str(state_path)]
    ).exit_code == 0
    return state_path


def initialized_registered_server(tmp_path: Path) -> RegisteredMcpServer:
    return create_mcp_server(McpServerConfig(state_path=initialized_state(tmp_path)))


def initialized_multi_vault_registered_server(tmp_path: Path) -> RegisteredMcpServer:
    main = tmp_path / "main"
    work = tmp_path / "work"
    main.mkdir()
    work.mkdir()
    state_path = tmp_path / "state"
    service = CatalogService(state_path=state_path)
    service.save_catalog(
        VaultCatalog.from_entries(
            entries=(
                VaultCatalogEntry.from_root(vault_id="main", root_path=main, display_name="Main"),
                VaultCatalogEntry.from_root(vault_id="work", root_path=work, display_name="Work"),
            ),
            active_vault_id="main",
        )
    )
    return create_mcp_server(McpServerConfig(state_path=state_path))


def test_create_mcp_server_exposes_resource_cache_and_registry(tmp_path: Path) -> None:
    registered = initialized_registered_server(tmp_path)

    assert registered.context_pack_cache.max_entries == 32
    assert registered.resource_registry is not None


def test_server_lists_exact_phase_5b_resource_templates(tmp_path: Path) -> None:
    registered = initialized_registered_server(tmp_path)

    async def run() -> None:
        templates = await registered.server.list_resource_templates()
        assert {str(template.uriTemplate) for template in templates} == EXPECTED_RESOURCE_TEMPLATES
        assert {template.mimeType for template in templates} == {"application/json"}
        assert await registered.server.list_resources() == []

    anyio.run(run)


def test_registry_reads_context_pack_cache_as_json_envelope(tmp_path: Path) -> None:
    registered = initialized_registered_server(tmp_path)
    pack = replace(make_pack(), pack_id="pack-1")
    rendered_json = DefaultContextPackRenderer().render_json(pack)
    registered.context_pack_cache.put(pack, rendered_json=rendered_json)

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://context/packs/pack-1"))

    assert body.uri == "vault://context/packs/pack-1"
    assert body.content_mime_type == "application/json"
    assert body.text == rendered_json
    assert body.metadata["pack_id"] == "pack-1"
    assert body.metadata["requested_scope_key"] == "main:wiki,docs:cross=False"
    assert body.warnings == ()


def test_server_reads_context_pack_resource_with_public_fastmcp_api(tmp_path: Path) -> None:
    registered = initialized_registered_server(tmp_path)
    pack = replace(make_pack(), pack_id="pack-1")
    registered.context_pack_cache.put(pack, rendered_json=DefaultContextPackRenderer().render_json(pack))

    async def run() -> None:
        contents = list(await registered.server.read_resource("vault://context/packs/pack-1"))
        assert len(contents) == 1
        envelope = json.loads(contents[0].content)
        assert envelope["uri"] == "vault://context/packs/pack-1"
        assert envelope["content_mime_type"] == "application/json"
        assert envelope["metadata"]["pack_id"] == "pack-1"
        assert contents[0].mime_type == "application/json"

    anyio.run(run)


def test_server_reads_encoded_document_resource_with_public_fastmcp_api(tmp_path: Path) -> None:
    state_path = initialized_state(tmp_path)
    document = make_document("default", "wiki/page.md", "hash")
    chunk = make_chunk("default", document.document_id, document.path, chunk_id="chunk-1", text="Indexed body")
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[chunk], tombstones=[])
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    async def run() -> None:
        contents = list(await registered.server.read_resource("vault://default/documents/wiki%2Fpage.md"))
        assert len(contents) == 1
        envelope = json.loads(contents[0].content)
        assert envelope["uri"] == "vault://default/documents/wiki%2Fpage.md"
        assert envelope["content_mime_type"] == "text/markdown"
        assert envelope["text"] == "Indexed body"
        assert envelope["metadata"]["document_id"] == document.document_id

    anyio.run(run)


def test_missing_context_pack_resource_raises_not_found(tmp_path: Path) -> None:
    registered = initialized_registered_server(tmp_path)

    with pytest.raises(McpProtocolError) as exc_info:
        registered.resource_registry.read(McpResourceRequest(uri="vault://context/packs/missing"))

    assert exc_info.value.kind == "not_found"
    assert exc_info.value.payload.code == "resource_not_found"


def test_current_context_resource_is_per_vault_not_all_vault_summary(tmp_path: Path) -> None:
    registered = initialized_multi_vault_registered_server(tmp_path)

    main = registered.resource_registry.read(McpResourceRequest(uri="vault://main/context/current"))
    work = registered.resource_registry.read(McpResourceRequest(uri="vault://work/context/current"))

    assert main.metadata["vault_id"] == "main"
    assert main.metadata["display_name"] == "Main"
    assert main.metadata["active"] is True
    assert work.metadata["vault_id"] == "work"
    assert work.metadata["display_name"] == "Work"
    assert work.metadata["active"] is False
    assert "recent decisions" not in main.text.casefold()
