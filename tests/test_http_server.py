from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_result_explanation import make_record
from vault_graph.app.catalog_service import CatalogService
from vault_graph.errors import VaultGraphError
from vault_graph.http.http_errors import HttpRequestError, HttpServerConfig
from vault_graph.http.http_server import create_http_app
from vault_graph.memory.result_explanation_cache import ResultExplanationCache


def make_state(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    CatalogService(state_path=state_path).create_default_catalog(vault_root=vault_root)
    return state_path


def test_http_config_rejects_remote_host(tmp_path: Path) -> None:
    with pytest.raises(HttpRequestError, match="remote HTTP serving is not supported"):
        HttpServerConfig(state_path=tmp_path / "state", host="0.0.0.0")


def test_http_health_loads_catalog(tmp_path: Path) -> None:
    app = create_http_app(HttpServerConfig(state_path=make_state(tmp_path)))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "vault-graph", "transport": "http"}


def test_http_health_returns_error_payload_for_missing_catalog(tmp_path: Path) -> None:
    app = create_http_app(HttpServerConfig(state_path=tmp_path / "missing-state"))

    response = TestClient(app, raise_server_exceptions=False).get("/health")

    assert response.status_code == 400
    assert "error" in response.json()


def test_http_package_does_not_import_mcp_modules() -> None:
    import vault_graph.http.http_server as http_server

    assert not any(name.startswith("vault_graph.mcp") for name in http_server.__dict__)
    assert issubclass(HttpRequestError, VaultGraphError)


def test_http_explain_result_uses_explanation_service(tmp_path: Path) -> None:
    cache = ResultExplanationCache()
    record = make_record()
    cache.put(record)
    app = create_http_app(HttpServerConfig(state_path=tmp_path / "state"), result_explanation_cache=cache)

    response = TestClient(app).post("/explain-result", json={"result_id": record.result_id})

    assert response.status_code == 200
    assert response.json()["result_id"] == record.result_id
    assert response.json()["source_kind"] == "search_result"


def test_http_explain_result_returns_error_for_missing_record(tmp_path: Path) -> None:
    app = create_http_app(
        HttpServerConfig(state_path=tmp_path / "state"),
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
        HttpServerConfig(state_path=tmp_path / "state"),
        result_explanation_cache=ResultExplanationCache(),
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/explain-result",
        json={"result_id": " "},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_result_id"
    assert response.json()["error"]["message"] == "result_id is required"
