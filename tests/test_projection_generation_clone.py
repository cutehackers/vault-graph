import hashlib
import sqlite3
from pathlib import Path

import pytest

from vault_graph.indexing.publication import projection_generation, tree_clone
from vault_graph.indexing.publication.projection_generation import ProjectionGenerationManager


def _sha256_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _activate_generation_with_sqlite(manager: ProjectionGenerationManager) -> Path:
    first = manager.stage()
    database = first.root_path / "metadata" / "metadata.sqlite3"
    database.parent.mkdir()
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE documents (id TEXT PRIMARY KEY, body TEXT)")
        connection.executemany(
            "INSERT INTO documents VALUES (?, ?)",
            [(f"doc-{index}", "old " * 64) for index in range(200)],
        )
    connection.close()
    manager.activate(first)
    return first.root_path


def _mutate_staged_sqlite(root: Path) -> None:
    with sqlite3.connect(root / "metadata" / "metadata.sqlite3") as connection:
        connection.execute("UPDATE documents SET body = 'new'")
        connection.execute("INSERT INTO documents VALUES ('doc-new', 'new')")
    connection.close()


def test_editing_staged_sqlite_keeps_active_generation_bytes(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    active_root = _activate_generation_with_sqlite(manager)
    before = _sha256_tree(active_root)

    staged = manager.stage(copy_active=True)
    _mutate_staged_sqlite(staged.root_path)
    manager.discard(staged)

    assert _sha256_tree(active_root) == before
    assert manager.active_layout() is not None
    assert manager.active_layout().root_path == active_root  # type: ignore[union-attr]


def test_stage_prepares_generation_with_clone_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    active_root = _activate_generation_with_sqlite(manager)
    calls: list[tuple[Path, Path]] = []
    real_clone_tree = tree_clone.clone_tree

    def recording_clone_tree(source: Path, target: Path) -> str:
        calls.append((source, target))
        return real_clone_tree(source, target)

    monkeypatch.setattr(projection_generation, "clone_tree", recording_clone_tree)

    staged = manager.stage(copy_active=True)
    manager.discard(staged)

    assert calls == [(active_root, staged.root_path)]


def test_stage_falls_back_to_copy_when_clonefile_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    active_root = _activate_generation_with_sqlite(manager)
    before = _sha256_tree(active_root)

    def failing_clonefile(source_path: Path, target_path: Path) -> None:
        raise OSError(45, "Operation not supported")

    monkeypatch.setattr(tree_clone, "_clonefile", failing_clonefile)

    staged = manager.stage(copy_active=True)
    assert _sha256_tree(staged.root_path) == before
    _mutate_staged_sqlite(staged.root_path)
    manager.discard(staged)

    assert _sha256_tree(active_root) == before
    assert len(capsys.readouterr().err.splitlines()) == 1
