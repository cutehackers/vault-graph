from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_result_explanation import make_record
from vault_graph.app.catalog_service import CatalogService
from vault_graph.errors import DataHomeNotInitializedError, LegacyDataHomeDetectedError, VaultGraphError
from vault_graph.http.http_errors import HttpRequestError, HttpServerConfig, map_exception_to_http_error
from vault_graph.http.http_server import create_http_app
from vault_graph.memory.result_explanation_cache import ResultExplanationCache


def make_state(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    CatalogService(graph_home_path=graph_home_path).create_default_catalog(vault_root=vault_root)
    return graph_home_path


def test_http_config_rejects_remote_host(tmp_path: Path) -> None:
    with pytest.raises(HttpRequestError, match="remote HTTP serving is not supported"):
        HttpServerConfig(graph_home_path=tmp_path / "state", host="0.0.0.0")


def test_http_health_loads_catalog(tmp_path: Path) -> None:
    app = create_http_app(HttpServerConfig(graph_home_path=make_state(tmp_path)))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "vault-graph", "transport": "http"}


def test_http_health_returns_error_payload_for_missing_catalog(tmp_path: Path) -> None:
    app = create_http_app(HttpServerConfig(graph_home_path=tmp_path / "missing-state"))

    response = TestClient(app, raise_server_exceptions=False).get("/health")

    assert response.status_code == 400
    assert "error" in response.json()


def test_http_data_home_errors_include_onboarding_recovery_hints() -> None:
    missing = map_exception_to_http_error(DataHomeNotInitializedError("data_home_not_initialized: setup required"))
    legacy = map_exception_to_http_error(LegacyDataHomeDetectedError("legacy_data_home_detected: old layout"))

    assert missing.payload.code == "data_home_not_initialized"
    assert "vg setup" in (missing.payload.recovery_hint or "")
    assert legacy.payload.code == "legacy_data_home_detected"
    assert "new --graph-home" in (legacy.payload.recovery_hint or "")


def test_http_package_does_not_import_mcp_modules() -> None:
    import vault_graph.http.http_server as http_server

    assert not any(name.startswith("vault_graph.mcp") for name in http_server.__dict__)
    assert issubclass(HttpRequestError, VaultGraphError)


def test_http_explain_result_uses_explanation_service(tmp_path: Path) -> None:
    cache = ResultExplanationCache()
    record = make_record()
    cache.put(record)
    app = create_http_app(HttpServerConfig(graph_home_path=tmp_path / "state"), result_explanation_cache=cache)

    response = TestClient(app).post("/explain-result", json={"result_id": record.result_id})

    assert response.status_code == 200
    assert response.json()["result_id"] == record.result_id
    assert response.json()["source_kind"] == "search_result"


def test_http_explain_result_returns_error_for_missing_record(tmp_path: Path) -> None:
    app = create_http_app(
        HttpServerConfig(graph_home_path=tmp_path / "state"),
        result_explanation_cache=ResultExplanationCache(),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/explain-result",
        json={"result_id": "missing"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "result_explanation_not_found"
    assert "Rerun the original HTTP request" in response.json()["error"]["recovery_hint"]


def test_http_explain_result_rejects_blank_result_id(tmp_path: Path) -> None:
    app = create_http_app(
        HttpServerConfig(graph_home_path=tmp_path / "state"),
        result_explanation_cache=ResultExplanationCache(),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/explain-result",
        json={"result_id": " "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_result_id"
    assert response.json()["error"]["message"] == "result_id is required"
