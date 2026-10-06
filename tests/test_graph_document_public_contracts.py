"""Public read contracts across the legacy and document graph backends."""

import json
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any, Self, cast

from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import (
    _ConfiguredDeterministicTextEmbeddings,
    _deterministic_text_embeddings,
    write_page,
)
from tests.test_graph_module_public_integration import fingerprints
from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_store_factory import document_store_path
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.cli.main import app
from vault_graph.http.http_errors import HttpServerConfig
from vault_graph.http.http_server import create_http_app
from vault_graph.mcp.mcp_resources import McpResourceRequest
from vault_graph.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.mcp.mcp_tools import (
    AskVaultInput,
    BuildContextPackInput,
    CheckIndexStatusInput,
    DecisionTraceInput,
    FindRelatedInput,
    SearchVaultInput,
)


class FixedIndexTime(datetime):
    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        return cls(2026, 10, 4, 12, tzinfo=UTC)


def _indexed_decision_home(tmp_path: Path, monkeypatch: MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)

    def embeddings(_self: object, config: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _deterministic_text_embeddings(config)

    monkeypatch.setattr(ReadOnlyServiceFactory, "_search_text_embeddings", embeddings)
    monkeypatch.setattr("vault_graph.indexing.metadata_indexer.datetime", FixedIndexTime)
    monkeypatch.setattr("vault_graph.indexing.graph_indexer.datetime", FixedIndexTime)
    vault = tmp_path / "vault"
    write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[target]].\n")
    write_page(vault, "wiki/target.md", "# Target\nTarget evidence.\n")
    write_page(
        vault,
        "wiki/decisions/use-target.md",
        "---\ntype: decision\ntitle: Use Target\ndepends_on: target\n---\n"
        "# Decision\nUse [[target]] as the target evidence source.\n",
    )
    home = tmp_path / "state"
    runner = CliRunner()
    initialized = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(home)])
    assert initialized.exit_code == 0, initialized.output
    indexed = runner.invoke(app, ["index", "--graph-home", str(home)])
    assert indexed.exit_code == 0, indexed.output
    return vault, home


def _without_read_time(value: Any) -> Any:
    # Answer IDs include read time. Status run times and vector revision change on the second index run.
    volatile = {"generated_at", "answer_id"}
    if isinstance(value, dict):
        return {key: _without_read_time(item) for key, item in value.items() if key not in volatile}
    if isinstance(value, list):
        return [_without_read_time(item) for item in value]
    return value


def _comparable_status(value: dict[str, Any]) -> dict[str, Any]:
    status = dict(value)
    for key in ("graph_last_success_at", "vector_last_success_at", "vector_revision"):
        status.pop(key, None)
    for key in ("graph", "vector"):
        if isinstance(status.get(key), dict):
            record = dict(status[key])
            record.pop("last_success_at", None)
            if key == "vector":
                record.pop("revision", None)
            status[key] = record
    if isinstance(status.get("active_generation"), dict):
        generation = dict(status["active_generation"])
        generation.pop("id", None)
        generation.pop("path", None)
        status["active_generation"] = generation
    if isinstance(status.get("projection_bundle"), dict):
        bundle = dict(status["projection_bundle"])
        if isinstance(bundle.get("revisions"), dict):
            revisions = dict(bundle["revisions"])
            revisions.pop("vector", None)
            bundle["revisions"] = revisions
        status["projection_bundle"] = bundle
    if isinstance(status.get("health_explorer"), dict):
        health = dict(status["health_explorer"])
        backends = []
        for backend in health.get("backends", []):
            record = dict(backend)
            record.pop("last_success_at", None)
            if str(record.get("revision", "")).startswith("vector-"):
                record.pop("revision", None)
            backends.append(record)
        health["backends"] = backends
        status["health_explorer"] = health
    return status


