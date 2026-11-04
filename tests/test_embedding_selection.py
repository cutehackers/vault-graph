import json
import os
import re
from pathlib import Path

import pytest

from vault_graph.errors import CatalogError
from vault_graph.operation.scope.embedding_selection import (
    DEFAULT_MODELS_DIR,
    EmbeddingSelection,
    load_embedding_selection,
    save_embedding_selection,
)


def _config_path(tmp_path: Path) -> Path:
    return tmp_path / "configs" / "embedding.json"


def test_default_models_dir_is_llm_models_under_home() -> None:
    assert DEFAULT_MODELS_DIR == Path("~/llm/models")


def test_missing_file_returns_default_and_creates_nothing(tmp_path: Path) -> None:
    path = _config_path(tmp_path)

    selection = load_embedding_selection(path)

    assert selection == EmbeddingSelection(model=None, models_dir=DEFAULT_MODELS_DIR)
    assert list(tmp_path.iterdir()) == []


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    models_dir = tmp_path / "models"

    save_embedding_selection(path, EmbeddingSelection(model="e5-small", models_dir=models_dir))

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "version": 1,
        "model": "e5-small",
        "models_dir": str(models_dir),
    }
    assert load_embedding_selection(path) == EmbeddingSelection(model="e5-small", models_dir=models_dir)


def test_save_round_trips_unset_model(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    selection = EmbeddingSelection(model=None, models_dir=tmp_path / "models")

    save_embedding_selection(path, selection)

    assert load_embedding_selection(path) == selection


def test_save_writes_temporary_file_then_replaces(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = _config_path(tmp_path)
    calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def recording_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        calls.append((os.fspath(source), os.fspath(target)))
        assert Path(source).parent == path.parent
        assert json.loads(Path(source).read_text(encoding="utf-8"))["model"] == "arctic-l"
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", recording_replace)

    save_embedding_selection(path, EmbeddingSelection(model="arctic-l", models_dir=tmp_path / "models"))

    assert len(calls) == 1
    assert calls[0][0] != os.fspath(path)
    assert Path(calls[0][1]) == path
    assert sorted(p.name for p in path.parent.iterdir()) == ["embedding.json"]


def test_save_rejects_relative_models_dir(tmp_path: Path) -> None:
    path = _config_path(tmp_path)

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        save_embedding_selection(path, EmbeddingSelection(model="arctic-l", models_dir=Path("~/llm/models")))

    assert not path.exists()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("not json", id="not-json"),
        pytest.param("[1, 2]", id="not-object"),
        pytest.param('{"version": 2, "model": "arctic-l", "models_dir": "/m"}', id="version-2"),
        pytest.param('{"version": "1", "model": "arctic-l", "models_dir": "/m"}', id="version-string"),
        pytest.param('{"version": true, "model": "arctic-l", "models_dir": "/m"}', id="version-bool"),
        pytest.param('{"model": "arctic-l", "models_dir": "/m"}', id="version-missing"),
        pytest.param('{"version": 1, "model": "arctic-l", "models_dir": "/m", "extra": 1}', id="unknown-key"),
        pytest.param('{"version": 1, "model": 3, "models_dir": "/m"}', id="model-int"),
        pytest.param('{"version": 1, "model": "", "models_dir": "/m"}', id="model-empty"),
        pytest.param('{"version": 1, "model": "arctic-l", "models_dir": 5}', id="models-dir-int"),
        pytest.param('{"version": 1, "model": "arctic-l", "models_dir": "relative/m"}', id="models-dir-relative"),
        pytest.param('{"version": 1, "model": "arctic-l"}', id="models-dir-missing"),
    ],
)
def test_load_rejects_invalid_content_and_names_path(tmp_path: Path, content: str) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        load_embedding_selection(path)

    assert path.read_bytes() == before


def test_load_rejects_file_over_4_kib(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True)
    payload = json.dumps({"version": 1, "model": "arctic-l", "models_dir": "/" + "m" * 4096})
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        load_embedding_selection(path)


def test_load_accepts_file_of_exactly_4_kib(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True)
    base = json.dumps({"version": 1, "model": "arctic-l", "models_dir": "/"})
    padding = 4096 - len(base.encode("utf-8"))
    path.write_text(base[:-1] + " " * padding + "}", encoding="utf-8")
    assert path.stat().st_size == 4096

    assert load_embedding_selection(path).model == "arctic-l"


def test_load_rejects_directory(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.mkdir(parents=True)

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        load_embedding_selection(path)


def test_load_rejects_symlink(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True)
    target = tmp_path / "real.json"
    target.write_text(json.dumps({"version": 1, "model": "arctic-l", "models_dir": "/m"}), encoding="utf-8")
    path.symlink_to(target)

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        load_embedding_selection(path)


def test_load_rejects_fifo(tmp_path: Path) -> None:
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True)
    os.mkfifo(path)

    with pytest.raises(CatalogError, match=re.escape(str(path))):
        load_embedding_selection(path)
