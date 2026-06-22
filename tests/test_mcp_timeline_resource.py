from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_sqlite_metadata_store import make_document
from vault_graph.cli.main import app
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


def test_timeline_recent_resource_returns_single_vault_json(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    document = make_document("default", "wiki/page.md", "hash")
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=[document], chunks=[], tombstones=[])
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert body.content_mime_type == "application/json"
    assert body.metadata["requested_scope"]["vault_ids"] == ["default"]  # type: ignore[index]
    assert body.metadata["limit"] == 20
    assert body.metadata["vaults"][0]["vault_id"] == "default"  # type: ignore[index]
    assert json.loads(body.text) == body.metadata


def test_timeline_recent_resource_maps_metadata_errors_to_vault_scoped_mcp_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError) as exc_info:
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/timeline/recent"))

    assert exc_info.value.payload.code == "metadata_unavailable"
    assert exc_info.value.payload.affected_vault_ids == ("default",)
    assert exc_info.value.payload.recovery_hint == "Run vg index, then vg status for the selected Vault."
