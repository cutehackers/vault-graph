"""Rerank presets, `configs/reranker.json`, and `vg reranker use/off` (spec 2026-11-13 D5, D9, D10, D18, A8, A19).

Every CLI test replaces `huggingface_hub` with a fake module, so no model file is downloaded.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import types
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

from vault_graph.errors import CatalogError
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.rerank_presets import (
    RERANK_PRESETS,
    RerankModelUnavailableError,
    RerankPreset,
)
from vault_graph.interface.composition.adapters.text_cross_encoder import TextCrossEncoderReranker
from vault_graph.operation.scope.reranker_selection import (
    RerankerSelection,
    load_reranker_selection,
    reranker_config_path,
    save_reranker_selection,
)

runner = CliRunner()

_MMARCO_REVISION = "1427fd652930e4ba29e8149678df786c240d8825"


class FakeHub:
    """Stand-in for `huggingface_hub.snapshot_download`."""

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.calls: list[dict[str, object]] = []
        self.downloaded: set[tuple[str, str]] = set()
        self.fail_download = False

    def snapshot_download(self, **kwargs: object) -> str:
        self.calls.append(kwargs)
        key = (str(kwargs["repo_id"]), str(kwargs["cache_dir"]))
        if kwargs["local_files_only"]:
            if key not in self.downloaded:
                raise FileNotFoundError("not in cache")
        else:
            if self.fail_download:
                raise OSError("offline")
            self.downloaded.add(key)
        return str(self.tmp_path / "snapshot")

    def download_calls(self) -> list[dict[str, object]]:
        return [call for call in self.calls if not call["local_files_only"]]


@pytest.fixture
def hub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeHub:
    fake = FakeHub(tmp_path)
    module = types.ModuleType("huggingface_hub")
    cast(Any, module).snapshot_download = fake.snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    monkeypatch.setenv("HOME", str(tmp_path / "user-home"))
    return fake


@pytest.fixture
def home(tmp_path: Path) -> Path:
    vault_root = tmp_path / "vault"
    (vault_root / "wiki").mkdir(parents=True)
    (vault_root / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    path = tmp_path / "graph-home"
    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(path)])
    assert result.exit_code == 0, result.output
    return path


def _settings(home: Path) -> Path:
    return home / "configs" / "reranker.json"


def _use_embedding_models_dir(home: Path, models_dir: Path) -> None:
    payload = {"version": 1, "model": "arctic-m", "models_dir": str(models_dir)}
    (home / "configs" / "embedding.json").write_text(json.dumps(payload), encoding="utf-8")


# A19, D18
def test_presets_hold_only_mmarco_arm64_int8_at_a_pinned_revision() -> None:
    assert list(RERANK_PRESETS) == ["mmarco"]
    preset = RERANK_PRESETS["mmarco"]
    assert preset.repo_id == "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    assert preset.model_name == preset.repo_id
    assert preset.revision == _MMARCO_REVISION
    assert preset.model_file == "onnx/model_qint8_arm64.onnx"
    assert preset.files == (
        "onnx/model_qint8_arm64.onnx",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    )
    assert preset.file_bytes == {
        "onnx/model_qint8_arm64.onnx": 118_620_017,
        "tokenizer.json": 17_082_660,
        "config.json": 891,
        "tokenizer_config.json": 435,
        "special_tokens_map.json": 239,
    }
    assert preset.download_mb == 136
    assert all("bge" not in name for name in RERANK_PRESETS)


# D9
def test_missing_settings_file_means_off_and_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "configs" / "reranker.json"

    assert load_reranker_selection(path) == RerankerSelection(enabled=False, model=None)
    assert not path.exists()


def test_settings_round_trip_uses_version_enabled_and_model(tmp_path: Path) -> None:
    path = tmp_path / "configs" / "reranker.json"

    save_reranker_selection(path, RerankerSelection(enabled=True, model="mmarco"))

    assert json.loads(path.read_text(encoding="utf-8")) == {"version": 1, "enabled": True, "model": "mmarco"}
    assert load_reranker_selection(path) == RerankerSelection(enabled=True, model="mmarco")
    assert reranker_config_path(tmp_path) == path


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"version": 1, "enabled": True},
        {"version": 1, "enabled": True, "model": "mmarco", "extra": 1},
        {"version": 2, "enabled": True, "model": "mmarco"},
        {"version": 1, "enabled": "yes", "model": "mmarco"},
        {"version": 1, "enabled": True, "model": ""},
        {"version": 1, "enabled": True, "model": None},
    ],
)
def test_invalid_settings_file_names_the_path(tmp_path: Path, payload: object) -> None:
    path = tmp_path / "reranker.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CatalogError, match=str(path)):
        load_reranker_selection(path)


def test_settings_file_that_is_not_json_names_the_path(tmp_path: Path) -> None:
    path = tmp_path / "reranker.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(CatalogError, match="not valid JSON"):
        load_reranker_selection(path)


# D10, A8
def test_use_downloads_pinned_files_into_embedding_models_dir_then_turns_on(
    hub: FakeHub, home: Path, tmp_path: Path
) -> None:
    models_dir = tmp_path / "models"
    _use_embedding_models_dir(home, models_dir)

    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    preset = RERANK_PRESETS["mmarco"]
    [download] = hub.download_calls()
    assert download["repo_id"] == preset.repo_id
    assert download["revision"] == _MMARCO_REVISION
    assert download["allow_patterns"] == list(preset.files)
    assert download["cache_dir"] == str(models_dir)
    assert json.loads(_settings(home).read_text(encoding="utf-8")) == {
        "version": 1,
        "enabled": True,
        "model": "mmarco",
    }
    assert "download: done" in result.output


def test_use_defaults_to_the_default_models_dir_without_embedding_settings(
    hub: FakeHub, home: Path, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    [download] = hub.download_calls()
    assert download["cache_dir"] == str(tmp_path / "user-home" / "llm" / "models")
    assert not (home / "configs" / "embedding.json").exists()


def test_use_does_not_download_files_already_present(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _use_embedding_models_dir(home, models_dir)
    hub.downloaded.add((RERANK_PRESETS["mmarco"].repo_id, str(models_dir)))

    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    assert hub.download_calls() == []
    [lookup] = hub.calls
    assert lookup["revision"] == _MMARCO_REVISION
    assert "download: already present" in result.output
    assert json.loads(_settings(home).read_text(encoding="utf-8"))["enabled"] is True


def test_failed_download_leaves_the_settings_file_unchanged(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    _use_embedding_models_dir(home, tmp_path / "models")
    save_reranker_selection(_settings(home), RerankerSelection(enabled=False, model="mmarco"))
    before = _settings(home).read_bytes()
    hub.fail_download = True

    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)])

    assert result.exit_code == 1
    assert "offline" in result.output
    assert _settings(home).read_bytes() == before


def test_failed_download_does_not_create_the_settings_file(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    _use_embedding_models_dir(home, tmp_path / "models")
    hub.fail_download = True

    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)])

    assert result.exit_code == 1
    assert not _settings(home).exists()


def test_use_rejects_an_unknown_preset_without_downloading(hub: FakeHub, home: Path) -> None:
    result = runner.invoke(app, ["reranker", "use", "bge", "--graph-home", str(home)])

    assert result.exit_code == 1
    assert "unknown reranker model 'bge'" in result.output
    assert "mmarco" in result.output
    assert hub.calls == []
    assert not _settings(home).exists()


def test_off_turns_off_only_enabled(hub: FakeHub, home: Path) -> None:
    save_reranker_selection(_settings(home), RerankerSelection(enabled=True, model="mmarco"))

    result = runner.invoke(app, ["reranker", "off", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    assert json.loads(_settings(home).read_text(encoding="utf-8")) == {
        "version": 1,
        "enabled": False,
        "model": "mmarco",
    }
    assert hub.calls == []


def test_off_without_settings_file_writes_nothing(hub: FakeHub, home: Path) -> None:
    result = runner.invoke(app, ["reranker", "off", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    assert not _settings(home).exists()
    assert hub.calls == []


def test_use_requires_an_initialized_graph_home(hub: FakeHub, tmp_path: Path) -> None:
    result = runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(tmp_path / "missing")])

    assert result.exit_code == 1
    assert "graph_home_not_initialized" in result.output
    assert hub.calls == []


class _ScoreByLength:
    def rerank(self, query: str, documents: Iterable[str]) -> list[float]:
        return [float(len(document)) for document in documents]


class _WordTokenizer:
    def encode(self, text: str, add_special_tokens: bool = True) -> types.SimpleNamespace:
        return types.SimpleNamespace(offsets=[match.span() for match in re.finditer(r"\S+", text)])


def _search_adapter(models_dir: Path, built: list[tuple[str, Path]]) -> TextCrossEncoderReranker:
    def encoder_factory(preset: RerankPreset, snapshot: Path) -> _ScoreByLength:
        built.append((preset.name, snapshot))
        return _ScoreByLength()

    return TextCrossEncoderReranker(
        RERANK_PRESETS["mmarco"],
        models_dir,
        encoder_factory=encoder_factory,
        tokenizer_loader=lambda snapshot: _WordTokenizer(),
    )


# A8, I2: search only looks up local files and never swaps in another model.
def test_search_adapter_without_model_files_does_not_download_or_fall_back(hub: FakeHub, tmp_path: Path) -> None:
    built: list[tuple[str, Path]] = []
    reranker = _search_adapter(tmp_path / "models", built)

    with pytest.raises(RerankModelUnavailableError, match="mmarco"):
        reranker.rerank("query", ["a", "bb"])

    assert hub.calls
    assert all(call["local_files_only"] is True for call in hub.calls)
    assert {call["repo_id"] for call in hub.calls} == {RERANK_PRESETS["mmarco"].repo_id}
    assert {call["revision"] for call in hub.calls} == {_MMARCO_REVISION}
    assert built == []


def test_search_adapter_finds_files_from_use_without_downloading(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    _use_embedding_models_dir(home, models_dir)
    assert runner.invoke(app, ["reranker", "use", "mmarco", "--graph-home", str(home)]).exit_code == 0
    assert runner.invoke(app, ["reranker", "off", "--graph-home", str(home)]).exit_code == 0
    downloads_before = len(hub.download_calls())
    built: list[tuple[str, Path]] = []

    order = _search_adapter(models_dir, built).rerank("query", ["a", "bbb", "bb"])

    assert order == [1, 2, 0]
    assert built == [("mmarco", tmp_path / "snapshot")]
    assert len(hub.download_calls()) == downloads_before
    assert hub.calls[-1]["local_files_only"] is True
    assert hub.calls[-1]["cache_dir"] == str(models_dir)


# D10: importing the modules prepares no model and touches no network.
def test_importing_reranker_modules_does_not_load_model_libraries() -> None:
    code = (
        "import sys\n"
        "import vault_graph.interface.composition.adapters.rerank_presets\n"
        "import vault_graph.operation.scope.reranker_selection\n"
        "import vault_graph.interface.cli.reranker_commands\n"
        "print(sorted(name for name in ('huggingface_hub', 'fastembed', 'onnxruntime') if name in sys.modules))\n"
    )
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)

    assert completed.stdout.strip() == "[]"
