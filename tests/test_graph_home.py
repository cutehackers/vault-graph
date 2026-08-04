from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.app.graph_home import (
    DATA_HOME_FORMAT,
    GraphHomeManifest,
    GraphHomeResolver,
    data_home_id_for_root,
)
from vault_graph.errors import (
    DataHomeManifestError,
    DataHomeNotInitializedError,
    LegacyDataHomeDetectedError,
    ReadOnlyBoundaryError,
)


def test_default_resolution_never_searches_current_directory(tmp_path: Path) -> None:
    resolver = GraphHomeResolver(default_path=tmp_path / "home" / ".vault-graph")
    (tmp_path / ".vault-graph" / "configs").mkdir(parents=True)
    (tmp_path / ".vault-graph" / "configs" / "vaults.yaml").write_text("legacy", encoding="utf-8")

    descriptor = resolver.resolve()

    assert descriptor.root_path == (tmp_path / "home" / ".vault-graph").resolve()
    assert descriptor.legacy is False
    assert descriptor.initialized is False


def test_initialize_writes_self_describing_manifest_and_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "graph-home"
    resolver = GraphHomeResolver()

    first = resolver.initialize(root)
    manifest_text = first.manifest_path.read_text(encoding="utf-8")
    second = resolver.initialize(root)

    assert first.manifest is not None
    assert first.manifest.format == DATA_HOME_FORMAT
    assert first.manifest.data_home_id == data_home_id_for_root(root)
    assert json.loads(manifest_text)["canonical_root"] == str(root.resolve())
    assert second == first
    assert first.configs_path.is_dir()
    assert first.generations_path.is_dir()
    assert first.runs_path.is_dir()


def test_require_initialized_reports_missing_home_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "missing"

    with pytest.raises(DataHomeNotInitializedError, match="data_home_not_initialized"):
        GraphHomeResolver().require_initialized(root)

    assert not root.exists()


def test_legacy_home_is_rejected_without_migration_and_is_not_overwritten(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    (root / "configs").mkdir(parents=True)
    legacy_catalog = root / "configs" / "vaults.yaml"
    legacy_catalog.write_text("vaults: []\n", encoding="utf-8")

    with pytest.raises(LegacyDataHomeDetectedError, match="legacy_data_home_detected"):
        GraphHomeResolver().initialize(root)

    assert not (root / "data-home.json").exists()
    assert legacy_catalog.read_text(encoding="utf-8") == "vaults: []\n"


def test_legacy_home_is_detected_from_old_code_projection(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    (root / "projections" / "code").mkdir(parents=True)
    (root / "projections" / "code" / "active.json").write_text("{}\n", encoding="utf-8")

    descriptor = GraphHomeResolver().resolve(root)

    assert descriptor.legacy is True
    with pytest.raises(LegacyDataHomeDetectedError, match="choose a new --graph-home PATH"):
        GraphHomeResolver().require_initialized(root)


def test_manifest_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "graph-home"
    root.mkdir()
    (root / "data-home.json").write_text(
        json.dumps(
            GraphHomeManifest(
                format=DATA_HOME_FORMAT,
                data_home_id="wrong",
                layout_version=1,
                canonical_root=str(root.resolve()),
            ).to_dict()
        ),
        encoding="utf-8",
    )

    with pytest.raises(DataHomeManifestError, match="data_home_manifest_identity_mismatch"):
        GraphHomeResolver().resolve(root)


def test_child_path_rejects_escape_and_symlink(tmp_path: Path) -> None:
    descriptor = GraphHomeResolver().initialize(tmp_path / "graph-home")

    with pytest.raises(DataHomeManifestError, match="child path must be relative"):
        descriptor.child_path("..", "escape")

    outside = tmp_path / "outside"
    outside.mkdir()
    symlink = descriptor.root_path / "configs" / "escape"
    symlink.symlink_to(outside, target_is_directory=True)

    with pytest.raises(DataHomeManifestError, match="symlinked Data Home child"):
        descriptor.child_path("configs", "escape", "file.txt")


def test_update_active_generation_validates_direct_child(tmp_path: Path) -> None:
    resolver = GraphHomeResolver()
    descriptor = resolver.initialize(tmp_path / "graph-home")
    generation = descriptor.generations_path / "generation-1"
    generation.mkdir()

    updated = resolver.update_active_generation(
        descriptor.root_path,
        generation_id="generation-1",
        generation_path="projections/generations/generation-1",
    )

    assert updated.manifest is not None
    assert updated.manifest.active_generation_id == "generation-1"
    assert updated.manifest.active_generation_path == "projections/generations/generation-1"

    with pytest.raises(DataHomeManifestError, match="generation must be a direct child"):
        resolver.update_active_generation(
            descriptor.root_path,
            generation_id="generation-1",
            generation_path="projections/generations/generation-1/nested",
        )


def test_data_home_must_be_outside_vault(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(ReadOnlyBoundaryError, match="must not be inside"):
        GraphHomeResolver().initialize(vault / ".vault-graph", vault_roots=(vault,))
