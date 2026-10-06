import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from graph_document import GraphLimits, ReadLimits
from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.legacy_graph_projection import LegacyGraphProjection
from tests.test_cli_graph_indexing import (
    _ConfiguredDeterministicTextEmbeddings,
    _deterministic_text_embeddings,
    write_page,
)
from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_document_service_factory import GraphDocumentServiceFactory
from vault_graph.app.graph_store_factory import document_store_path
from vault_graph.app.projection_generation import ProjectionGenerationManager
from vault_graph.app.read_only_service_factory import ReadOnlyServiceFactory
from vault_graph.cli.main import app
from vault_graph.extraction.vault_graph_document_adapter import VaultProjectionRequest
from vault_graph.graph.graph_contracts import GraphExtractionSpec, current_graph_extraction_spec
from vault_graph.graph.graph_identity import graph_scope_key
from vault_graph.http.http_errors import HttpServerConfig
from vault_graph.http.http_server import create_http_app
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_service_factory import McpServiceFactory
from vault_graph.mcp.mcp_tools import FindRelatedInput, McpToolRegistry
from vault_graph.memory.result_explanation_cache import ResultExplanationCache
from vault_graph.projection.graph_projection import GraphProjectionEdge, GraphProjectionNode
from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter
from vault_graph.storage.local.document_graph_store import DocumentGraphStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore


def fingerprints(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items() if key != "generated_at"}
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def invoke_public_gateways(home: Path) -> tuple[dict[str, Any], ...]:
    cli = CliRunner().invoke(app, ["related", "--graph-home", str(home), "--format", "json", "Source"])
    assert cli.exit_code == 0, cli.output
    cli_payload = json.loads(cli.stdout)
    with TestClient(create_http_app(HttpServerConfig(home))) as client:
        response = client.post("/related", json={"target": "Source"})
        assert response.status_code == 200, response.text
        http_payload = response.json()
    factory = McpServiceFactory(graph_home_path=home)
    registry = McpToolRegistry(
        services=factory.open_read_only(),
        service_factory=factory,
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )
    mcp_payload = registry.find_related(FindRelatedInput(target="Source")).payload
    for payload in (cli_payload, http_payload, mcp_payload):
        count = payload["result_count"]
        assert isinstance(count, int) and count > 0, json.dumps(payload)
        assert payload["projection_build_id"]
    return tuple(normalize(payload) for payload in (cli_payload, http_payload, mcp_payload))


def indexed_home(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> tuple[Path, Path]:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)

    def embeddings(_self: object, config: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _deterministic_text_embeddings(config)

    monkeypatch.setattr(ReadOnlyServiceFactory, "_search_text_embeddings", embeddings)
    vault = tmp_path / "vault"
    write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[target]].\n")
    write_page(vault, "wiki/target.md", "# Target\nTarget evidence.\n")
    home = tmp_path / "state"
    runner = CliRunner()
    initialized = runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(home)])
    assert initialized.exit_code == 0, initialized.output
    indexed = runner.invoke(app, ["index", "--graph-home", str(home)])
    assert indexed.exit_code == 0, indexed.output
    return vault, home


def test_real_public_factories_preserve_legacy_results_and_read_only_state(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    before_vault, before_state = fingerprints(vault), fingerprints(home)
    adapter_results = invoke_public_gateways(home)
    monkeypatch.setattr(
        "vault_graph.projection.vault_graph_projection_adapter.VaultGraphProjectionAdapter",
        LegacyGraphProjection,
    )
    legacy_results = invoke_public_gateways(home)
    assert adapter_results == legacy_results
    assert fingerprints(vault) == before_vault
    assert fingerprints(home) == before_state


def test_document_backend_transition_serves_public_queries_without_legacy_database(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    class FixedIndexTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> "FixedIndexTime":
            return cls(2026, 10, 4, 12, tzinfo=UTC)

    # Compare the same source and indexing instant, including revision IDs.
    monkeypatch.setattr("vault_graph.indexing.metadata_indexer.datetime", FixedIndexTime)
    monkeypatch.setattr("vault_graph.indexing.graph_indexer.datetime", FixedIndexTime)
    vault, home = indexed_home(tmp_path, monkeypatch)
    expected = invoke_public_gateways(home)
    before_vault = fingerprints(vault)
    switched = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    config = CatalogService(graph_home_path=home)
    config.graph_path.unlink()
    before_state = fingerprints(home)
    assert invoke_public_gateways(home) == expected
    assert fingerprints(home) == before_state
    assert fingerprints(vault) == before_vault


def test_document_index_and_legacy_rollback_keep_source_changes(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    switched = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    legacy_path = CatalogService(graph_home_path=home).graph_path
    legacy_before = hashlib.sha256(legacy_path.read_bytes()).hexdigest()
    write_page(vault, "wiki/new.md", "# New\nNew evidence.\n")
    write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[new]].\n")
    updated = runner.invoke(app, ["index", "--graph-home", str(home)])
    assert updated.exit_code == 0, updated.output
    config = CatalogService(graph_home_path=home)
    assert hashlib.sha256(config.graph_path.read_bytes()).hexdigest() == legacy_before
    document_results = invoke_public_gateways(home)
    assert any(item["entity"]["canonical_path"] == "wiki/new.md" for item in document_results[0]["items"])
    rolled_back = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "legacy"])
    assert rolled_back.exit_code == 0, rolled_back.output
    assert "mode: full" in rolled_back.output
    legacy_results = invoke_public_gateways(home)
    assert any(item["entity"]["canonical_path"] == "wiki/new.md" for item in legacy_results[0]["items"])
    assert document_results[0]["result_count"] == legacy_results[0]["result_count"]


