import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_graph_store_contract import make_entity, make_relationship
from vault_graph.cli.main import app
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph_retrieval import (
    GraphRetrievalRevision,
    GraphRetrievalWarning,
    RelatedItem,
    RelatedResponse,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference

runner = CliRunner()


class _FakeGraphRetrievalService:
    def __init__(self, response: RelatedResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def related(self, **kwargs: Any) -> RelatedResponse:
        self.calls.append(kwargs)
        return self.response


def test_cli_related_text_renders_evidence_linked_items(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = related_response()
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(app, ["related", "--state", str(tmp_path / "state"), "GraphRAG"])

    assert result.exit_code == 0
    assert fake_service.calls[0]["target"] == "GraphRAG"
    assert fake_service.calls[0]["requested_scope"].vault_ids == ("default",)
    assert "target: GraphRAG" in result.stdout
    assert "resolved: [default] GraphRAG (concept)" in result.stdout
    assert "projection: graph-projection-v1 build-1" in result.stdout
    assert "1. [default] Search" in result.stdout
    assert "relationship: depends_on stated" in result.stdout
    assert "evidence: [default] wiki/graphrag.md#dependency" in result.stdout
    assert "signals: graph" in result.stdout


def test_cli_related_text_renders_cross_vault_actual_scope(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = related_response(include_cross_vault=True)
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(
        app,
        ["related", "--state", str(tmp_path / "state"), "--all-vaults", "--include-cross-vault", "GraphRAG"],
    )

    assert result.exit_code == 0
    assert fake_service.calls[0]["include_cross_vault"] is True
    assert "actual_scopes: default:wiki:cross" in result.stdout


def test_cli_related_json_uses_related_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = related_response()
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(
        app,
        ["related", "--state", str(tmp_path / "state"), "--format", "json", "GraphRAG"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["target"] == "GraphRAG"
    assert payload["resolved_target"]["vault_id"] == "default"
    assert payload["graph_projection_version"] == GRAPH_PROJECTION_VERSION
    assert payload["result_count"] == 1
    assert payload["items"][0]["entity"]["name"] == "Search"
    assert payload["items"][0]["entity"]["evidence_refs"][0]["owner_kind"] == "entity"
    assert payload["items"][0]["entity"]["extraction_method"] == "test"
    assert payload["items"][0]["entity"]["created_at"] == "2026-06-10T00:00:00+00:00"
    assert payload["items"][0]["relationship_path"][0]["type"] == "depends_on"
    assert payload["items"][0]["relationship_path"][0]["evidence_refs"][0]["owner_kind"] == "relationship"
    assert payload["items"][0]["relationship_path"][0]["extraction_method"] == "test"
    assert payload["items"][0]["relationship_path"][0]["created_at"] == "2026-06-10T00:00:00+00:00"
    assert payload["items"][0]["evidence"][0]["chunk_id"] == "default-chunk"
    assert payload["warnings"] == []
    assert payload["store_revisions"][0]["kind"] == "graph"


def test_cli_related_rejects_include_cross_vault_without_all_vaults(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["related", "--state", str(tmp_path / "state"), "--include-cross-vault", "GraphRAG"],
    )

    assert result.exit_code == 1
    assert "include_cross_vault_requires_multi_vault_graph_scope" in result.stdout


def test_cli_related_ambiguous_target_exits_zero_with_warning(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    scope = QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",))
    first = make_entity("first", name="GraphRAG")
    second = make_entity("second", name="GraphRAG")
    response = RelatedResponse(
        target="GraphRAG",
        resolved_target=None,
        target_candidates=(first, second),
        requested_scope=scope,
        actual_scopes=(QueryScope(vault_ids=("first",), content_scopes=("wiki",)),),
        projection_build_id=None,
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=0,
        items=(),
        warnings=(
            GraphRetrievalWarning(
                code="ambiguous_graph_target",
                message="Graph target matched multiple equal-rank entities.",
                severity="warning",
                affected_vault_ids=("first", "second"),
            ),
        ),
        store_revisions=(),
        generated_at="2026-06-11T00:00:00+00:00",
    )
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(
        app,
        ["related", "--state", str(tmp_path / "state"), "--all-vaults", "GraphRAG"],
    )

    assert result.exit_code == 0
    assert "warning: ambiguous_graph_target [first,second]" in result.stdout
    assert "candidate: [first] GraphRAG (concept)" in result.stdout
    assert "candidate: [second] GraphRAG (concept)" in result.stdout


def test_cli_related_real_factory_does_not_create_missing_state_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    init_result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before = state_tree(state_path)

    result = runner.invoke(app, ["related", "--state", str(state_path), "GraphRAG"])

    assert init_result.exit_code == 0
    assert result.exit_code == 0
    assert "warning: graph_missing [default]" in result.stdout
    assert state_tree(state_path) == before
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "graph" / "graph.sqlite3").exists()
    assert not (state_path / "data" / "projection_cache").exists()


def related_response(*, include_cross_vault: bool = False) -> RelatedResponse:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",), include_cross_vault=include_cross_vault)
    source = make_entity("default", name="GraphRAG")
    target = make_entity("default", name="Search")
    relationship = make_relationship(source, target)
    evidence = EvidenceReference(
        vault_id="default",
        document_id="default-doc",
        chunk_id="default-chunk",
        path="wiki/graphrag.md",
        section="Dependency",
        anchor="dependency",
        content_hash="default-hash",
        raw_sha256="raw-sha",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )
    return RelatedResponse(
        target="GraphRAG",
        resolved_target=source,
        target_candidates=(source,),
        requested_scope=scope,
        actual_scopes=(scope,),
        projection_build_id="build-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        result_count=1,
        items=(
            RelatedItem(
                rank=1,
                entity=target,
                relationship_path=(relationship,),
                evidence=(evidence,),
                score=0.8,
                explanation="1-edge graph path via depends_on",
            ),
        ),
        warnings=(),
        store_revisions=(
            GraphRetrievalRevision(
                kind="graph",
                revision="graph-1",
                scope_key="default:wiki:local",
                vault_id="default",
            ),
            GraphRetrievalRevision(kind="projection", revision="build-1", scope_key="projection"),
        ),
        generated_at="2026-06-11T00:00:00+00:00",
    )


def fake_graph_service_factory(
    tmp_path: Path,
    fake_service: _FakeGraphRetrievalService,
) -> object:
    catalog = make_catalog(tmp_path=tmp_path, vault_ids=("default", "first", "second"))

    def factory(_: Path) -> tuple[object, VaultCatalog, _FakeGraphRetrievalService]:
        return object(), catalog, fake_service

    return factory


def make_catalog(*, tmp_path: Path, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries: list[VaultCatalogEntry] = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, content_scopes=("wiki",)))
    return VaultCatalog.from_entries(entries=entries, active_vault_id="default")


def state_tree(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(str(child.relative_to(path)) for child in path.rglob("*")))
