import json
from pathlib import Path

import pytest

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
