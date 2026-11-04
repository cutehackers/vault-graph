"""A bad embedding settings file stops every command that builds the embedding model (spec 6, A-14)."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
from vault_graph.errors import ReadOnlyBoundaryError, TextEmbeddingsError
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters import text_embeddings as adapter
from vault_graph.interface.composition.adapters.text_embeddings import text_embeddings_for
from vault_graph.interface.composition.recall_index_refresh import vectors_need_catch_up
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import EmbeddingSelection, save_embedding_selection

runner = CliRunner()

BAD_SETTINGS = {
    "not-json": b"{not json",
    "version-2": json.dumps({"version": 2, "model": "arctic-l", "models_dir": "/tmp/models"}).encode(),
    "unknown-key": json.dumps({"version": 1, "model": "arctic-l", "models_dir": "/tmp/models", "extra": True}).encode(),
    "unknown-preset": json.dumps({"version": 1, "model": "nope", "models_dir": "/tmp/models"}).encode(),
}


def _deterministic_text_embeddings(_: object) -> _ConfiguredDeterministicTextEmbeddings:
    from tests.test_vector_indexer import SPEC

    return _ConfiguredDeterministicTextEmbeddings(SPEC)


@pytest.fixture
def no_model_load(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_: object) -> Path:
        raise AssertionError("no model may be resolved or loaded with a bad settings file")

    monkeypatch.setattr(adapter, "_resolve_snapshot", fail)
    monkeypatch.setattr(adapter, "_default_backend_factory", fail)


@pytest.fixture
def indexed_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nGraphRAG evidence\n", encoding="utf-8")
    home = tmp_path / "home"
    with monkeypatch.context() as patch:
        patch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)
        assert runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(home)]).exit_code == 0
        result = runner.invoke(app, ["index", "--graph-home", str(home)])
        assert result.exit_code == 0, result.output
    return home


def _write_settings(home: Path, raw: bytes) -> Path:
    path = home / "configs" / "embedding.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


@pytest.mark.parametrize("case", sorted(BAD_SETTINGS))
def test_text_embeddings_for_raises_text_embeddings_error_with_the_path(tmp_path: Path, case: str) -> None:
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    path = _write_settings(catalog_service.graph_home_path, BAD_SETTINGS[case])

    with pytest.raises(TextEmbeddingsError) as caught:
        text_embeddings_for(catalog_service, local_files_only=True)

    assert str(path) in str(caught.value)
    assert path.read_bytes() == BAD_SETTINGS[case]


def test_unknown_preset_error_lists_the_available_names(tmp_path: Path) -> None:
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    _write_settings(catalog_service.graph_home_path, BAD_SETTINGS["unknown-preset"])

    with pytest.raises(TextEmbeddingsError, match="'nope'") as caught:
        text_embeddings_for(catalog_service, local_files_only=False)

    for name in ("arctic-l", "e5-small", "minilm"):
        assert name in str(caught.value)


@pytest.mark.parametrize("case", sorted(BAD_SETTINGS))
@pytest.mark.parametrize("command", ["search", "index"])
def test_search_and_index_stop_on_a_bad_settings_file(
    indexed_home: Path, no_model_load: None, case: str, command: str
) -> None:
    path = _write_settings(indexed_home, BAD_SETTINGS[case])
    active = (indexed_home / "projections" / "active.json").read_bytes()
    arguments = [command, "--graph-home", str(indexed_home)] + (["GraphRAG"] if command == "search" else [])

    result = runner.invoke(app, arguments)

    assert result.exit_code != 0
    assert str(path) in result.output
    assert path.read_bytes() == BAD_SETTINGS[case]
    assert (indexed_home / "projections" / "active.json").read_bytes() == active


def test_background_index_decision_logs_a_bad_settings_file_and_starts_nothing(
    indexed_home: Path, no_model_load: None, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_settings(indexed_home, BAD_SETTINGS["version-2"])

    assert vectors_need_catch_up(indexed_home, "default") is False

    assert str(path) in capsys.readouterr().err


def test_index_checks_the_models_dir_from_the_settings_file(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\nBody\n", encoding="utf-8")
    home = tmp_path / "home"
    assert runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(home)]).exit_code == 0
    save_embedding_selection(
        home / "configs" / "embedding.json", EmbeddingSelection("minilm", (vault_root / "models").resolve())
    )

    result = runner.invoke(app, ["index", "--graph-home", str(home)])

    assert result.exit_code != 0
    assert "must not be inside a registered Vault" in result.output


def test_save_embedding_selection_writes_the_settings_file(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    catalog_service.create_default_catalog(vault_root=vault_root)

    catalog_service.save_embedding_selection(EmbeddingSelection("e5-small", tmp_path / "models"))

    assert catalog_service.embedding_config_path == catalog_service.graph_home_path / "configs" / "embedding.json"
    assert json.loads(catalog_service.embedding_config_path.read_text(encoding="utf-8")) == {
        "version": 1,
        "model": "e5-small",
        "models_dir": str(tmp_path / "models"),
    }


def test_save_embedding_selection_refuses_a_models_dir_inside_a_vault(tmp_path: Path) -> None:
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")
    catalog_service.create_default_catalog(vault_root=vault_root)

    with pytest.raises(ReadOnlyBoundaryError, match="must not be inside a registered Vault"):
        catalog_service.save_embedding_selection(EmbeddingSelection("e5-small", vault_root.resolve() / "models"))

    assert not catalog_service.embedding_config_path.exists()


def test_catalog_service_has_no_embedding_cache_path(tmp_path: Path) -> None:
    catalog_service = CatalogService(graph_home_path=tmp_path / "home")

    assert not hasattr(catalog_service, "embedding_cache_path")
