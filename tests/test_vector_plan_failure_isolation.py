"""Spec 2026-11-05 §4.3.1 단기 수정: a vector plan failure is a vector result, not a crashed ``vg index``."""

from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.fakes.in_memory_vector_store import InMemoryVectorStore
from tests.test_cli_vector_indexing import _deterministic_text_embeddings, write_page
from tests.test_vector_indexer import SPEC, ChunkStore, chunk
from vault_graph.errors import VectorStoreError
from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager
from vault_graph.indexing.vector_index_adapter import VectorIndexer
from vault_graph.interface.cli.main import app
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.storage.interfaces.vector_store import VectorManifestRecord

runner = CliRunner()
_SQL_ERROR = "Error executing plan: Internal error: too many SQL variables"


class _ManifestFailingStore(InMemoryVectorStore):
    def export_manifest(self, scope: QueryScope) -> tuple[VectorManifestRecord, ...]:
        raise VectorStoreError(_SQL_ERROR)


def _raise_manifest_error(**_: object) -> tuple[object, ...]:
    raise VectorStoreError(_SQL_ERROR)


def test_plan_failure_becomes_a_failed_vector_result_at_the_plan_stage() -> None:
    indexer = VectorIndexer(
        chunk_store=ChunkStore((chunk(),)),
        vector_store=_ManifestFailingStore(),
        text_embeddings=DeterministicTextEmbeddings(SPEC),
    )

    result = indexer.apply(scopes=(QueryScope(vault_ids=("default",), content_scopes=("wiki",)),))

    assert result.failed is True
    assert result.failed_stage == "plan"
    assert _SQL_ERROR in (result.error or "")
    assert result.upsert_count == 0
    assert result.embedding_spec == SPEC


def test_vg_index_publishes_metadata_and_graph_when_the_vector_plan_fails(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    graph_home = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home)])
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
    assert runner.invoke(app, ["index", "--graph-home", str(graph_home)]).exit_code == 0
    manager = ProjectionGenerationManager(graph_home)
    first = manager.active_layout()
    assert first is not None

    write_page(vault_root, "wiki/page.md", "# Page\nChanged\n")
    monkeypatch.setattr("vault_graph.indexing.vector_index_adapter._manifest_for_scopes", _raise_manifest_error)
    result = runner.invoke(app, ["index", "--graph-home", str(graph_home)])

    assert result.exception is None or isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == 1
    assert "vector_failed: True" in result.stdout
    assert "too many SQL variables" in result.stdout
    second = manager.active_layout()
    assert second is not None and second != first
    bundle = json.loads((second.root_path / "bundle-manifest.json").read_text(encoding="utf-8"))
    revision_line = next(line for line in result.stdout.splitlines() if line.startswith("index_revision: "))
    assert bundle["component_revisions"]["metadata"] == revision_line.removeprefix("index_revision: ")
    assert "graph" in bundle["components"]
    assert "vector" not in bundle["components"]
