from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_cli_graph_indexing import _deterministic_text_embeddings
from vault_graph.cli.main import app

runner = CliRunner()


def write_page(root: Path, path: str, body: str) -> None:
    file_path = root / path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(body, encoding="utf-8")


def test_graph_dry_run_does_not_create_state_or_modify_vault(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before_vault = _tree_snapshot(vault_root)

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert _tree_snapshot(vault_root) == before_vault
    assert not (state_path / "metadata").exists()
    assert not (state_path / "vector").exists()
    assert not (state_path / "graph").exists()
    assert not (state_path / "projection_cache").exists()


def test_graph_apply_and_status_do_not_modify_vault_or_projection_cache(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _deterministic_text_embeddings)
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before_vault = _tree_snapshot(vault_root)

    index_result = runner.invoke(app, ["index", "--state", str(state_path)])
    before_status_state = _tree_snapshot(state_path)
    status_result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert index_result.exit_code == 0
    assert status_result.exit_code == 0
    assert _tree_snapshot(vault_root) == before_vault
    assert _tree_snapshot(state_path) == before_status_state
    assert not (state_path / "projection_cache").exists()


def test_graph_status_is_read_only_before_graph_indexing(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    write_page(vault_root, "wiki/page.md", "# Page\nBody\n")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    before_state = _tree_snapshot(state_path)

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert _tree_snapshot(state_path) == before_state
    assert not (state_path / "graph").exists()


def _tree_snapshot(root: Path) -> dict[str, tuple[int, bytes]]:
    return {
        str(path.relative_to(root)): (path.stat().st_size, path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
