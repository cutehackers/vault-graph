"""Spec 2026-11-13 D15, A13: `longmemeval_run --reranker <preset>` writes `configs/reranker.json` per Graph Home."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from tests.benchmarks import longmemeval_run as run
from vault_graph.operation.scope.reranker_selection import (
    RerankerSelection,
    load_reranker_selection,
    reranker_config_path,
)


@pytest.fixture
def commands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Replace the subprocess runner so `prepare` runs no real tool and records each command."""
    seen: list[list[str]] = []

    def fake_run(
        command: Sequence[str], *, label: str, env: Mapping[str, str], cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        seen.append(list(command))
        return subprocess.CompletedProcess(list(command), 0, "", "")

    monkeypatch.setattr(run, "_run", fake_run)
    return seen


def test_prepare_with_a_preset_writes_the_reranker_config(tmp_path: Path, commands: list[list[str]]) -> None:
    workspace = run.Workspace(tmp_path / "q0001")
    tools = run.LocalTools(vault_builder=tmp_path / "builder", reranker="mmarco")

    tools.prepare(workspace)

    assert any("setup" in command for command in commands)
    path = reranker_config_path(workspace.graph_home)
    assert load_reranker_selection(path) == RerankerSelection(enabled=True, model="mmarco")


def test_prepare_without_a_preset_writes_no_reranker_config(tmp_path: Path, commands: list[list[str]]) -> None:
    workspace = run.Workspace(tmp_path / "q0001")

    run.LocalTools(vault_builder=tmp_path / "builder").prepare(workspace)

    assert any("setup" in command for command in commands)
    assert not reranker_config_path(workspace.graph_home).exists()


def test_an_unknown_preset_is_refused_before_any_question_runs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown rerank preset 'nope'"):
        run.LocalTools(vault_builder=tmp_path / "builder", reranker="nope")


def test_the_reranker_argument_is_optional_and_limited_to_the_preset_names() -> None:
    base = ["--data", "d.json", "--vault-builder", "b", "--work-dir", "w", "--out-dir", "o"]

    assert run._parse_args(base).reranker is None
    assert run._parse_args([*base, "--reranker", "mmarco"]).reranker == "mmarco"
    with pytest.raises(SystemExit):
        run._parse_args([*base, "--reranker", "nope"])
