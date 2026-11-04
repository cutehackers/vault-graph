"""`vg embedding list` and `vg embedding use` (spec 4.5, 6, A-8..A-10, A-17).

Every test replaces `huggingface_hub` with a fake module, so no model file is downloaded.
"""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest
import typer
from typer.testing import CliRunner

from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.text_embeddings import EMBEDDING_PRESETS
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.embedding_selection import EmbeddingSelection

runner = CliRunner()


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
def vault_root(tmp_path: Path) -> Path:
    root = tmp_path / "vault"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    return root


@pytest.fixture
def home(tmp_path: Path, vault_root: Path) -> Path:
    path = tmp_path / "graph-home"
    result = runner.invoke(app, ["init", "--vault", str(vault_root), "--graph-home", str(path)])
    assert result.exit_code == 0, result.output
    return path


def _settings(home: Path) -> Path:
    return home / "configs" / "embedding.json"


def _settings_bytes(home: Path) -> bytes | None:
    path = _settings(home)
    return path.read_bytes() if path.exists() else None


def _tree_digest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_use_downloads_the_preset_and_saves_an_absolute_models_dir(
    hub: FakeHub, home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["embedding", "use", "e5-small", "--models-dir", "models", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    models_dir = tmp_path / "models"
    assert json.loads(_settings(home).read_text(encoding="utf-8")) == {
        "version": 1,
        "model": "e5-small",
        "models_dir": str(models_dir),
    }
    preset = EMBEDDING_PRESETS["e5-small"]
    [download] = hub.download_calls()
    assert download["local_files_only"] is False
    assert download["repo_id"] == preset.repo_id
    assert download["revision"] == preset.revision
    assert download["allow_patterns"] == list(preset.files or ())
    assert download["cache_dir"] == str(models_dir)
    assert "vg index" in result.output
    assert "keyword results only" in result.output


def test_use_expands_tilde_in_models_dir(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["embedding", "use", "minilm", "--models-dir", "~/models", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    saved = json.loads(_settings(home).read_text(encoding="utf-8"))
    assert saved["models_dir"] == str(tmp_path / "user-home" / "models")


def test_use_without_models_dir_keeps_the_current_folder(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    current = tmp_path / "current-models"
    CatalogService(graph_home_path=home).save_embedding_selection(
        EmbeddingSelection(model="arctic-l", models_dir=current)
    )

    result = runner.invoke(app, ["embedding", "use", "e5-small", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    assert json.loads(_settings(home).read_text(encoding="utf-8"))["models_dir"] == str(current)


def test_use_without_settings_file_uses_the_default_folder(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["embedding", "use", "e5-small", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    saved = json.loads(_settings(home).read_text(encoding="utf-8"))
    assert saved["models_dir"] == str(tmp_path / "user-home" / "llm" / "models")


def test_use_does_not_download_a_model_that_is_already_in_the_folder(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    hub.downloaded.add((EMBEDDING_PRESETS["e5-small"].repo_id, str(models_dir)))

    result = runner.invoke(
        app, ["embedding", "use", "e5-small", "--models-dir", str(models_dir), "--graph-home", str(home)]
    )

    assert result.exit_code == 0, result.output
    assert hub.download_calls() == []
    assert json.loads(_settings(home).read_text(encoding="utf-8"))["model"] == "e5-small"


@pytest.mark.parametrize("existing_settings", [False, True])
@pytest.mark.parametrize("case", ["unknown-name", "download-fails", "models-dir-inside-vault"])
def test_use_failures_exit_non_zero_and_leave_settings_bytes_unchanged(
    hub: FakeHub, home: Path, vault_root: Path, tmp_path: Path, case: str, existing_settings: bool
) -> None:
    if existing_settings:
        CatalogService(graph_home_path=home).save_embedding_selection(
            EmbeddingSelection(model="minilm", models_dir=tmp_path / "old-models")
        )
    before = _settings_bytes(home)
    args = ["embedding", "use", "e5-small", "--models-dir", str(tmp_path / "models"), "--graph-home", str(home)]
    if case == "unknown-name":
        args[2] = "nope"
    elif case == "download-fails":
        hub.fail_download = True
    else:
        args[4] = str(vault_root / "models")

    result = runner.invoke(app, args)

    assert result.exit_code != 0
    assert _settings_bytes(home) == before
    if case == "unknown-name":
        assert "e5-small, arctic-l, minilm" in result.output
        assert hub.calls == []
    if case == "models-dir-inside-vault":
        assert hub.calls == []
        assert not (vault_root / "models").exists()


def test_list_json_shows_recommended_model_first_and_writes_nothing(hub: FakeHub, home: Path, tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    CatalogService(graph_home_path=home).save_embedding_selection(
        EmbeddingSelection(model="arctic-l", models_dir=models_dir)
    )
    hub.downloaded.add((EMBEDDING_PRESETS["arctic-l"].repo_id, str(models_dir)))
    before = _tree_digest(home)

    result = runner.invoke(app, ["embedding", "list", "--format", "json", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["settings_path"] == str(_settings(home))
    assert payload["models_dir"] == str(models_dir)
    models = payload["models"]
    assert [model["name"] for model in models] == ["e5-small", "arctic-l", "minilm"]
    assert [model["role"] for model in models] == ["recommended", "alternative", "alternative"]
    assert [model["selected"] for model in models] == [False, True, False]
    assert [model["downloaded"] for model in models] == [False, True, False]
    for model in models:
        preset = EMBEDDING_PRESETS[model["name"]]
        assert model["dimensions"] == preset.dimensions
        assert model["max_tokens"] == preset.max_tokens
        assert model["download_mb"] == preset.download_mb
        assert model["summary"] == preset.summary
    assert hub.calls
    assert all(call["local_files_only"] is True for call in hub.calls)
    assert _tree_digest(home) == before


def test_list_without_settings_file_selects_the_default_and_creates_nothing(
    hub: FakeHub, home: Path, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["embedding", "list", "--format", "json", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["models_dir"] == str(tmp_path / "user-home" / "llm" / "models")
    assert [model["selected"] for model in payload["models"]] == [True, False, False]
    assert not _settings(home).exists()
    assert not (tmp_path / "user-home").exists()


def test_list_text_shows_settings_path_folder_and_recommended_model_first(hub: FakeHub, home: Path) -> None:
    result = runner.invoke(app, ["embedding", "list", "--graph-home", str(home)])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == f"embedding_settings: {_settings(home)}"
    assert lines[1].startswith("models_dir: ")
    model_lines = [line for line in lines if line.startswith("model: ")]
    assert [line.split()[1] for line in model_lines] == ["e5-small", "arctic-l", "minilm"]
    assert "recommended" in model_lines[0] and "selected=yes" in model_lines[0]
    assert all("alternative" in line and "selected=no" in line for line in model_lines[1:])
    assert all("downloaded=no" in line for line in model_lines)


def test_list_rejects_unknown_format(hub: FakeHub, home: Path) -> None:
    result = runner.invoke(app, ["embedding", "list", "--format", "yaml", "--graph-home", str(home)])

    assert result.exit_code != 0


@pytest.mark.parametrize("command", [["list"], ["use", "e5-small"]])
def test_commands_require_an_initialized_graph_home(hub: FakeHub, tmp_path: Path, command: list[str]) -> None:
    home = tmp_path / "not-initialized"

    result = runner.invoke(app, ["embedding", *command, "--graph-home", str(home)])

    assert result.exit_code != 0
    assert "vg init" in result.output
    assert not home.exists()
    assert hub.download_calls() == []


def test_help_adds_only_the_embedding_group() -> None:
    command = cast(Any, typer.main.get_command(app))
    assert set(command.commands) == {
        "ask",
        "context",
        "decision-trace",
        "index",
        "init",
        "projection-audit",
        "related",
        "search",
        "serve",
        "setup",
        "status",
        "watch",
        "code",
        "harness",
        "hook",
        "mcp",
        "project",
        "vault",
        "embedding",
    }
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "embedding" in result.output
