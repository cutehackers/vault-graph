import json
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_graph_retrieval_service import relationship_with_type, typed_entity
from tests.test_graph_store_contract import make_entity
from vault_graph.cli.main import app
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.projection.graph_projection import GRAPH_PROJECTION_VERSION
from vault_graph.retrieval.graph_retrieval import (
    DecisionTraceResponse,
    DecisionTraceStep,
    GraphRetrievalRevision,
    GraphRetrievalWarning,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference

runner = CliRunner()


class _FakeGraphRetrievalService:
    def __init__(self, response: DecisionTraceResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def decision_trace(self, **kwargs: Any) -> DecisionTraceResponse:
        self.calls.append(kwargs)
        return self.response


def test_cli_decision_trace_text_renders_steps(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = decision_trace_response()
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(app, ["decision-trace", "--state", str(tmp_path / "state"), "Use GraphRAG"])

    assert result.exit_code == 0
    assert fake_service.calls[0]["topic"] == "Use GraphRAG"
    assert fake_service.calls[0]["requested_scope"].vault_ids == ("default",)
    assert "topic: Use GraphRAG" in result.stdout
    assert "trace_kind: decision" in result.stdout
    assert "resolved: [default] Use GraphRAG (Decision)" in result.stdout
    assert "projection: graph-projection-v1 trace-build-1" in result.stdout
    assert "steps: 2" in result.stdout
    assert "1. decision [default] Use GraphRAG" in result.stdout
    assert "2. depends_on [default] Search" in result.stdout
    assert "evidence: [default] wiki/decisions/use-graphrag.md#decision" in result.stdout
    assert "evidence: [default] wiki/search.md#dependency" in result.stdout
    assert "answer:" not in result.stdout
    assert "recommendation:" not in result.stdout
    assert "final:" not in result.stdout


def test_cli_decision_trace_json_uses_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = decision_trace_response()
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(
        app,
        ["decision-trace", "--state", str(tmp_path / "state"), "--format", "json", "Use GraphRAG"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["topic"] == "Use GraphRAG"
    assert payload["trace_kind"] == "decision"
    assert payload["resolved_target"]["type"] == "Decision"
    assert payload["graph_projection_version"] == GRAPH_PROJECTION_VERSION
    assert payload["steps"][0]["role"] == "decision"
    assert payload["steps"][0]["relationship_path"] == []
    assert payload["steps"][1]["role"] == "depends_on"
    assert payload["steps"][1]["relationship_path"][0]["type"] == "depends_on"
    assert payload["steps"][1]["evidence"][0]["path"] == "wiki/search.md"
    assert payload["warnings"] == []
    assert payload["store_revisions"][0]["kind"] == "graph"


def test_cli_decision_trace_topic_trace_warning_is_visible(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    response = decision_trace_response(trace_kind="topic")
    fake_service = _FakeGraphRetrievalService(response)
    monkeypatch.setattr(
        "vault_graph.cli.main._graph_retrieval_service",
        fake_graph_service_factory(tmp_path, fake_service),
    )

    result = runner.invoke(app, ["decision-trace", "--state", str(tmp_path / "state"), "GraphRAG"])

    assert result.exit_code == 0
    assert "warning: topic_not_durable_decision [default]" in result.stdout
    assert "trace_kind: topic" in result.stdout


def test_cli_decision_trace_real_factory_does_not_create_missing_state_files(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    init_result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before = state_tree(state_path)

    result = runner.invoke(app, ["decision-trace", "--state", str(state_path), "GraphRAG"])

    assert init_result.exit_code == 0
    assert result.exit_code == 0
    assert "warning: graph_missing [default]" in result.stdout
    assert state_tree(state_path) == before
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "graph" / "graph.sqlite3").exists()
    assert not (state_path / "data" / "projection_cache").exists()


def decision_trace_response(*, trace_kind: str = "decision") -> DecisionTraceResponse:
    scope = QueryScope(vault_ids=("default",), content_scopes=("wiki",))
    decision = typed_entity(
        make_entity(
            "default",
            name="Use GraphRAG",
            document_id="decision-doc",
            chunk_id="decision-chunk",
            content_hash="decision-hash",
            path="wiki/decisions/use-graphrag.md",
        ),
        entity_type="Decision" if trace_kind == "decision" else "Concept",
    )
    target = make_entity(
        "default",
        name="Search",
        document_id="search-doc",
        chunk_id="search-chunk",
        content_hash="search-hash",
        path="wiki/search.md",
    )
    relationship = relationship_with_type(decision, target, "depends_on")
    decision_evidence = EvidenceReference(
        vault_id="default",
        document_id="decision-doc",
        chunk_id="decision-chunk",
        path="wiki/decisions/use-graphrag.md",
        section="Decision",
        anchor="decision",
        content_hash="decision-hash",
        raw_sha256="decision-raw",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )
    relationship_evidence = EvidenceReference(
        vault_id="default",
        document_id="search-doc",
        chunk_id="search-chunk",
        path="wiki/search.md",
        section="Dependency",
        anchor="dependency",
        content_hash="search-hash",
        raw_sha256="search-raw",
        metadata_index_revision="metadata-1",
        vault_revision="vault-1",
    )
    warnings: tuple[GraphRetrievalWarning, ...] = ()
    if trace_kind == "topic":
        warnings = (
            GraphRetrievalWarning(
                code="topic_not_durable_decision",
                message="Graph target is not a durable Decision entity.",
                severity="warning",
                affected_vault_ids=("default",),
                entity_id=decision.entity_id,
            ),
        )
    return DecisionTraceResponse(
        topic="Use GraphRAG" if trace_kind == "decision" else "GraphRAG",
        trace_kind=trace_kind,  # type: ignore[arg-type]
        resolved_target=decision,
        target_candidates=(decision,),
        requested_scope=scope,
        actual_scopes=(scope,),
        projection_build_id="trace-build-1",
        graph_projection_version=GRAPH_PROJECTION_VERSION,
        steps=(
            DecisionTraceStep(
                rank=1,
                role=trace_kind,
                entity=decision,
                relationship_path=(),
                evidence=(decision_evidence,),
                relationship_status="not_applicable",
                explanation=f"{trace_kind} identity evidence",
            ),
            DecisionTraceStep(
                rank=2,
                role="depends_on",
                entity=target,
                relationship_path=(relationship,),
                evidence=(relationship_evidence,),
                relationship_status="stated",
                explanation="1-edge graph path via depends_on",
            ),
        ),
        warnings=warnings,
        store_revisions=(
            GraphRetrievalRevision(
                kind="graph",
                revision="graph-1",
                scope_key="default:wiki:local",
                vault_id="default",
            ),
            GraphRetrievalRevision(kind="projection", revision="trace-build-1", scope_key="projection"),
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
