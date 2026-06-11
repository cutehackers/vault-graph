import json
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
from vault_graph.cli.main import _search_text_embeddings, app

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _ConfiguredDeterministicTextEmbeddings(SPEC)


class _UnavailableSearchTextEmbeddings(_ConfiguredDeterministicTextEmbeddings):
    def can_embed_without_download(self) -> bool:
        return False


def _unavailable_search_text_embeddings(_: object) -> _UnavailableSearchTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _UnavailableSearchTextEmbeddings(SPEC)


def test_cli_search_uses_active_vault_by_default(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "wiki/page.md" in result.stdout
    assert "GraphRAG evidence" in result.stdout


def test_cli_search_text_output_prints_resolved_scope_for_zero_results(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _unavailable_search_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "missing"])

    assert result.exit_code == 0
    assert "vault_ids: default" in result.stdout
    assert "actual_scopes: default:raw,wiki,docs,scratch/reports" in result.stdout
    assert "results: 0" in result.stdout


def test_cli_search_json_uses_search_response_contract(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "--format", "json", "GraphRAG"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["query_text"] == "GraphRAG"
    assert payload["result_count"] == 1
    assert payload["results"][0]["vault_id"] == "default"
    assert payload["results"][0]["kind"] == "evidence_chunk"
    assert payload["warnings"] == []


def test_cli_search_after_graph_indexing_does_not_expose_graph_expansion(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    index_result = runner.invoke(app, ["index", "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert index_result.exit_code == 0
    assert result.exit_code == 0
    assert "results:" in result.stdout
    assert "graph_" not in result.stdout
    assert "related" not in result.stdout
    assert "decision-trace" not in result.stdout
    assert "include_graph" not in result.stdout


def test_cli_search_scope_flags_are_mutually_exclusive(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(
        app, ["search", "--state", str(state_path), "--vault-id", "default", "--all-vaults", "GraphRAG"]
    )

    assert result.exit_code == 1
    assert "Use either --vault-id or --all-vaults" in result.stdout


def test_cli_search_missing_keyword_projection_exits_nonzero_without_writes(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 1
    assert "keyword_index_unavailable" in result.stdout or "metadata_unavailable" in result.stdout
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()


def test_search_text_embeddings_uses_local_files_only(tmp_path: Path) -> None:
    from vault_graph.app.catalog_service import CatalogService

    config = CatalogService(state_path=tmp_path / "state", embedding_cache_path=tmp_path / "embedding-cache")

    embeddings = _search_text_embeddings(config)

    assert embeddings.config.local_files_only is True
