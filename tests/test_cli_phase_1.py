from pathlib import Path

from typer.testing import CliRunner

from vault_graph.cli.main import app

runner = CliRunner()


def test_cli_init_creates_default_catalog(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    assert result.exit_code == 0
    assert "default" in result.stdout
    assert (state_path / "configs" / "vaults.yaml").exists()


def test_cli_index_dry_run_reports_scope(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--dry-run"])

    assert result.exit_code == 0
    assert "vault_ids: default" in result.stdout
    assert "changed: 1" in result.stdout
    assert not (state_path / "metadata").exists()


def test_cli_vault_add_and_list(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(first), "--state", str(state_path)])

    add_result = runner.invoke(app, ["vault", "add", "work", "--path", str(second), "--state", str(state_path)])
    list_result = runner.invoke(app, ["vault", "list", "--state", str(state_path)])

    assert add_result.exit_code == 0
    assert list_result.exit_code == 0
    assert "default" in list_result.stdout
    assert "work" in list_result.stdout


def test_cli_index_rejects_conflicting_vault_scope_options(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault-id", "first", "--vault", str(first), "--state", str(state_path)])
    runner.invoke(app, ["vault", "add", "second", "--path", str(second), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--vault-id", "first", "--all-vaults"])

    assert result.exit_code != 0
    assert "Use either --vault-id or --all-vaults" in result.stdout
    assert not (state_path / "metadata").exists()


def test_cli_index_accepts_full_option(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--full"])

    assert result.exit_code == 0
    assert "mode: full" in result.stdout


def test_cli_index_renders_unknown_vault_id_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["index", "--state", str(state_path), "--vault-id", "missing", "--dry-run"])

    assert result.exit_code != 0
    assert "unknown vault_id: missing" in result.stdout


def test_cli_vault_add_renders_duplicate_error(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["vault", "add", "default", "--path", str(vault_root), "--state", str(state_path)])

    assert result.exit_code != 0
    assert "duplicate vault_id" in result.stdout


def test_cli_status_reports_paths_and_schema_health(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert f"state: {state_path.resolve()}" in result.stdout
    assert f"default {vault_root.resolve()}" in result.stdout
    assert "metadata_schema_compatible: False" in result.stdout


def test_cli_status_reports_schema_incompatible_sqlite_file(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    state_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--state", str(state_path)])
    metadata_path = state_path / "metadata" / "metadata.sqlite3"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text("not sqlite", encoding="utf-8")

    result = runner.invoke(app, ["status", "--state", str(state_path)])

    assert result.exit_code == 0
    assert "metadata_ok: False" in result.stdout
