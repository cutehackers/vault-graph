"""Read-only lookup of the active projection generation under a Data Home.

CatalogService (M01) needs the active generation path to place metadata, vector and graph stores.
Writing and switching generations stays in indexing/publication/projection_generation.py (M04),
which re-exports these names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from vault_graph.errors import VaultGraphError
from vault_graph.operation.scope.graph_home import GraphHomeResolver


class ProjectionGenerationError(VaultGraphError):
    pass


@dataclass(frozen=True)
class ProjectionLayout:
    generation_id: str
    root_path: Path


def active_projection_layout(graph_home_path: Path) -> ProjectionLayout | None:
    """Return the active generation, or None when no generation was published."""

    graph_home_path = graph_home_path.expanduser().resolve()
    active_manifest = graph_home_path / "projections" / "active.json"
    if (graph_home_path / "data-home.json").exists():
        return _active_layout_from_data_home(graph_home_path, active_manifest)
    if not active_manifest.exists():
        return None
    payload = json.loads(active_manifest.read_text(encoding="utf-8"))
    generation_id = str(payload.get("generation_id", ""))
    relative_path = str(payload.get("generation_path", ""))
    if not generation_id or not relative_path:
        raise ProjectionGenerationError("active projection manifest is incomplete")
    candidate = validated_generation_path(graph_home_path, relative_path)
    if candidate.name != generation_id:
        raise ProjectionGenerationError("active projection generation identity mismatch")
    if not candidate.is_dir():
        raise ProjectionGenerationError("active projection generation is missing")
    return ProjectionLayout(generation_id=generation_id, root_path=candidate)


def validated_generation_path(graph_home_path: Path, relative_path: str) -> Path:
    """Resolve a manifest path and require it to be a direct child of projections/generations."""

    raw = Path(relative_path)
    if raw.is_absolute() or ".." in raw.parts:
        raise ProjectionGenerationError("projection generation path escapes Data Home root")
    candidate = (graph_home_path / raw).resolve()
    generations_root = (graph_home_path / "projections" / "generations").resolve()
    if candidate.parent != generations_root or candidate.is_symlink():
        raise ProjectionGenerationError("projection generation path is not a direct generation child")
    return candidate


def _active_layout_from_data_home(graph_home_path: Path, active_manifest: Path) -> ProjectionLayout | None:
    descriptor = GraphHomeResolver().require_initialized(graph_home_path)
    assert descriptor.manifest is not None
    manifest = descriptor.manifest
    if manifest.active_generation_id is None or manifest.active_generation_path is None:
        if active_manifest.exists():
            raise ProjectionGenerationError("data home and active projection manifests disagree")
        return None
    candidate = validated_generation_path(graph_home_path, manifest.active_generation_path)
    if candidate.name != manifest.active_generation_id or not candidate.is_dir():
        raise ProjectionGenerationError("active Data Home generation is missing or mismatched")
    if not active_manifest.exists():
        raise ProjectionGenerationError("active projection manifest is missing")
    try:
        payload = json.loads(active_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProjectionGenerationError("active projection manifest is unreadable") from exc
    if (
        payload.get("generation_id") != manifest.active_generation_id
        or payload.get("generation_path") != manifest.active_generation_path
    ):
        raise ProjectionGenerationError("data home and active projection manifests disagree")
    return ProjectionLayout(generation_id=manifest.active_generation_id, root_path=candidate)
