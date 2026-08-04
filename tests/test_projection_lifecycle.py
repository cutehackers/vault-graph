import json
from pathlib import Path

import pytest

from vault_graph.app.catalog_service import CatalogService
from vault_graph.app.graph_home import GraphHomeResolver
from vault_graph.app.projection_generation import (
    ProjectionBundlePublisher,
    ProjectionGenerationError,
)


def _write_components(
    publisher: ProjectionBundlePublisher,
    staged: object,
    *,
    components: tuple[str, ...] = ("metadata", "vector", "graph"),
    source_snapshot: dict[str, object] | None = None,
) -> None:
    snapshot = source_snapshot or {"vault_ids": ["default"], "source_revision": "vault-1"}
    for component in components:
        publisher.write_component_manifest(
            staged,
            component,
            source_snapshot=snapshot,
            contract={"component_contract": f"{component}-v1"},
            schema_version=f"{component}-schema-v1",
            revision=f"{component}-revision-1",
        )


def test_stage_from_active_copies_the_complete_baseline(tmp_path: Path) -> None:
    publisher = ProjectionBundlePublisher(tmp_path)
    first = publisher.stage_from_active()
    (publisher.component_root(first, "metadata") / "marker.txt").write_text("old", encoding="utf-8")
    _write_components(publisher, first, components=("metadata",))
    publisher.activate(first, enabled_components=("metadata",))

    staged = publisher.stage_from_active(full=True)
    (publisher.component_root(staged, "metadata") / "marker.txt").write_text("new", encoding="utf-8")

    assert (publisher.component_root(first, "metadata") / "marker.txt").read_text(encoding="utf-8") == "old"
    assert (publisher.component_root(staged, "metadata") / "marker.txt").read_text(encoding="utf-8") == "new"
    assert publisher.manager.active_layout() == first


def test_bundle_validation_requires_complete_components_and_common_snapshot(tmp_path: Path) -> None:
    publisher = ProjectionBundlePublisher(tmp_path)
    staged = publisher.stage_from_active()
    _write_components(publisher, staged)

    bundle = publisher.validate_bundle(staged, enabled_components=("metadata", "vector", "graph"))

    assert bundle["generation_id"] == staged.generation_id
    assert bundle["components"] == ["graph", "metadata", "vector"]

    manifest_path = publisher.component_root(staged, "graph") / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["source_snapshot"] = {"vault_ids": ["default"], "source_revision": "vault-2"}
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectionGenerationError, match="source snapshot"):
        publisher.validate_bundle(staged, enabled_components=("metadata", "vector", "graph"))


def test_failed_bundle_is_discarded_without_changing_active_generation(tmp_path: Path) -> None:
    publisher = ProjectionBundlePublisher(tmp_path)
    first = publisher.stage_from_active()
    _write_components(publisher, first)
    publisher.activate(first, enabled_components=("metadata", "vector", "graph"))

    failed = publisher.stage_from_active()
    publisher.write_component_manifest(
        failed,
        "metadata",
        source_snapshot={"vault_ids": ["default"], "source_revision": "vault-2"},
        contract={"component_contract": "metadata-v1"},
        schema_version="metadata-schema-v1",
        revision="metadata-revision-2",
        status="failed",
    )
    publisher.write_run_diagnostic(
        run_id="run-failed",
        status="failed",
        staged=failed,
        error="metadata failed",
    )
    publisher.discard(failed)

    assert publisher.manager.active_layout() == first
    assert not failed.root_path.exists()
    diagnostic = tmp_path / "runs" / "run-failed.json"
    assert json.loads(diagnostic.read_text(encoding="utf-8"))["status"] == "failed"


def test_rollback_restores_previous_generation(tmp_path: Path) -> None:
    publisher = ProjectionBundlePublisher(tmp_path)
    first = publisher.stage_from_active()
    _write_components(publisher, first, components=("metadata",))
    publisher.activate(first, enabled_components=("metadata",))
    second = publisher.stage_from_active()
    _write_components(publisher, second, components=("metadata",), source_snapshot={"source_revision": "2"})
    publisher.activate(second, enabled_components=("metadata",))

    restored = publisher.rollback()

    assert restored == first
    assert publisher.manager.active_layout() == first


def test_readers_keep_the_generation_path_pinned_after_activation(tmp_path: Path) -> None:
    resolver = GraphHomeResolver()
    descriptor = resolver.initialize(tmp_path / "graph-home")
    publisher = ProjectionBundlePublisher(descriptor.root_path)
    first = publisher.stage_from_active()
    _write_components(publisher, first, components=("metadata",))
    publisher.activate(first, enabled_components=("metadata",))

    old_reader = CatalogService(graph_home_path=descriptor.root_path)
    second = publisher.stage_from_active()
    _write_components(publisher, second, components=("metadata",), source_snapshot={"source_revision": "2"})
    publisher.activate(second, enabled_components=("metadata",))
    new_reader = CatalogService(graph_home_path=descriptor.root_path)

    assert old_reader.metadata_path.parent.parent == first.root_path
    assert new_reader.metadata_path.parent.parent == second.root_path
