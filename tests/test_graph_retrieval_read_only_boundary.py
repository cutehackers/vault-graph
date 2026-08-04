from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_search import _deterministic_text_embeddings, write_page
from vault_graph.cli.main import app

runner = CliRunner()


def test_related_does_not_create_missing_state_files(tmp_path: Path) -> None:
    graph_home_path = _initialized_state(tmp_path)
    before = state_tree(graph_home_path)

    result = runner.invoke(app, ["related", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "warning: graph_missing [default]" in result.stdout
    assert state_tree(graph_home_path) == before
    assert _missing_read_graph_home_paths(graph_home_path)


def test_decision_trace_does_not_create_missing_state_files(tmp_path: Path) -> None:
    graph_home_path = _initialized_state(tmp_path)
    before = state_tree(graph_home_path)

    result = runner.invoke(app, ["decision-trace", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "warning: graph_missing [default]" in result.stdout
    assert state_tree(graph_home_path) == before
    assert _missing_read_graph_home_paths(graph_home_path)


def test_search_include_graph_does_not_create_missing_state_files(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    graph_home_path = _initialized_state(tmp_path)
    before = state_tree(graph_home_path)

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "--include-graph", "GraphRAG"])

    assert result.exit_code == 1
    assert "metadata_unavailable" in result.stdout or "keyword_index_unavailable" in result.stdout
    assert state_tree(graph_home_path) == before
    assert _missing_read_graph_home_paths(graph_home_path)


def test_search_include_graph_does_not_auto_index(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    before = state_tree(graph_home_path)

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "--include-graph", "GraphRAG"])

    assert result.exit_code == 1
    assert "metadata_unavailable" in result.stdout or "keyword_index_unavailable" in result.stdout
    assert state_tree(graph_home_path) == before
    assert not (graph_home_path / "metadata" / "metadata.sqlite3").exists()
    assert not (graph_home_path / "graph" / "graph.sqlite3").exists()
    assert not (graph_home_path / "data" / "projection_cache").exists()


def test_plain_search_does_not_open_graph_retrieval_factory(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)

    def fail_graph_factory(_: Path) -> object:
        raise AssertionError("plain search must not open graph retrieval state")

    monkeypatch.setattr("vault_graph.cli.main._graph_retrieval_service", fail_graph_factory)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["search", "--graph-home", str(graph_home_path), "GraphRAG"])

    assert result.exit_code == 0
    assert "wiki/page.md" in result.stdout


def _initialized_state(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = tmp_path / "state"
    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    assert result.exit_code == 0
    return graph_home_path


def _missing_read_graph_home_paths(graph_home_path: Path) -> bool:
    return not any(
        path.exists()
        for path in (
            graph_home_path / "metadata" / "metadata.sqlite3",
            graph_home_path / "vector",
            graph_home_path / "graph" / "graph.sqlite3",
            graph_home_path / "graph" / "status.json",
            graph_home_path / "data" / "projection_cache",
        )
    )


def state_tree(path: Path) -> tuple[str, ...]:
    if not path.exists():
        return ()
    return tuple(sorted(str(child.relative_to(path)) for child in path.rglob("*")))
