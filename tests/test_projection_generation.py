import json
from pathlib import Path

import pytest

from vault_graph.app.graph_home import GraphHomeResolver
from vault_graph.app.projection_generation import ProjectionGenerationError, ProjectionGenerationManager


def test_activation_switches_one_manifest_and_preserves_previous_generation(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    first = manager.stage()
    manager.activate(first)
    second = manager.stage()
    manager.activate(second)

    assert manager.active_layout() == second
    assert first.root_path.exists()


@pytest.mark.parametrize("relative_path", ["../escape", "/absolute", "projections/generations/../escape"])
def test_active_manifest_rejects_unsafe_generation_paths(tmp_path: Path, relative_path: str) -> None:
    manifest = tmp_path / "projections" / "active.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps({"generation_id": "escape", "generation_path": relative_path}),
        encoding="utf-8",
    )

    with pytest.raises(ProjectionGenerationError):
        ProjectionGenerationManager(tmp_path).active_layout()


def test_discard_removes_only_uncommitted_generation(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    staged = manager.stage()

    manager.discard(staged)

    assert not staged.root_path.exists()


def test_incremental_stage_copies_active_generation_without_mutating_it(tmp_path: Path) -> None:
    manager = ProjectionGenerationManager(tmp_path)
    first = manager.stage()
    (first.root_path / "metadata").mkdir()
    (first.root_path / "metadata" / "marker.txt").write_text("old", encoding="utf-8")
    manager.activate(first)

    staged = manager.stage(copy_active=True)
    (staged.root_path / "metadata" / "marker.txt").write_text("new", encoding="utf-8")

    assert manager.active_layout() == first
    assert (first.root_path / "metadata" / "marker.txt").read_text(encoding="utf-8") == "old"
    assert (staged.root_path / "metadata" / "marker.txt").read_text(encoding="utf-8") == "new"


def test_activation_updates_data_home_active_generation_pointer(tmp_path: Path) -> None:
    resolver = GraphHomeResolver()
    descriptor = resolver.initialize(tmp_path / "graph-home")
    manager = ProjectionGenerationManager(descriptor.root_path)
    staged = manager.stage()

    manager.activate(staged)

    resolved = resolver.require_initialized(descriptor.root_path)
    assert resolved.manifest is not None
    assert resolved.manifest.active_generation_id == staged.generation_id
    assert resolved.manifest.active_generation_path == staged.root_path.relative_to(descriptor.root_path).as_posix()


def test_active_layout_rejects_mismatched_data_home_and_projection_manifests(tmp_path: Path) -> None:
    resolver = GraphHomeResolver()
    descriptor = resolver.initialize(tmp_path / "graph-home")
    manager = ProjectionGenerationManager(descriptor.root_path)
    first = manager.stage()
    manager.activate(first)
    second = manager.stage()
    second.root_path.mkdir(exist_ok=True)
    (descriptor.root_path / "projections" / "active.json").write_text(
        json.dumps(
            {
                "generation_id": second.generation_id,
                "generation_path": second.root_path.relative_to(descriptor.root_path).as_posix(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ProjectionGenerationError, match="manifests disagree"):
        manager.active_layout()