def test_document_legacy_document_roundtrip_rebuilds_current_source(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    for backend in ("document", "legacy"):
        result = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", backend])
        assert result.exit_code == 0, result.output
    write_page(vault, "wiki/new.md", "# New\nNew evidence.\n")
    write_page(vault, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[new]].\n")
    before_vault = fingerprints(vault)
    previous = ProjectionGenerationManager(home).active_layout()
    assert previous is not None
    before_generation = fingerprints(previous.root_path)
    result = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert result.exit_code == 0, result.output
    assert fingerprints(vault) == before_vault
    assert fingerprints(previous.root_path) == before_generation
    related = invoke_public_gateways(home)[0]
    assert any(item["entity"]["canonical_path"] == "wiki/new.md" for item in related["items"])


@pytest.mark.parametrize("corruption", ["schema", "profile", "cache", "checkpoint_shape"])
def test_full_document_rebuild_recovers_incompatible_cache(
    tmp_path: Path, monkeypatch: MonkeyPatch, corruption: str
) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert result.exit_code == 0, result.output
    config = CatalogService(graph_home_path=home)
    if corruption == "schema":
        with sqlite3.connect(document_store_path(config) / "derived.sqlite3") as connection:
            connection.execute("UPDATE schema_info SET version = 'unsupported-schema'")
    elif corruption == "cache":
        (document_store_path(config) / "compatibility.json").unlink()
    elif corruption == "checkpoint_shape":
        marker = document_store_path(config) / "compatibility.json"
        wrapped = json.loads(marker.read_text())
        del wrapped["payload"]["plans"][0]["requested_scope"]
        payload = json.dumps(wrapped["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        wrapped["digest"] = hashlib.sha256(payload.encode()).hexdigest()
        marker.write_text(json.dumps(wrapped), encoding="utf-8")
    else:
        next_spec = GraphExtractionSpec.from_payload(
            {**json.loads(current_graph_extraction_spec().serialized_spec), "spec_version": "next-extraction"}
        )
        for module in (
            "vault_graph.extraction.vault_graph_document_adapter",
            "vault_graph.app.local_index_service_factory",
            "vault_graph.graph.graph_contracts",
            "vault_graph.cli.main",
        ):
            monkeypatch.setattr(f"{module}.current_graph_extraction_spec", lambda: next_spec)
    previous = ProjectionGenerationManager(home).active_layout()
    assert previous is not None
    before_generation = fingerprints(previous.root_path)
    before_vault = fingerprints(vault)
    rejected = runner.invoke(app, ["related", "Source", "--graph-home", str(home), "--format", "json"])
    assert rejected.exit_code != 0
    assert fingerprints(previous.root_path) == before_generation
    recovered = runner.invoke(app, ["index", "--graph-home", str(home), "--full"])
    assert recovered.exit_code == 0, recovered.output
    assert fingerprints(previous.root_path) == before_generation
    assert fingerprints(vault) == before_vault
    assert invoke_public_gateways(home)[0]["result_count"] > 0


def test_incompatible_multi_vault_cache_requires_full_all_vaults(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    second = tmp_path / "second"
    write_page(second, "wiki/source.md", "---\ntitle: Source\n---\nSee [[target]].\n")
    write_page(second, "wiki/target.md", "# Second target\nEvidence.\n")
    runner = CliRunner()
    added = runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--graph-home", str(home)])
    assert added.exit_code == 0, added.output
    switched = runner.invoke(app, ["index", "--graph-home", str(home), "--all-vaults", "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    config = CatalogService(graph_home_path=home)
    with sqlite3.connect(document_store_path(config) / "derived.sqlite3") as connection:
        connection.execute("UPDATE schema_info SET version = 'unsupported-schema'")
    manager = ProjectionGenerationManager(home)
    previous = manager.active_layout()
    assert previous is not None
    before_generation, before_vaults = fingerprints(previous.root_path), (fingerprints(vault), fingerprints(second))
    rejected = runner.invoke(app, ["index", "--graph-home", str(home), "--full"])
    assert rejected.exit_code != 0
    assert "requires --all-vaults" in rejected.output
    assert manager.active_layout() == previous
    assert fingerprints(previous.root_path) == before_generation
    recovered = runner.invoke(app, ["index", "--graph-home", str(home), "--full", "--all-vaults"])
    assert recovered.exit_code == 0, recovered.output
    for entry in config.load_catalog().entries():
        result = runner.invoke(
            app, ["related", "Source", "--vault-id", entry.vault_id, "--graph-home", str(home), "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["result_count"] > 0
    assert fingerprints(previous.root_path) == before_generation
    assert (fingerprints(vault), fingerprints(second)) == before_vaults


def test_failed_document_cache_rebuild_keeps_previous_generation(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    switched = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    config = CatalogService(graph_home_path=home)
    (document_store_path(config) / "compatibility.json").unlink()
    manager = ProjectionGenerationManager(home)
    previous = manager.active_layout()
    assert previous is not None
    before_generation, before_vault = fingerprints(previous.root_path), fingerprints(vault)
    generations = set(previous.root_path.parent.iterdir())

    def failed_apply(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("injected graph rebuild failure")

    monkeypatch.setattr(DocumentGraphStore, "apply_reconcile_plan", failed_apply)
    failed = runner.invoke(app, ["index", "--graph-home", str(home), "--full"])
    assert failed.exit_code != 0
    assert "injected graph rebuild failure" in str(failed.exception)
    assert manager.active_layout() == previous
    assert set(previous.root_path.parent.iterdir()) == generations
    assert fingerprints(previous.root_path) == before_generation
    assert fingerprints(vault) == before_vault


def test_missing_backend_selector_cannot_revive_copied_legacy_state(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    runner = CliRunner()
    switched = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert switched.exit_code == 0, switched.output
    config = CatalogService(graph_home_path=home)
    (config.graph_path.parent / "backend.json").unlink()
    before = fingerprints(home)
    queried = runner.invoke(app, ["related", "--graph-home", str(home), "--format", "json", "Source"])
    assert queried.exit_code != 0
    assert "backend selector is missing" in queried.output
    assert fingerprints(home) == before


def test_document_transition_dry_run_reports_intent_without_creating_state(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    before_home, before_vault = fingerprints(home), fingerprints(vault)
    result = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "graph_backend_transition: legacy -> document" in result.output
    assert fingerprints(home) == before_home
    assert fingerprints(vault) == before_vault


def test_legacy_public_query_does_not_require_graph_document_package(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    before_home, before_vault = fingerprints(home), fingerprints(vault)
    code = """
import importlib.abc
import sys
class MissingDocumentPackage(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'graph_document' or fullname.startswith('graph_document.'):
            raise ModuleNotFoundError('graph_document intentionally unavailable')
sys.meta_path.insert(0, MissingDocumentPackage())
from vault_graph.cli.main import app
app()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, "related", "Source", "--graph-home", str(home), "--format", "json"],
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")},
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["result_count"] > 0
    assert fingerprints(home) == before_home
    assert fingerprints(vault) == before_vault


def test_failed_transition_construction_discards_private_generation(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    from vault_graph.errors import GraphStoreUnavailable
    from vault_graph.storage.local.document_graph_store import DocumentGraphStore

    vault, home = indexed_home(tmp_path, monkeypatch)
    before_home, before_vault = fingerprints(home), fingerprints(vault)

    def failed_bootstrap(*args: object, **kwargs: object) -> None:
        raise GraphStoreUnavailable("bootstrap fault")

    monkeypatch.setattr(DocumentGraphStore, "bootstrap_from_legacy", failed_bootstrap)
    result = CliRunner().invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert result.exit_code != 0
    assert "bootstrap fault" in result.output
    assert fingerprints(home) == before_home
    assert fingerprints(vault) == before_vault


def test_document_transition_includes_newly_registered_vault_and_preserves_scope(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _, home = indexed_home(tmp_path, monkeypatch)
    other = tmp_path / "other"
    write_page(other, "wiki/source.md", "---\ntitle: Source\n---\n# Overview\nSee [[other-target]].\n")
    write_page(other, "wiki/other-target.md", "# Other Target\nOther evidence.\n")
    runner = CliRunner()
    added = runner.invoke(app, ["vault", "add", "other", "--path", str(other), "--graph-home", str(home)])
    assert added.exit_code == 0, added.output
    rejected = runner.invoke(app, ["index", "--graph-home", str(home), "--graph-backend", "document"])
    assert rejected.exit_code != 0 and "requires --all-vaults" in rejected.output
    transitioned = runner.invoke(
        app, ["index", "--graph-home", str(home), "--graph-backend", "document", "--all-vaults"]
    )
    assert transitioned.exit_code == 0, transitioned.output
    for vault_id, target_path in (("default", "wiki/target.md"), ("other", "wiki/other-target.md")):
        result = runner.invoke(
            app, ["related", "Source", "--graph-home", str(home), "--vault-id", vault_id, "--format", "json"]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert any(item["entity"]["canonical_path"] == target_path for item in payload["items"])
        assert all(item["entity"]["vault_id"] == vault_id for item in payload["items"])


def test_document_graph_factory_integrates_real_metadata_and_preserves_legacy_cache(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    vault, home = indexed_home(tmp_path, monkeypatch)
    before_vault, before_state = fingerprints(vault), fingerprints(home)
    catalog_service = CatalogService(graph_home_path=home)
    scope = catalog_service.load_catalog().default_scope()
    legacy = SQLiteGraphStore.open_read_only(catalog_service.graph_path)
    original = legacy.current_manifest((scope,))
    bridge = GraphDocumentServiceFactory(graph_home_path=home).open_adapter(
        graph_limits=GraphLimits(10, 100000, 1000000, 1000, 1000, 10000, 1024),
        read_limits=ReadLimits(1000, 1000, 10000, 100, 1000000),
    )
    assert fingerprints(home) == before_state
    batch = bridge.materialize_documents(scope)
    update = bridge.sync(batch, expected_revision=0)
    restored = bridge.restore_snapshot(collection_id=batch.collection_id)
    assert update.ready and restored.graph_revision == update.graph_revision
    assert {node.entity_id for node in restored.nodes} == {row.entity_id for row in original.entity_rows}
    assert {edge.relationship_id for edge in restored.relationships} == {
        row.relationship_id for row in original.relationship_rows
    }
    original_edges: list[GraphProjectionEdge] = []
    for edge in restored.relationships:
        expected = legacy.get_relationship(source_vault_id=edge.source_vault_id, relationship_id=edge.relationship_id)
        assert expected is not None
        assert (edge.status, edge.confidence) == (expected.status, expected.confidence)
        assert edge.evidence_ref_ids == tuple(sorted(ref.evidence_ref_id for ref in expected.evidence_refs))
        original_edges.append(
            GraphProjectionEdge(
                expected.source_vault_id,
                expected.source_entity_id,
                expected.target_vault_id,
                expected.target_entity_id,
                expected.relationship_id,
                expected.type,
                expected.status,
                expected.confidence,
                tuple(sorted(ref.evidence_ref_id for ref in expected.evidence_refs)),
                expected.graph_index_revision,
            )
        )
    original_nodes: list[GraphProjectionNode] = []
    for row in original.entity_rows:
        entity = legacy.get_entity(vault_id=row.vault_id, entity_id=row.entity_id)
        assert entity is not None
        original_nodes.append(
            GraphProjectionNode(entity.vault_id, entity.entity_id, entity.type, entity.name, entity.normalized_name)
        )
    seed = next(node for node in original_nodes if node.name == "Source" and node.type == "WikiPage")
    projection_input = bridge.read_projection_input(
        VaultProjectionRequest(
            collection_id=batch.collection_id,
            selection="all",
            seed_entity_ids=(seed.entity_id,),
            actual_scope_keys=(graph_scope_key(scope),),
            max_depth=2,
            direction="both",
            relationship_types=(),
            statuses=("stated", "inferred", "contested"),
            include_cross_vault=False,
            limit=10,
            edge_limit=500,
            source_graph_revisions=tuple(row.graph_index_revision for row in original.revision_rows),
            relationship_revisions=tuple(
                (edge.source_vault_id, edge.relationship_id, edge.graph_index_revision) for edge in original_edges
            ),
        )
    )
    expected_input = replace(
        projection_input,
        seeds=(seed,),
        nodes=tuple(original_nodes),
        relationships=tuple(original_edges),
    )
    assert VaultGraphProjectionAdapter().project(projection_input) == LegacyGraphProjection().project(expected_input)
    assert fingerprints(vault) == before_vault
    after = fingerprints(home)
    assert {path: after[path] for path in before_state} == before_state
    assert (home / "cache" / "graph-document" / "derived.sqlite3").is_file()
