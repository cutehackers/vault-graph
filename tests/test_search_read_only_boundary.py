from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_search_missing_indexes_does_not_create_metadata_or_vector_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["search", "--state", str(state_path), "Body"])

    assert result.exit_code == 1
    assert not (state_path / "metadata" / "metadata.sqlite3").exists()
    assert not (state_path / "vector" / "chroma" / "chroma.sqlite3").exists()
    assert not (state_path / "vector" / "status.json").exists()


def test_successful_search_does_not_mutate_existing_state_or_vault(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from tests.test_cli_search import _deterministic_text_embeddings

    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    monkeypatch.setattr("vault_graph.cli.main._search_text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nGraphRAG evidence\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    runner.invoke(app, ["index", "--state", str(state_path)])
    before_vault = _tree_snapshot(vault_root)
    before_state = _tree_snapshot(state_path)

    result = runner.invoke(app, ["search", "--state", str(state_path), "GraphRAG"])

    assert result.exit_code == 0
    assert _tree_snapshot(vault_root) == before_vault
    assert _tree_snapshot(state_path) == before_state


def _tree_snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
