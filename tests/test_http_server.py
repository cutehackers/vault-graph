from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_result_explanation import make_record
from vault_graph.errors import DataHomeNotInitializedError, LegacyDataHomeDetectedError, VaultGraphError
from vault_graph.interface.http.http_errors import HttpRequestError, HttpServerConfig, map_exception_to_http_error
from vault_graph.interface.http.http_server import create_http_app
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.retrieval.explanation.result_explanation_cache import ResultExplanationCache


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
    import vault_graph.interface.http.http_server as http_server

    assert not any(name.startswith("vault_graph.interface.mcp") for name in http_server.__dict__)
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


# --- V2: /search without scope uses the `cwd` project's Vaults; results carry vault_name and vault_role ---


class _RecordingRetrieval:
    def __init__(self) -> None:
        from tests.test_mcp_tool_serialization import make_search_response

        self.response = make_search_response()
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return self.response


class _SearchServiceFactory:
    def __init__(self, catalog: object, retrieval: _RecordingRetrieval) -> None:
        self.catalog = catalog
        self.retrieval = retrieval

    def open_read_only(self) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(catalog=self.catalog, metadata_store=_AllIndexed())

    def open_retrieval_service(self, *, include_graph: bool = False) -> _RecordingRetrieval:
        del include_graph
        return self.retrieval


class _AllIndexed:
    def list_document_states(self, vault_ids: tuple[str, ...]) -> tuple[object, ...]:
        from types import SimpleNamespace

        return tuple(SimpleNamespace(document_id="doc") for _ in vault_ids)


def _project_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, project_vaults: tuple[str, ...] = ("personal", "team")
) -> tuple[TestClient, _RecordingRetrieval, Path]:
    import json
    import subprocess
    from typing import Any, cast

    from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV
    from vault_graph.operation.scope.vault_catalog import VaultCatalog, VaultCatalogEntry

    entries = []
    for vault_id, folder in (("main", "vault"), ("p-id", "personal"), ("t-id", "team")):
        (tmp_path / folder).mkdir()
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=tmp_path / folder))
    catalog = VaultCatalog.from_entries(entries=entries, active_vault_id="main")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    map_file = tmp_path / "vault-map.json"
    map_file.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "personal": {"path": str(tmp_path / "personal"), "role": "personal"},
                    "team": {"path": str(tmp_path / "team"), "role": "team"},
                    "main-vault": {"path": str(tmp_path / "vault"), "role": "project"},
                    "unregistered": {"path": str(tmp_path / "nowhere"), "role": "project"},
                },
                "projects": {"repo": {"root": str(repo), "vaults": list(project_vaults)}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(VAULT_MAP_ENV, str(map_file))
    retrieval = _RecordingRetrieval()
    app = create_http_app(
        HttpServerConfig(graph_home_path=tmp_path / "state"),
        service_factory=cast(Any, _SearchServiceFactory(catalog, retrieval)),
    )
    return TestClient(app, raise_server_exceptions=False), retrieval, repo


def test_http_search_with_cwd_searches_every_project_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, retrieval, repo = _project_app(tmp_path, monkeypatch)

    response = client.post("/search", json={"query": "GraphRAG", "cwd": str(repo)})

    assert response.status_code == 200
    assert retrieval.calls[0]["requested_scope"].vault_ids == ("p-id", "t-id")  # type: ignore[attr-defined]


def test_http_search_without_cwd_uses_the_active_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, retrieval, repo = _project_app(tmp_path, monkeypatch)
    monkeypatch.chdir(repo)

    response = client.post("/search", json={"query": "GraphRAG"})

    assert response.status_code == 200
    assert retrieval.calls[0]["requested_scope"].vault_ids == ("main",)  # type: ignore[attr-defined]


def test_http_search_results_carry_labels_and_explicit_scope_is_otherwise_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from vault_graph.interface.http.http_serialization import domain_to_json_dict

    client, retrieval, repo = _project_app(tmp_path, monkeypatch)

    response = client.post("/search", json={"query": "GraphRAG", "cwd": str(repo), "scope": {"vault_ids": ["main"]}})

    payload = response.json()
    assert retrieval.calls[0]["requested_scope"].vault_ids == ("main",)  # type: ignore[attr-defined]
    assert (payload["results"][0]["vault_name"], payload["results"][0]["vault_role"]) == ("main-vault", "project")
    for result in payload["results"]:
        del result["vault_name"], result["vault_role"]
    assert payload == domain_to_json_dict(retrieval.response)


def test_http_search_project_without_registered_vault_returns_empty_and_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, retrieval, repo = _project_app(tmp_path, monkeypatch, project_vaults=("unregistered",))

    response = client.post("/search", json={"query": "GraphRAG", "cwd": str(repo)})

    payload = response.json()
    assert response.status_code == 200
    assert retrieval.calls == []
    assert payload["results"] == []
    assert payload["result_count"] == 0
    assert any("vg setup" in warning["message"] for warning in payload["warnings"])


def test_http_search_rejects_a_non_string_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _project_app(tmp_path, monkeypatch)

    response = client.post("/search", json={"query": "GraphRAG", "cwd": 3})

    assert response.status_code == 400
