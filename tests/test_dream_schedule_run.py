"""The scheduled dream run: every registered project, one at a time, from its root (spec 2026-11-24 D3, D8, D10).

`run_scheduled_dreams` gets a fake vault map, a fake port opener and a fake `run_dream_locked`, so no test reaches
a real judge. The worker lock is the real `logs/dream-worker.lock` flock, held by the test where a test needs it.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from vault_graph.errors import VaultGraphError
from vault_graph.interface.composition.adapters.dream_scheduled_run import run_scheduled_dreams
from vault_graph.interface.composition.adapters.dream_worker import (
    DREAM_WORKER_LOCK,
    DreamRun,
    _ran_recently,
    read_dream_runs,
)
from vault_graph.operation.integration.vault_map import MappedProject, VaultMap
from vault_graph.operation.scope.dream_settings import DreamSettings, dream_settings_path, save_dream_settings


def _project(project_id: str, root: str) -> MappedProject:
    return MappedProject(project_id=project_id, root=root, vault_names=("v",), remote=None)


def _map(tmp_path: Path, projects: list[MappedProject]) -> VaultMap:
    return VaultMap(path=tmp_path / "vault-map.json", version=2, vaults=(), projects=tuple(projects))


class FakeRunner:
    """Stands in for `run_dream_locked`. Closes the lock descriptor the way the real one does."""

    def __init__(self, results: dict[str, DreamRun | Exception] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.results = results or {}

    def __call__(self, graph_home: Path, cwd: Path, settings: DreamSettings, ports: Any, **kwargs: Any) -> DreamRun:
        self.calls.append({"cwd": cwd, "ports": ports, **kwargs})
        lock_fd = kwargs.get("lock_fd")
        if lock_fd is not None:
            os.close(lock_fd)
        result = self.results.get(ports["project"], DreamRun("ran", project_id=ports["project"]))
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def graph_home(tmp_path: Path) -> Path:
    home = tmp_path / "graph-home"
    save_dream_settings(dream_settings_path(home), DreamSettings(enabled=True))
    return home


@pytest.fixture
def roots(tmp_path: Path) -> dict[str, Path]:
    made = {}
    for name in ("alpha", "beta", "gamma"):
        folder = tmp_path / "projects" / name
        folder.mkdir(parents=True)
        made[name] = folder
    return made


def _opener(roots: dict[str, Path], calls: list[tuple[Path, Path]] | None = None) -> Any:
    by_root = {root: name for name, root in roots.items()}

    def open_ports(root: Path) -> Any:
        if calls is not None:
            calls.append((root, root))
        return {"project": by_root[root]}

    return open_ports


def _run(
    graph_home: Path, vault_map: VaultMap | None, runner: FakeRunner, open_ports: Any, **kwargs: Any
) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = run_scheduled_dreams(
        graph_home,
        vault_map=vault_map,
        open_ports=open_ports,
        run_locked=runner,
        echo=lines.append,
        **kwargs,
    )
    return code, lines


def test_projects_come_out_in_id_order(tmp_path: Path) -> None:
    vault_map = _map(tmp_path, [_project("b", "/b"), _project("a", "/a"), _project("c", "/c")])

    assert [project.project_id for project in vault_map.projects] == ["a", "b", "c"]
    assert vault_map.default_write_vaults == {"a": None, "b": None, "c": None}


def test_every_project_runs_once_in_turn_from_its_root_as_a_scheduled_run(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path]
) -> None:
    vault_map = _map(tmp_path, [_project(name, str(root)) for name, root in reversed(roots.items())])
    runner = FakeRunner()
    opened: list[tuple[Path, Path]] = []

    code, _ = _run(graph_home, vault_map, runner, _opener(roots, opened))

    assert code == 0
    assert [call["cwd"] for call in runner.calls] == [roots["alpha"], roots["beta"], roots["gamma"]]
    assert all(call["trigger"] == "schedule" for call in runner.calls)
    assert all(call["lock_fd"] is not None for call in runner.calls)
    assert [cwd for cwd, _ in opened] == [roots["alpha"], roots["beta"], roots["gamma"]]


@pytest.mark.parametrize("enabled, broken", [(False, False), (True, True)])
def test_off_or_broken_settings_judge_nothing(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path], enabled: bool, broken: bool
) -> None:
    path = dream_settings_path(graph_home)
    if broken:
        path.write_text(json.dumps({"version": 1, "enabled": True}), encoding="utf-8")
    else:
        save_dream_settings(path, DreamSettings(enabled=enabled))
    runner = FakeRunner()

    code, lines = _run(graph_home, _map(tmp_path, [_project("alpha", str(roots["alpha"]))]), runner, _opener(roots))

    assert (code, lines, runner.calls) == (0, ["dream: skipped off"], [])


def test_a_missing_or_empty_root_is_skipped_without_a_run_line(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path]
) -> None:
    gone = tmp_path / "gone"
    vault_map = _map(
        tmp_path, [_project("alpha", str(gone)), _project("beta", ""), _project("gamma", str(roots["gamma"]))]
    )
    runner = FakeRunner()

    code, lines = _run(graph_home, vault_map, runner, _opener(roots))

    assert code == 0
    assert f"skipped alpha: root missing {gone}" in lines
    assert "skipped beta: root missing " in lines
    assert [call["cwd"] for call in runner.calls] == [roots["gamma"]]
    assert read_dream_runs(graph_home) == []


def test_skipped_and_failed_runs_go_on_to_the_next_project(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path]
) -> None:
    vault_map = _map(tmp_path, [_project(name, str(root)) for name, root in roots.items()])
    runner = FakeRunner(
        {
            "alpha": DreamRun("skipped", "no_write_vault", project_id="alpha"),
            "beta": DreamRun("failed", "judge_unavailable", project_id="beta", message="claude cannot run"),
        }
    )

    code, lines = _run(graph_home, vault_map, runner, _opener(roots))

    assert code == 0
    assert len(runner.calls) == 3
    assert any("alpha" in line and "skipped no_write_vault" in line for line in lines)
    assert any("beta" in line and "failed judge_unavailable" in line for line in lines)


@pytest.mark.parametrize("error", [VaultGraphError("index is broken"), OSError("disk gone")])
def test_an_error_in_one_project_is_logged_and_the_run_ends_with_1(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path], error: Exception
) -> None:
    vault_map = _map(tmp_path, [_project(name, str(root)) for name, root in roots.items()])
    runner = FakeRunner({"alpha": error})

    code, lines = _run(graph_home, vault_map, runner, _opener(roots))

    assert code == 1
    assert any(line.startswith("error alpha:") and str(error) in line for line in lines)
    assert [call["cwd"] for call in runner.calls] == [roots["alpha"], roots["beta"], roots["gamma"]]


def test_a_project_whose_ports_cannot_open_is_an_error(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path]
) -> None:
    vault_map = _map(tmp_path, [_project("alpha", str(roots["alpha"])), _project("beta", str(roots["beta"]))])
    runner = FakeRunner()
    by_root = {root: name for name, root in roots.items()}

    def open_ports(root: Path) -> Any:
        return "no vault-map.json" if by_root[root] == "alpha" else {"project": by_root[root]}

    code, lines = _run(graph_home, vault_map, runner, open_ports)

    assert code == 1
    assert "error alpha: no vault-map.json" in lines
    assert [call["cwd"] for call in runner.calls] == [roots["beta"]]
    assert not (graph_home / DREAM_WORKER_LOCK).exists() or _lock_is_free(graph_home)


def test_no_vault_map_ends_with_1(graph_home: Path) -> None:
    runner = FakeRunner()

    code, lines = _run(graph_home, None, runner, lambda root: {"project": "x"})

    assert code == 1
    assert lines and lines[0].startswith("dream: skipped no_vault_map")
    assert runner.calls == []


@pytest.fixture
def held_lock(graph_home: Path) -> Iterator[int]:
    (graph_home / DREAM_WORKER_LOCK.parent).mkdir(parents=True, exist_ok=True)
    descriptor = os.open(graph_home / DREAM_WORKER_LOCK, os.O_RDWR | os.O_CREAT, 0o644)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _lock_is_free(graph_home: Path) -> bool:
    descriptor = os.open(graph_home / DREAM_WORKER_LOCK, os.O_RDWR)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(descriptor)


def test_a_lock_freed_within_the_wait_lets_the_project_run(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path], held_lock: int
) -> None:
    vault_map = _map(tmp_path, [_project("alpha", str(roots["alpha"]))])
    runner = FakeRunner()
    clock = {"now": 0.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds
        if clock["now"] >= 10:
            fcntl.flock(held_lock, fcntl.LOCK_UN)

    code, _ = _run(
        graph_home, vault_map, runner, _opener(roots), lock_wait_seconds=60, sleep=sleep, monotonic=lambda: clock["now"]
    )

    assert code == 0
    assert [call["cwd"] for call in runner.calls] == [roots["alpha"]]
    assert _lock_is_free(graph_home)


def test_a_lock_held_past_the_wait_leaves_a_locked_line_and_moves_on(
    tmp_path: Path, graph_home: Path, roots: dict[str, Path], held_lock: int
) -> None:
    vault_map = _map(tmp_path, [_project("alpha", str(roots["alpha"])), _project("beta", str(roots["beta"]))])
    runner = FakeRunner()
    clock = {"now": 0.0}

    def sleep(seconds: float) -> None:
        clock["now"] += seconds

    code, lines = _run(
        graph_home, vault_map, runner, _opener(roots), lock_wait_seconds=30, sleep=sleep, monotonic=lambda: clock["now"]
    )

    assert code == 0
    assert runner.calls == []
    assert "skipped alpha: locked" in lines and "skipped beta: locked" in lines
    runs = read_dream_runs(graph_home)
    assert [(run["project"], run["reason"], run["trigger"], run["cwd"]) for run in runs] == [
        ("alpha", "locked", "schedule", str(roots["alpha"])),
        ("beta", "locked", "schedule", str(roots["beta"])),
    ]
    # A locked line does not keep the hook run out (F3).
    assert not _ran_recently(runs, "alpha", DreamSettings(enabled=True), datetime.now(UTC))


def test_the_default_lock_wait_is_thirty_minutes() -> None:
    from vault_graph.interface.composition.adapters import dream_scheduled_run

    assert dream_scheduled_run.LOCK_WAIT_SECONDS == 30 * 60
