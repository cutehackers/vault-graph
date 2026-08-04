from __future__ import annotations

from pathlib import Path

from vault_graph.errors import (
    CatalogError,
    DataHomeNotInitializedError,
    LegacyDataHomeDetectedError,
    MemoryProjectionError,
    ResultExplanationError,
    VectorStoreError,
)
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


def test_data_home_errors_include_onboarding_recovery_hints() -> None:
    missing = map_exception_to_mcp_error(DataHomeNotInitializedError("data_home_not_initialized: setup required"))
    legacy = map_exception_to_mcp_error(LegacyDataHomeDetectedError("legacy_data_home_detected: old layout"))

    assert missing.payload.code == "data_home_not_initialized"
    assert "vg setup" in (missing.payload.recovery_hint or "")
    assert legacy.payload.code == "legacy_data_home_detected"
    assert "new --graph-home" in (legacy.payload.recovery_hint or "")


def test_result_explanation_not_found_maps_to_mcp_not_found() -> None:
    error = map_exception_to_mcp_error(
        ResultExplanationError("result_explanation_not_found: missing result explanation")
    )

    assert error.kind == "not_found"
    assert error.payload.code == "result_explanation_not_found"
    assert "Rerun the original MCP tool" in (error.payload.recovery_hint or "")


def test_memory_projection_error_maps_to_execution_error() -> None:
    error = map_exception_to_mcp_error(MemoryProjectionError("metadata_unavailable: not initialized"))

    assert error.kind == "execution"
    assert error.payload.code == "metadata_unavailable"


def test_invalid_memory_limit_prefix_is_preserved() -> None:
    error = map_exception_to_mcp_error(MemoryProjectionError("invalid_memory_limit: limit must be 1..50"))

    assert error.kind == "execution"
    assert error.payload.code == "invalid_memory_limit"


def test_phase_6c_memory_projection_error_prefixes_are_preserved() -> None:
    invalid_since = map_exception_to_mcp_error(MemoryProjectionError("invalid_timeline_since: bad timestamp"))
    unavailable = map_exception_to_mcp_error(MemoryProjectionError("timeline_projection_unavailable: stale status"))

    assert invalid_since.kind == "invalid_parameter"
    assert invalid_since.payload.code == "invalid_timeline_since"
    assert unavailable.kind == "execution"
    assert unavailable.payload.code == "timeline_projection_unavailable"


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


def test_internal_error_may_include_user_graph_home_path(tmp_path: Path) -> None:
    graph_home_path = tmp_path / "state"
    secret_path = tmp_path / "vault" / "wiki" / "page.md"
    error = map_exception_to_mcp_error(
        RuntimeError(f"failed at {graph_home_path}; checked {secret_path}"),
        user_graph_home_path=graph_home_path,
    )

    assert str(graph_home_path) in error.payload.message
    assert str(secret_path) not in error.payload.message
    assert "<redacted-path>" in error.payload.message