def _differences(left: Any, right: Any, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        return [
            difference
            for key in left.keys() | right.keys()
            for difference in _differences(left.get(key), right.get(key), f"{path}.{key}")
        ]
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return [
            difference
            for index, (item_left, item_right) in enumerate(zip(left, right, strict=True))
            for difference in _differences(item_left, item_right, f"{path}[{index}]")
        ]
    return [] if left == right else [f"{path}: {left!r} != {right!r}"]


def _cli_json(home: Path, *args: str) -> dict[str, Any]:
    result = CliRunner().invoke(app, [*args, "--graph-home", str(home), "--format", "json"])
    assert result.exit_code == 0, result.output
    return cast(dict[str, Any], json.loads(result.stdout))


def _http_json(client: TestClient, path: str, payload: dict[str, object] | None = None) -> dict[str, Any]:
    response = client.get(path) if payload is None else client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def _public_reads(home: Path) -> dict[str, Any]:
    cli = {
        "related": _cli_json(home, "related", "Source"),
        "decision_trace": _cli_json(home, "decision-trace", "Use Target"),
        "search_plain": _cli_json(home, "search", "Use Target"),
        "search_graph": _cli_json(home, "search", "Use Target", "--include-graph"),
        "context": _cli_json(home, "context", "Use Target", "--include-graph"),
        "answer": _cli_json(home, "ask", "Why use Target?", "--include-graph"),
        "status": _cli_json(home, "status"),
    }
    with TestClient(create_http_app(HttpServerConfig(home))) as client:
        http = {
            "related": _http_json(client, "/related", {"target": "Source"}),
            "decision_trace": _http_json(client, "/decision-trace", {"decision_or_topic": "Use Target"}),
            "search_plain": _http_json(client, "/search", {"query": "Use Target"}),
            "search_graph": _http_json(client, "/search", {"query": "Use Target", "include_graph": True}),
            "context": _http_json(client, "/context", {"goal": "Use Target", "include_graph": True}),
            "answer": _http_json(client, "/ask", {"question": "Why use Target?", "include_graph": True}),
            "status": _http_json(client, "/status"),
        }
    registered = create_mcp_server(McpServerConfig(graph_home_path=home))
    tools = registered.tool_registry
    mcp = {
        "related": tools.find_related(FindRelatedInput(target="Source")).payload,
        "decision_trace": tools.get_decision_trace(DecisionTraceInput(decision_or_topic="Use Target")).payload,
        "search_plain": tools.search_vault(SearchVaultInput(query="Use Target")).payload,
        "search_graph": tools.search_vault(SearchVaultInput(query="Use Target", include_graph=True)).payload,
        "context": tools.build_context_pack(BuildContextPackInput(goal="Use Target", include_graph=True)).payload,
        "answer": tools.ask_vault(AskVaultInput(question="Why use Target?", include_graph=True)).payload,
        "status": tools.check_index_status(CheckIndexStatusInput()).payload,
    }
    entity_id = cli["related"]["resolved_target"]["entity_id"]
    resource = registered.resource_registry.read(McpResourceRequest(uri=f"vault://default/graph/entities/{entity_id}"))
    assert resource.content_mime_type == "application/json"
    mcp["graph_resource"] = json.loads(resource.text)
    for raw_gateway in (cli, http, mcp):
        gateway = cast(dict[str, Any], raw_gateway)
        assert cast(int, gateway["related"]["result_count"]) > 0
        assert gateway["decision_trace"]["trace_kind"] == "decision"
        assert any(step["role"] == "depends_on" for step in gateway["decision_trace"]["steps"])
        assert all(
            signal["kind"] != "graph" for result in gateway["search_plain"]["results"] for signal in result["signals"]
        )
        assert any(
            signal["kind"] == "graph" for result in gateway["search_graph"]["results"] for signal in result["signals"]
        )
        assert gateway["context"]["backend"]["graph_projection"]["used"] is True
        assert gateway["context"]["decisions"]
        assert gateway["context"]["evidence"]
        assert gateway["answer"]["evidence"]
        assert any(step["kind"] == "decision_trace" for step in gateway["answer"]["reasoning_trace"])
    cli["status"] = _comparable_status(cli["status"])
    http["status"] = _comparable_status(http["status"])
    mcp["status"] = _comparable_status(mcp["status"])
    return cast(dict[str, Any], _without_read_time({"cli": cli, "http": http, "mcp": mcp}))


def test_document_backend_preserves_public_read_contracts_without_read_writes(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    vault, home = _indexed_decision_home(tmp_path, monkeypatch)
    source_before = fingerprints(vault)
    legacy_state_before_reads = fingerprints(home)
    legacy = _public_reads(home)
    assert fingerprints(vault) == source_before
    assert fingerprints(home) == legacy_state_before_reads

    switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    CatalogService(graph_home_path=home).graph_path.unlink()
    state_before_reads = fingerprints(home)
    document = _public_reads(home)
    for gateway, actual_reads in document.items():
        for operation, actual in actual_reads.items():
            assert actual == legacy[gateway][operation], "\n".join(
                _differences(actual, legacy[gateway][operation], f"{gateway}.{operation}")[:12]
            )
    assert fingerprints(home) == state_before_reads
    assert fingerprints(vault) == source_before


def test_missing_document_compatibility_marker_rejects_public_graph_reads(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    vault, home = _indexed_decision_home(tmp_path, monkeypatch)
    switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    assert CatalogService(graph_home_path=home).graph_path.is_file()
    marker = document_store_path(CatalogService(graph_home_path=home)) / "compatibility.json"
    assert marker.is_file()
    marker.unlink()
    source_before, state_before = fingerprints(vault), fingerprints(home)

    cli = CliRunner().invoke(app, ["related", "Source", "--graph-home", str(home), "--format", "json"])
    assert cli.exit_code != 0
    with TestClient(create_http_app(HttpServerConfig(home)), raise_server_exceptions=False) as client:
        response = client.post("/related", json={"target": "Source"})
    assert response.status_code != 200
    assert fingerprints(vault) == source_before
    assert fingerprints(home) == state_before
