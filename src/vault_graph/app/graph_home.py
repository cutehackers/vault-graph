"""Resolve and validate the local Vault Graph Data Home."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from vault_graph.app.path_guard import assert_graph_home_outside_vaults
from vault_graph.errors import (
    DataHomeManifestError,
    DataHomeNotInitializedError,
    LegacyDataHomeDetectedError,
)

DATA_HOME_FORMAT = "vault-graph-data-home-v1"
DATA_HOME_LAYOUT_VERSION = 1
DEFAULT_GRAPH_HOME = Path.home() / ".vault-graph"
MANIFEST_NAME = "data-home.json"


@dataclass(frozen=True)
class GraphHomeManifest:
    """Self-describing identity and active projection pointer for a Data Home."""

    format: str
    data_home_id: str
    layout_version: int
    canonical_root: str
    active_generation_id: str | None = None
    active_generation_path: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "data_home_id": self.data_home_id,
            "layout_version": self.layout_version,
            "canonical_root": self.canonical_root,
            "active_generation_id": self.active_generation_id,
            "active_generation_path": self.active_generation_path,
        }

    @classmethod
    def from_dict(cls, payload: object, *, expected_root: Path) -> GraphHomeManifest:
        if not isinstance(payload, dict):
            raise DataHomeManifestError("data_home_manifest_invalid: manifest must contain an object")
        format_value = _required_text(payload.get("format"), "format")
        if format_value != DATA_HOME_FORMAT:
            raise DataHomeManifestError(f"data_home_manifest_incompatible: unsupported format {format_value!r}")
        layout_version = payload.get("layout_version")
        if not isinstance(layout_version, int) or layout_version != DATA_HOME_LAYOUT_VERSION:
            raise DataHomeManifestError("data_home_manifest_incompatible: layout version is unsupported")
        canonical_root = _required_text(payload.get("canonical_root"), "canonical_root")
        if Path(canonical_root).expanduser().resolve() != expected_root:
            raise DataHomeManifestError("data_home_manifest_identity_mismatch: canonical root differs from path")
        data_home_id = _required_text(payload.get("data_home_id"), "data_home_id")
        if data_home_id != data_home_id_for_root(expected_root):
            raise DataHomeManifestError("data_home_manifest_identity_mismatch: data home identity differs from path")
        active_generation_id = _optional_text(payload.get("active_generation_id"), "active_generation_id")
        active_generation_path = _optional_text(payload.get("active_generation_path"), "active_generation_path")
        if (active_generation_id is None) != (active_generation_path is None):
            raise DataHomeManifestError("data_home_manifest_invalid: active generation fields must be paired")
        return cls(
            format=format_value,
            data_home_id=data_home_id,
            layout_version=layout_version,
            canonical_root=canonical_root,
            active_generation_id=active_generation_id,
            active_generation_path=active_generation_path,
        )


@dataclass(frozen=True)
class GraphHomeDescriptor:
    """Resolved Data Home paths and optional validated manifest."""

    root_path: Path
    manifest: GraphHomeManifest | None
    legacy: bool

    @property
    def manifest_path(self) -> Path:
        return self.root_path / MANIFEST_NAME

    @property
    def configs_path(self) -> Path:
        return self.root_path / "configs"

    @property
    def projections_path(self) -> Path:
        return self.root_path / "projections"

    @property
    def generations_path(self) -> Path:
        return self.projections_path / "generations"

    @property
    def runs_path(self) -> Path:
        return self.root_path / "runs"

    @property
    def initialized(self) -> bool:
        return self.manifest is not None

    def child_path(self, *parts: str) -> Path:
        """Return a safe Data Home child path without following a child symlink."""

        if not parts or any(not part or Path(part).is_absolute() or part in {".", ".."} for part in parts):
            raise DataHomeManifestError("data_home_path_invalid: child path must be relative")
        raw_candidate = self.root_path.joinpath(*parts)
        if any(path.is_symlink() for path in _existing_path_chain(raw_candidate, stop=self.root_path)):
            raise DataHomeManifestError("data_home_path_invalid: symlinked Data Home child is not allowed")
        candidate = raw_candidate.resolve(strict=False)
        if self.root_path not in candidate.parents:
            raise DataHomeManifestError("data_home_path_invalid: child path escapes Data Home")
        return candidate


class GraphHomeResolver:
    """Own the canonical Data Home path, manifest, and initialization boundary."""

    def __init__(self, *, default_path: Path = DEFAULT_GRAPH_HOME) -> None:
        self._default_path = default_path.expanduser()

    def resolve(self, path: Path | None = None) -> GraphHomeDescriptor:
        raw_path = (path if path is not None else self._default_path).expanduser()
        if raw_path.exists() and raw_path.is_symlink():
            raise DataHomeManifestError("data_home_path_invalid: Data Home root must not be a symlink")
        root_path = raw_path.resolve()
        manifest_path = root_path / MANIFEST_NAME
        if manifest_path.exists() and manifest_path.is_symlink():
            raise DataHomeManifestError("data_home_manifest_invalid: manifest must not be a symlink")
        if not manifest_path.exists():
            return GraphHomeDescriptor(root_path=root_path, manifest=None, legacy=_looks_legacy(root_path))
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DataHomeManifestError("data_home_manifest_invalid: manifest is unreadable") from exc
        descriptor = GraphHomeDescriptor(
            root_path=root_path,
            manifest=GraphHomeManifest.from_dict(payload, expected_root=root_path),
            legacy=False,
        )
        _validate_active_generation(descriptor)
        return descriptor

    def require_initialized(self, path: Path | None = None) -> GraphHomeDescriptor:
        descriptor = self.resolve(path)
        if descriptor.initialized:
            return descriptor
        if descriptor.legacy:
            raise _legacy_data_home_error()
        raise DataHomeNotInitializedError("data_home_not_initialized: run `vg setup --vault PATH --graph-home PATH`")

    def initialize(
        self,
        path: Path | None = None,
        *,
        vault_roots: Iterable[Path] = (),
    ) -> GraphHomeDescriptor:
        descriptor = self.resolve(path)
        assert_graph_home_outside_vaults(graph_home=descriptor.root_path, vault_roots=vault_roots)
        if descriptor.initialized:
            return descriptor
        if descriptor.legacy:
            raise _legacy_data_home_error()
        descriptor.root_path.mkdir(parents=True, exist_ok=True)
        for directory in (
            descriptor.configs_path,
            descriptor.projections_path,
            descriptor.generations_path,
            descriptor.runs_path,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        manifest = GraphHomeManifest(
            format=DATA_HOME_FORMAT,
            data_home_id=data_home_id_for_root(descriptor.root_path),
            layout_version=DATA_HOME_LAYOUT_VERSION,
            canonical_root=str(descriptor.root_path),
        )
        _write_manifest(descriptor.manifest_path, manifest)
        return GraphHomeDescriptor(root_path=descriptor.root_path, manifest=manifest, legacy=False)

    def update_active_generation(
        self,
        path: Path | None,
        *,
        generation_id: str | None,
        generation_path: str | None,
    ) -> GraphHomeDescriptor:
        descriptor = self.require_initialized(path)
        if (generation_id is None) != (generation_path is None):
            raise DataHomeManifestError("data_home_manifest_invalid: active generation fields must be paired")
        if generation_path is not None:
            candidate = descriptor.child_path(*Path(generation_path).parts)
            if candidate.parent != descriptor.generations_path.resolve():
                raise DataHomeManifestError("data_home_generation_invalid: generation must be a direct child")
            if candidate.name != generation_id or not candidate.is_dir():
                raise DataHomeManifestError("data_home_generation_invalid: active generation is missing or mismatched")
        assert descriptor.manifest is not None
        manifest = GraphHomeManifest(
            format=descriptor.manifest.format,
            data_home_id=descriptor.manifest.data_home_id,
            layout_version=descriptor.manifest.layout_version,
            canonical_root=descriptor.manifest.canonical_root,
            active_generation_id=generation_id,
            active_generation_path=generation_path,
        )
        _write_manifest(descriptor.manifest_path, manifest)
        return GraphHomeDescriptor(root_path=descriptor.root_path, manifest=manifest, legacy=False)


def data_home_id_for_root(root_path: Path) -> str:
    canonical_root = root_path.expanduser().resolve()
    digest = hashlib.sha256(f"vault-graph-data-home:{canonical_root}".encode()).hexdigest()
    return f"dhome_{digest[:32]}"


def _write_manifest(path: Path, manifest: GraphHomeManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".data-home-", suffix=".json", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(manifest.to_dict(), stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        try:
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_descriptor = None
        if directory_descriptor is not None:
            try:
                os.fsync(directory_descriptor)
            except OSError:
                pass
            finally:
                os.close(directory_descriptor)
    except OSError as exc:
        raise DataHomeManifestError("data_home_manifest_write_failed: cannot publish manifest") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


def _looks_legacy(root_path: Path) -> bool:
    if not root_path.exists() or not root_path.is_dir():
        return False
    markers = (
        root_path / "configs" / "vaults.yaml",
        root_path / "metadata",
        root_path / "vector",
        root_path / "graph",
        root_path / "projections" / "active.json",
        root_path / "projections" / "code",
    )
    return any(marker.exists() for marker in markers)


def _legacy_data_home_error() -> LegacyDataHomeDetectedError:
    return LegacyDataHomeDetectedError(
        "legacy_data_home_detected: "
        "unsupported pre-release layout; choose a new --graph-home PATH "
        "or move this rebuildable directory aside, then run `vg setup --vault PATH --graph-home PATH`"
    )


def _validate_active_generation(descriptor: GraphHomeDescriptor) -> None:
    manifest = descriptor.manifest
    if manifest is None or manifest.active_generation_path is None or manifest.active_generation_id is None:
        return
    candidate = descriptor.child_path(*Path(manifest.active_generation_path).parts)
    if candidate.parent != descriptor.generations_path.resolve():
        raise DataHomeManifestError("data_home_generation_invalid: generation must be a direct child")
    if candidate.name != manifest.active_generation_id or not candidate.is_dir():
        raise DataHomeManifestError("data_home_generation_invalid: active generation is missing or mismatched")


def _existing_path_chain(path: Path, *, stop: Path) -> tuple[Path, ...]:
    chain: list[Path] = []
    current = path
    while current != stop:
        chain.append(current)
        current = current.parent
    return tuple(chain)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DataHomeManifestError(f"data_home_manifest_invalid: {field_name} is required")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DataHomeManifestError(f"data_home_manifest_invalid: {field_name} must be text or null")
    return value
