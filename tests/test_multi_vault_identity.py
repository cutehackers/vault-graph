from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore


def test_two_vaults_with_same_relative_path_do_not_collide(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    (first / "wiki").mkdir(parents=True)
    (second / "wiki").mkdir(parents=True)
    (first / "wiki" / "same.md").write_text("# Same\nFirst body\n", encoding="utf-8")
    (second / "wiki" / "same.md").write_text("# Same\nSecond body\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner = CliRunner()

    init_result = runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    add_result = runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])
    assert init_result.exit_code == 0
    assert add_result.exit_code == 0
    assert runner.invoke(app, ["index", "--all-vaults", "--state", str(state_path)]).exit_code == 0

    store = SQLiteMetadataStore(state_path / "metadata" / "metadata.sqlite3")
    first_state = store.document_state("first", "wiki/same.md")
    second_state = store.document_state("second", "wiki/same.md")

    assert first_state.document_id is not None
    assert second_state.document_id is not None
    assert first_state.document_id != second_state.document_id
    assert first_state.content_hash != second_state.content_hash
