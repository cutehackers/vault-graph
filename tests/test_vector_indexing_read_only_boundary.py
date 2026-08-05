from pathlib import Path

from typer.testing import CliRunner

from vault_graph.app.catalog_service import CatalogService
from vault_graph.cli.main import app
from vault_graph.errors import ReadOnlyBoundaryError

runner = CliRunner()


def test_vector_graph_home_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = vault_root / ".vault-graph"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "Data Home must not be inside a registered Vault" in result.stdout


def test_graph_graph_home_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    graph_home_path = vault_root / ".vault-graph"

    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    assert result.exit_code != 0
    assert "Data Home must not be inside a registered Vault" in result.stdout


def test_dry_run_does_not_create_vector_or_metadata_state(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    graph_home_path = tmp_path / "state"
    runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(graph_home_path)])

    result = runner.invoke(app, ["index", "--graph-home", str(graph_home_path), "--dry-run"])

    assert result.exit_code == 0
    assert not (graph_home_path / "metadata").exists()
    assert not (graph_home_path / "vector").exists()
    assert (vault_root / "wiki" / "page.md").read_text(encoding="utf-8") == "# Page\nBody\n"


def test_search_and_ask_are_exposed_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "search" in result.output
    assert "ask" in result.output


def test_embedding_cache_path_cannot_be_inside_vault_root(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    config = CatalogService(
        graph_home_path=tmp_path / "state",
        embedding_cache_path=vault_root / ".cache" / "vault-graph" / "embeddings",
    )
    catalog = config.create_default_catalog(vault_root=vault_root)

    try:
        config.assert_cache_target_safe(target_path=config.embedding_cache_path, catalog=catalog)
    except ReadOnlyBoundaryError as exc:
        assert "must not be inside a registered Vault" in str(exc)
    else:
        raise AssertionError("cache path inside a Vault root should fail")
