import json
from pathlib import Path

import pytest

from vault_graph.code_index.code_generation import (
    CodeGenerationError,
    CodeProjectionGenerationManager,
)


def test_code_activation_preserves_previous_generation_and_vault_manifest(tmp_path: Path) -> None:
    vault_manifest = tmp_path / "projections" / "active.json"
    vault_manifest.parent.mkdir(parents=True)
    vault_manifest.write_text('{"generation_id": "vault-current"}', encoding="utf-8")

    manager = CodeProjectionGenerationManager(tmp_path)
    first = manager.stage(("repo-a",))
    manager.activate(first)
    second = manager.stage(("repo-a",))
    manager.activate(second)

    assert manager.active_layout(("repo-a",)) == second
    assert first.root_path.exists()
    assert json.loads(vault_manifest.read_text(encoding="utf-8")) == {"generation_id": "vault-current"}


def test_code_active_manifest_rejects_unsafe_generation_paths(tmp_path: Path) -> None:
    manifest = tmp_path / "projections" / "code" / "active.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "generation_id": "escape",
                "generation_path": "projections/code/generations/../escape",
                "repository_ids": ["repo-a"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CodeGenerationError):
        CodeProjectionGenerationManager(tmp_path).active_layout(("repo-a",))


def test_code_discard_removes_only_uncommitted_generation(tmp_path: Path) -> None:
    manager = CodeProjectionGenerationManager(tmp_path)
    staged = manager.stage(("repo-a",))

    manager.discard(staged)

    assert not staged.root_path.exists()


def test_code_active_layout_rejects_repository_mismatch(tmp_path: Path) -> None:
    manager = CodeProjectionGenerationManager(tmp_path)
    staged = manager.stage(("repo-a",))
    manager.activate(staged)

    assert manager.active_layout(("repo-b",)) is None


def test_code_discard_cannot_remove_active_generation(tmp_path: Path) -> None:
    manager = CodeProjectionGenerationManager(tmp_path)
    staged = manager.stage(("repo-a",))
    manager.activate(staged)

    with pytest.raises(CodeGenerationError):
        manager.discard(staged)
