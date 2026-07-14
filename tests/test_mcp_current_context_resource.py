from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

from tests.test_read_only_boundary import file_bytes
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app
from vault_graph.ingestion.vault_catalog import VaultCatalog, VaultCatalogEntry
from vault_graph.mcp.mcp_errors import McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

runner = CliRunner()


def test_current_context_resource_returns_single_vault_project_memory_projection(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    seed_project_status(state_path, vault_id="default")
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/context/current"))

    assert body.content_mime_type == "application/json"
    assert body.metadata["requested_scope"]["vault_ids"] == ["default"]  # type: ignore[index]
    assert body.metadata["vaults"][0]["vault_id"] == "default"  # type: ignore[index]
    assert "metadata_health" not in body.metadata


def test_current_context_resource_does_not_return_all_vault_summary(tmp_path: Path) -> None:
    main = tmp_path / "main"
    work = tmp_path / "work"
    main.mkdir()
    work.mkdir()
    state_path = tmp_path / "state"
    CatalogService(state_path=state_path).save_catalog(
        VaultCatalog.from_entries(
            entries=(
                VaultCatalogEntry.from_root(vault_id="main", root_path=main, display_name="Main"),
                VaultCatalogEntry.from_root(vault_id="work", root_path=work, display_name="Work"),
            ),
            active_vault_id="main",
        )
    )
    seed_project_status(state_path, vault_id="main")
    seed_project_status(state_path, vault_id="work")
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    main_body = registered.resource_registry.read(McpResourceRequest(uri="vault://main/context/current"))
    work_body = registered.resource_registry.read(McpResourceRequest(uri="vault://work/context/current"))

    assert main_body.metadata["requested_scope"]["vault_ids"] == ["main"]  # type: ignore[index]
    assert work_body.metadata["requested_scope"]["vault_ids"] == ["work"]  # type: ignore[index]
    assert len(main_body.metadata["vaults"]) == 1  # type: ignore[arg-type]
    assert len(work_body.metadata["vaults"]) == 1  # type: ignore[arg-type]


def test_current_context_resource_maps_memory_projection_error_with_recovery_hint(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    with pytest.raises(McpProtocolError) as exc_info:
        registered.resource_registry.read(McpResourceRequest(uri="vault://default/context/current"))

    assert exc_info.value.kind == "execution"
    assert exc_info.value.payload.code == "metadata_unavailable"
    assert exc_info.value.payload.affected_vault_ids == ("default",)
    assert "Run vg index" in (exc_info.value.payload.recovery_hint or "")


def test_current_context_resource_preserves_memory_warnings_in_body_and_metadata(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = initialized_state(tmp_path, vault_root)
    SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    body = registered.resource_registry.read(McpResourceRequest(uri="vault://default/context/current"))

    warning_codes = {warning.code for warning in body.warnings}
    metadata_warnings = cast(list[dict[str, object]], body.metadata["warnings"])
    metadata_codes = {warning["code"] for warning in metadata_warnings}
    assert "no_memory_items_found" in warning_codes
    assert warning_codes == metadata_codes


def test_current_context_resource_does_not_mutate_vault_bytes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "docs").mkdir(parents=True)
    (vault_root / "docs" / "status.md").write_text("# Status\nCurrent\n", encoding="utf-8")
    state_path = initialized_state(tmp_path, vault_root)
    seed_project_status(state_path, vault_id="default")
    before = file_bytes(vault_root)
    registered = create_mcp_server(McpServerConfig(state_path=state_path))

    registered.resource_registry.read(McpResourceRequest(uri="vault://default/context/current"))

    assert file_bytes(vault_root) == before


def initialized_state(tmp_path: Path, vault_root: Path) -> Path:
    state_path = tmp_path / "state"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)]).exit_code == 0
    return state_path


def seed_project_status(state_path: Path, *, vault_id: str) -> None:
    document = make_document(vault_id, "docs/status.md", f"{vault_id}-status")
    chunk = make_chunk(
        vault_id,
        document.document_id,
        document.path,
        chunk_id=f"{vault_id}-chunk",
        text="Current state",
    )
    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(
        index_revision=f"{vault_id}-metadata",
        documents=[document],
        chunks=[chunk],
        tombstones=[],
    )
