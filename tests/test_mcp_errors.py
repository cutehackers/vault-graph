from __future__ import annotations

from pathlib import Path

from vault_graph.errors import CatalogError, VectorStoreError
from vault_graph.mcp.mcp_errors import McpProtocolError, map_exception_to_mcp_error


def test_catalog_error_maps_to_invalid_parameter() -> None:
    error = map_exception_to_mcp_error(CatalogError("unknown vault_id: work"))

    assert isinstance(error, McpProtocolError)
    assert error.kind == "invalid_parameter"
    assert error.payload.code == "catalog_error"
    assert error.payload.message == "unknown vault_id: work"
    assert error.payload.severity == "error"


def test_backend_error_maps_to_execution_error() -> None:
    error = map_exception_to_mcp_error(VectorStoreError("vector search unavailable: not initialized"))

    assert error.kind == "execution"
    assert error.payload.code == "vector_store_error"
    assert error.payload.message == "vector search unavailable: not initialized"


def test_domain_error_redacts_absolute_paths(tmp_path: Path) -> None:
    vault_file = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(CatalogError(f"vault root does not exist: {vault_file}"))

    assert str(vault_file) not in error.payload.message
    assert "<redacted-path>" in error.payload.message


def test_internal_error_does_not_leak_arbitrary_absolute_path(tmp_path: Path) -> None:
    secret_path = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(RuntimeError(f"failed at {secret_path}"))

    assert error.kind == "internal"
    assert error.payload.code == "internal_error"
    assert str(secret_path) not in error.payload.message


def test_internal_error_may_include_user_state_path(tmp_path: Path) -> None:
    state_path = tmp_path / "state"
    secret_path = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(
        RuntimeError(f"failed at {state_path}; checked {secret_path}"),
        user_state_path=state_path,
    )

    assert str(state_path) in error.payload.message
    assert str(secret_path) not in error.payload.message
    assert "<redacted-path>" in error.payload.message
