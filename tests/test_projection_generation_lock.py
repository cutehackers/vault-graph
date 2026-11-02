"""Generation retention and the cross-process publish lock (re-audit findings 4 and 5)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from vault_graph.indexing.publication.projection_generation import (
    STALE_STAGED_GENERATION_SECONDS,
    ProjectionGenerationManager,
    ProjectionPublishBusyError,
)


def _generation_names(graph_home: Path) -> set[str]:
    return {path.name for path in (graph_home / "projections" / "generations").iterdir()}


def _publish_marker(manager: ProjectionGenerationManager, line: str) -> None:
    staged = manager.stage_from_active()
    marker = staged.root_path / "marker.txt"
    existing = marker.read_text(encoding="utf-8") if marker.exists() else ""
    marker.write_text(existing + line + "\n", encoding="utf-8")
    manager.activate(staged)


def test_activation_keeps_only_active_and_previous_generations(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    layouts = []
    for index in range(4):
        staged = manager.stage_from_active()
        (staged.root_path / "marker.txt").write_text(str(index), encoding="utf-8")
        manager.activate(staged)
        layouts.append(staged)

    assert _generation_names(tmp_path) == {layouts[-1].generation_id, layouts[-2].generation_id}
    assert manager.rollback() == layouts[-2]
    assert manager.active_layout() == layouts[-2]


def test_stage_removes_stale_leftovers_but_keeps_recent_and_active_ones(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    first = manager.stage()
    manager.activate(first)
    second = manager.stage()
    manager.activate(second)
    generations = tmp_path / "projections" / "generations"
    stale = generations / "stalestaged"
    stale.mkdir()
    (stale / "big.bin").write_bytes(b"x" * 16)
    recent = generations / "recentstaged"
    recent.mkdir()
    old = time.time() - STALE_STAGED_GENERATION_SECONDS - 60
    for path in (stale, first.root_path, second.root_path):
        os.utime(path, (old, old))

    staged = manager.stage_from_active()

    assert not stale.exists()
    assert recent.exists()
    assert first.root_path.exists()
    assert second.root_path.exists()
    assert staged.root_path.exists()
    manager.discard(staged)


def test_try_lock_timeout_raises_busy_while_another_publisher_stages(tmp_path: Path) -> None:
    holder = ProjectionGenerationManager(tmp_path)
    held = holder.stage()

    started = time.monotonic()
    with pytest.raises(ProjectionPublishBusyError):
        ProjectionGenerationManager(tmp_path).stage_from_active(lock_timeout=0.2)
    assert time.monotonic() - started < 2

    holder.activate(held)
    staged = ProjectionGenerationManager(tmp_path).stage_from_active(lock_timeout=0.2)
    assert staged.root_path.exists()


def test_discard_releases_the_publish_lock(tmp_path: Path) -> None:
    holder = ProjectionGenerationManager(tmp_path)
    holder.discard(holder.stage())

    staged = ProjectionGenerationManager(tmp_path).stage(lock_timeout=0)
    assert staged.root_path.exists()


def test_waiting_publisher_builds_on_the_generation_published_while_it_waited(tmp_path: Path) -> None:
    first = ProjectionGenerationManager(tmp_path)
    _publish_marker(first, "base")
    held = first.stage_from_active()
    (held.root_path / "marker.txt").write_text("base\nfirst\n", encoding="utf-8")
    result: dict[str, object] = {}

    def second_publisher() -> None:
        try:
            _publish_marker(ProjectionGenerationManager(tmp_path), "second")
        except BaseException as exc:  # pragma: no cover - surfaced by the assertion below
            result["error"] = exc

    thread = threading.Thread(target=second_publisher)
    thread.start()
    time.sleep(0.3)
    assert thread.is_alive(), "second publisher must wait for the lock"
    first.activate(held)
    thread.join(timeout=10)

    assert "error" not in result
    active = ProjectionGenerationManager(tmp_path).active_layout()
    assert active is not None
    assert (active.root_path / "marker.txt").read_text(encoding="utf-8") == "base\nfirst\nsecond\n"


def test_concurrent_processes_never_overwrite_each_other(tmp_path: Path) -> None:
    script = textwrap.dedent(
        """
        import sys
        from pathlib import Path
        from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager
        manager = ProjectionGenerationManager(Path(sys.argv[1]))
        for round_index in range(3):
            staged = manager.stage_from_active()
            marker = staged.root_path / "marker.txt"
            existing = marker.read_text(encoding="utf-8") if marker.exists() else ""
            marker.write_text(existing + f"{sys.argv[2]}-{round_index}\\n", encoding="utf-8")
            manager.activate(staged)
        """
    )
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(tmp_path), f"p{index}"], stderr=subprocess.PIPE, text=True)
        for index in range(4)
    ]
    for process in processes:
        _, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr

    active = ProjectionGenerationManager(tmp_path).active_layout()
    assert active is not None
    lines = (active.root_path / "marker.txt").read_text(encoding="utf-8").splitlines()
    assert sorted(lines) == sorted(f"p{index}-{round_index}" for index in range(4) for round_index in range(3))
    assert len(_generation_names(tmp_path)) <= 2
