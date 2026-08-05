import shutil
from pathlib import Path

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.fakes.deterministic_text_embeddings import DeterministicTextEmbeddings
from tests.test_vector_indexer import SPEC
from vault_graph.cli.main import app


class _ConfiguredDeterministicTextEmbeddings(DeterministicTextEmbeddings):
    class Config:
        embedding_batch_size = 256
        embedding_parallelism = None
        embedding_lazy_load = True

    config = Config()


def _fake_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    return _ConfiguredDeterministicTextEmbeddings(SPEC)


def file_bytes(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_index_commands_do_not_modify_vault_files(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.cli.main._text_embeddings", _fake_text_embeddings)
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("---\ntitle: Page\n---\n# Page\nBody\n", encoding="utf-8")
    graph_home_path = tmp_path / "state"
    runner = CliRunner()
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    before = file_bytes(vault_root)

    dry_run = runner.invoke(app, ["index", "--graph-home", str(graph_home_path), "--dry-run"])
    apply = runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    assert dry_run.exit_code == 0
    assert apply.exit_code == 0
    assert file_bytes(vault_root) == before


def test_init_rejects_graph_home_path_inside_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = vault_root / ".vault-graph"
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "Vault Graph Data Home must not be inside a registered Vault" in result.stdout
    assert not graph_home_path.exists()


def test_index_rejects_loaded_catalog_when_graph_home_path_is_inside_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = vault_root / ".vault-graph"
    (graph_home_path / "configs").mkdir(parents=True)
    (graph_home_path / "configs" / "vaults.yaml").write_text(
        "\n".join(
            [
                "active_vault_id: default",
                "vaults:",
                "  - vault_id: default",
                f"    root_path: {vault_root}",
                "    display_name: default",
                "    enabled: true",
                "    content_scopes: [wiki]",
                "    state_namespace: default",
                "    git_revision_policy: head",
            ]
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    result = runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "legacy_data_home_detected" in result.stdout
    assert not (graph_home_path / "metadata").exists()


def test_init_rejects_config_symlink_redirect_into_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "docs").mkdir(parents=True)
    graph_home_path = tmp_path / "state"
    graph_home_path.mkdir()
    (graph_home_path / "configs").symlink_to(vault_root / "docs", target_is_directory=True)
    runner = CliRunner()

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "Vault Graph write target must stay inside the Data Home" in result.stdout


def test_index_rejects_metadata_symlink_redirect_into_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    graph_home_path = tmp_path / "state"
    runner = CliRunner()
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)]).exit_code == 0
    shutil.rmtree(graph_home_path / "projections" / "generations")
    (graph_home_path / "projections" / "generations").symlink_to(vault_root / "wiki", target_is_directory=True)

    result = runner.invoke(app, ["index", "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "projection generation path" in result.stdout
    assert not (vault_root / "wiki" / "metadata.sqlite3").exists()


def test_status_with_graph_readiness_does_not_modify_vault_or_create_graph_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    graph_home_path = tmp_path / "state"
    runner = CliRunner()
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])
    before = file_bytes(vault_root)

    result = runner.invoke(app, ["status", "--graph-home", str(graph_home_path)])

    assert result.exit_code == 0
    assert file_bytes(vault_root) == before
    assert not (graph_home_path / "metadata").exists()
    assert not (graph_home_path / "vector").exists()
    assert not (graph_home_path / "graph").exists()
    assert not (graph_home_path / "projection_cache").exists()
