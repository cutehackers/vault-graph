from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vault_graph.operation.scope.active_projection import ProjectionGenerationError as ProjectionGenerationError
from vault_graph.operation.scope.active_projection import ProjectionLayout as ProjectionLayout
from vault_graph.operation.scope.active_projection import active_projection_layout, validated_generation_path
from vault_graph.operation.scope.graph_home import GraphHomeResolver

PROJECTION_BUNDLE_FORMAT = "vault-graph-projection-bundle-v1"
PROJECTION_COMPONENT_FORMAT = "vault-graph-projection-component-v1"
PROJECTION_BUNDLE_SCHEMA_VERSION = 1
PROJECTION_COMPONENTS = ("metadata", "vector", "graph", "code")
_SAFE_RUN_ID_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
PUBLISH_LOCK_FILENAME = ".publish.lock"
STALE_STAGED_GENERATION_SECONDS = 3600.0
_LOCK_POLL_SECONDS = 0.05


class ProjectionPublishBusyError(ProjectionGenerationError):
    """Another publisher holds the projection publish lock past the caller's timeout."""


@dataclass(frozen=True)
class ProjectionComponentManifest:
    """The contract and source snapshot for one rebuildable component."""

    generation_id: str
    component: str
    schema_version: str
    revision: str
    source_snapshot: dict[str, object]
    source_snapshot_id: str
    contract: dict[str, object]
    status: str = "ready"

    def to_dict(self) -> dict[str, object]:
        return {
            "format": PROJECTION_COMPONENT_FORMAT,
            "generation_id": self.generation_id,
            "component": self.component,
            "schema_version": self.schema_version,
            "revision": self.revision,
            "source_snapshot": self.source_snapshot,
            "source_snapshot_id": self.source_snapshot_id,
            "contract": self.contract,
            "status": self.status,
        }


class ProjectionGenerationManager:
    """Stages rebuildable projections and atomically selects the readable generation."""

    def __init__(self, graph_home_path: Path) -> None:
        self._graph_home_path = graph_home_path.expanduser().resolve()
        self._projection_root = self._graph_home_path / "projections"
        self._generations_root = self._projection_root / "generations"
        self._active_manifest = self._projection_root / "active.json"
        self._previous_manifest = self._projection_root / "previous.json"
        self._lock_path = self._projection_root / PUBLISH_LOCK_FILENAME
        self._lock_descriptor: int | None = None
        self._lock_holders: set[str] = set()

    def stage(self, *, copy_active: bool = False, lock_timeout: float | None = None) -> ProjectionLayout:
        """Stage a new generation and hold the publish lock until activate() or discard().

        lock_timeout=None waits for the lock. A number waits at most that many seconds and then
        raises ProjectionPublishBusyError, so callers that must not block can skip.
        """

        if self._projection_root.is_symlink() or self._generations_root.is_symlink():
            raise ProjectionGenerationError("projection generation path must not be a symlink")
        generation_id = uuid.uuid4().hex
        root_path = self._generations_root / generation_id
        self._acquire_lock(generation_id, lock_timeout)
        try:
            # Read the active generation only after the lock is held, so a publisher that
            # waited builds on the generation published while it waited.
            active = self.active_layout() if copy_active else None
            self._remove_stale_generations(active)
            if active is None:
                root_path.mkdir(parents=True, exist_ok=False)
            else:
                root_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(active.root_path, root_path, symlinks=False)
                # copytree copies the source timestamps; mark the staged folder as new.
                os.utime(root_path)
        except BaseException:
            self._release_lock(generation_id)
            raise
        return ProjectionLayout(generation_id=generation_id, root_path=root_path)

    def stage_from_active(self, *, full: bool = False, lock_timeout: float | None = None) -> ProjectionLayout:
        """Create copy-on-write staging for full and incremental runs."""

        return self.stage(copy_active=True, lock_timeout=lock_timeout)

    def active_layout(self) -> ProjectionLayout | None:
        return active_projection_layout(self._graph_home_path)

    def activate(self, staged: ProjectionLayout) -> None:
        self._acquire_lock(staged.generation_id, None)
        try:
            self._activate_locked(staged)
            self._remove_unretained_generations()
        finally:
            self._release_lock(staged.generation_id)

    def _activate_locked(self, staged: ProjectionLayout) -> None:
        expected = self.validate_layout(staged)
        self._projection_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "generation_id": staged.generation_id,
            "generation_path": expected.relative_to(self._graph_home_path).as_posix(),
        }
        previous_payload = self._read_active_payload()
        previous_layout = (
            _layout_from_payload(self._graph_home_path, previous_payload) if previous_payload is not None else None
        )
        if previous_payload is not None:
            _atomic_write_json(self._previous_manifest, previous_payload, prefix=".previous-")
        try:
            _atomic_write_json(self._active_manifest, payload, prefix=".active-")
            if (self._graph_home_path / "data-home.json").exists():
                GraphHomeResolver().update_active_generation(
                    self._graph_home_path,
                    generation_id=staged.generation_id,
                    generation_path=expected.relative_to(self._graph_home_path).as_posix(),
                )
        except Exception:
            # The two active pointers cannot be replaced by one filesystem
            # operation. Restore the previous pair immediately on failure;
            # a crash between the writes is handled by fail-closed readers.
            try:
                if previous_payload is None:
                    self._active_manifest.unlink(missing_ok=True)
                else:
                    _atomic_write_json(self._active_manifest, previous_payload, prefix=".active-rollback-")
                if (self._graph_home_path / "data-home.json").exists():
                    GraphHomeResolver().update_active_generation(
                        self._graph_home_path,
                        generation_id=previous_layout.generation_id if previous_layout is not None else None,
                        generation_path=(
                            previous_layout.root_path.relative_to(self._graph_home_path).as_posix()
                            if previous_layout is not None
                            else None
                        ),
                    )
            except Exception:
                pass
            raise

    def discard(self, staged: ProjectionLayout) -> None:
        validated = self.validate_layout(staged)
        active = self.active_layout()
        if active is not None and active.root_path == validated:
            raise ProjectionGenerationError("cannot discard the active projection generation")
        try:
            if validated.exists():
                shutil.rmtree(validated)
        finally:
            self._release_lock(staged.generation_id)

    def rollback(self) -> ProjectionLayout | None:
        """Restore the generation saved before the last activation."""

        if not self._previous_manifest.exists():
            return None
        try:
            payload = json.loads(self._previous_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectionGenerationError("previous projection manifest is unreadable") from exc
        previous = _layout_from_payload(self._graph_home_path, payload)
        if previous is None:
            return None
        self.activate(previous)
        return previous

    def validate_layout(self, staged: ProjectionLayout) -> Path:
        if not isinstance(staged, ProjectionLayout):
            raise ProjectionGenerationError("staged projection generation is invalid")
        if not staged.generation_id or not _is_safe_generation_id(staged.generation_id):
            raise ProjectionGenerationError("staged projection generation identity is invalid")
        raw_path = staged.root_path.expanduser()
        if raw_path.is_symlink():
            raise ProjectionGenerationError("staged projection generation must not be a symlink")
        try:
            relative_path = raw_path.resolve().relative_to(self._graph_home_path).as_posix()
        except ValueError as exc:
            raise ProjectionGenerationError("staged projection generation escapes Data Home root") from exc
        candidate = self._validated_generation_path(relative_path)
        if candidate != raw_path.resolve() or candidate.name != staged.generation_id or not candidate.is_dir():
            raise ProjectionGenerationError("staged projection generation is invalid")
        return candidate

    @property
    def graph_home_path(self) -> Path:
        return self._graph_home_path

    def _read_active_payload(self) -> dict[str, object] | None:
        if not self._active_manifest.exists():
            return None
        try:
            payload = json.loads(self._active_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectionGenerationError("active projection manifest is unreadable") from exc
        if not isinstance(payload, dict):
            raise ProjectionGenerationError("active projection manifest must contain an object")
        return payload

    def _validated_generation_path(self, relative_path: str) -> Path:
        return validated_generation_path(self._graph_home_path, relative_path)

    def _acquire_lock(self, holder: str, timeout: float | None) -> None:
        """Take the cross-process publish lock; nested holders in this manager share it."""

        if self._lock_descriptor is not None:
            self._lock_holders.add(holder)
            return
        if self._projection_root.is_symlink():
            raise ProjectionGenerationError("projection generation path must not be a symlink")
        self._projection_root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self._lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as exc:
            raise ProjectionGenerationError("cannot open the projection publish lock") from exc
        deadline = None if timeout is None else time.monotonic() + max(timeout, 0.0)
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if deadline is None else fcntl.LOCK_NB))
                    break
                except BlockingIOError:
                    if deadline is None or time.monotonic() >= deadline:
                        raise ProjectionPublishBusyError(
                            "another process is publishing a projection generation"
                        ) from None
                    time.sleep(_LOCK_POLL_SECONDS)
                except InterruptedError:
                    continue
        except BaseException:
            os.close(descriptor)
            raise
        self._lock_descriptor = descriptor
        self._lock_holders = {holder}

    def _release_lock(self, holder: str) -> None:
        self._lock_holders.discard(holder)
        if self._lock_holders or self._lock_descriptor is None:
            return
        descriptor, self._lock_descriptor = self._lock_descriptor, None
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _retained_generation_ids(self) -> set[str]:
        retained: set[str] = set()
        active = self.active_layout()
        if active is not None:
            retained.add(active.generation_id)
        if self._previous_manifest.exists():
            try:
                payload = json.loads(self._previous_manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict) and isinstance(payload.get("generation_id"), str):
                retained.add(payload["generation_id"])
        return retained

    def _generation_folders(self) -> list[Path]:
        if not self._generations_root.is_dir() or self._generations_root.is_symlink():
            return []
        return [
            path
            for path in self._generations_root.iterdir()
            if not path.is_symlink() and path.is_dir() and _is_safe_generation_id(path.name)
        ]

    def _remove_unretained_generations(self) -> None:
        """After activation, keep only the active and previous generations. Caller holds the lock."""

        retained = self._retained_generation_ids() | self._lock_holders
        for path in self._generation_folders():
            if path.name not in retained:
                shutil.rmtree(path, ignore_errors=True)

    def _remove_stale_generations(self, active: ProjectionLayout | None) -> None:
        """Remove staged folders left by interrupted runs. Caller holds the lock."""

        retained = self._retained_generation_ids() | self._lock_holders
        if active is not None:
            retained.add(active.generation_id)
        cutoff = time.time() - STALE_STAGED_GENERATION_SECONDS
        for path in self._generation_folders():
            if path.name in retained:
                continue
            try:
                modified = path.stat().st_mtime
            except OSError:
                continue
            if modified < cutoff:
                shutil.rmtree(path, ignore_errors=True)


class ProjectionBundlePublisher:
    """Publish a complete, self-describing projection generation."""

    def __init__(
        self,
        graph_home_path: Path,
        manager: ProjectionGenerationManager | None = None,
    ) -> None:
        self.manager = manager or ProjectionGenerationManager(graph_home_path)
        self._graph_home_path = self.manager.graph_home_path

    def stage_from_active(self, *, full: bool = False, lock_timeout: float | None = None) -> ProjectionLayout:
        return self.manager.stage_from_active(full=full, lock_timeout=lock_timeout)

    def component_root(self, staged: ProjectionLayout, component: str, *, create: bool = True) -> Path:
        self.manager.validate_layout(staged)
        _validate_component_name(component)
        root = staged.root_path / component
        if root.is_symlink():
            raise ProjectionGenerationError(f"{component} projection root must not be a symlink")
        if create:
            root.mkdir(parents=True, exist_ok=True)
        return root

    def write_component_manifest(
        self,
        staged: ProjectionLayout,
        component: str,
        *,
        source_snapshot: Mapping[str, object],
        contract: Mapping[str, object],
        schema_version: str,
        revision: str,
        status: str = "ready",
    ) -> ProjectionComponentManifest:
        if not isinstance(source_snapshot, Mapping) or not isinstance(contract, Mapping):
            raise ProjectionGenerationError("component manifest source_snapshot and contract must be mappings")
        if not schema_version or not revision:
            raise ProjectionGenerationError("component manifest schema_version and revision are required")
        if status not in {"ready", "failed", "partial"}:
            raise ProjectionGenerationError("component manifest status is invalid")
        root = self.component_root(staged, component)
        snapshot = _json_mapping(source_snapshot, "source_snapshot")
        contract_payload = _json_mapping(contract, "contract")
        manifest = ProjectionComponentManifest(
            generation_id=staged.generation_id,
            component=component,
            schema_version=schema_version,
            revision=revision,
            source_snapshot=snapshot,
            source_snapshot_id=_snapshot_id(snapshot),
            contract=contract_payload,
            status=status,
        )
        _atomic_write_json(root / "manifest.json", manifest.to_dict(), prefix=f".{component}-manifest-")
        return manifest

    def validate_bundle(
        self,
        staged: ProjectionLayout,
        *,
        enabled_components: Sequence[str] | None = None,
    ) -> dict[str, object]:
        self.manager.validate_layout(staged)
        components = tuple(sorted(set(enabled_components or self._discover_components(staged))))
        if not components:
            raise ProjectionGenerationError("projection bundle has no enabled components")
        manifests = tuple(self._read_component_manifest(staged, component) for component in components)
        snapshot_ids = {manifest.source_snapshot_id for manifest in manifests}
        if len(snapshot_ids) != 1:
            raise ProjectionGenerationError("projection components have mixed source snapshot revisions")
        return {
            "format": PROJECTION_BUNDLE_FORMAT,
            "schema_version": PROJECTION_BUNDLE_SCHEMA_VERSION,
            "generation_id": staged.generation_id,
            "components": list(components),
            "source_snapshot_id": manifests[0].source_snapshot_id,
            "component_revisions": {manifest.component: manifest.revision for manifest in manifests},
        }

    def write_bundle_manifest(
        self,
        staged: ProjectionLayout,
        *,
        enabled_components: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        bundle = self.validate_bundle(staged, enabled_components=enabled_components)
        if run_id is not None:
            _validate_run_id(run_id)
            bundle["run_id"] = run_id
        _atomic_write_json(staged.root_path / "bundle-manifest.json", bundle, prefix=".bundle-manifest-")
        return bundle

    def write_run_diagnostic(
        self,
        *,
        run_id: str,
        status: str,
        staged: ProjectionLayout | None = None,
        error: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> Path:
        _validate_run_id(run_id)
        if status not in {"staged", "published", "failed", "rolled_back"}:
            raise ProjectionGenerationError("projection run status is invalid")
        runs_root = self._graph_home_path / "runs"
        if runs_root.is_symlink():
            raise ProjectionGenerationError("Data Home runs path must not be a symlink")
        runs_root.mkdir(parents=True, exist_ok=True)
        active = self.manager.active_layout()
        payload: dict[str, object] = {
            "format": "vault-graph-projection-run-v1",
            "run_id": run_id,
            "status": status,
            "created_at": datetime.now(UTC).isoformat(),
            "active_generation_id": active.generation_id if active is not None else None,
        }
        if staged is not None:
            self.manager.validate_layout(staged)
            payload["staged_generation_id"] = staged.generation_id
        if error is not None:
            payload["error"] = error
        if details is not None:
            payload["details"] = _json_mapping(details, "details")
        destination = runs_root / f"{run_id}.json"
        _atomic_write_json(destination, payload, prefix=f".{run_id}-")
        return destination

    def activate(
        self,
        staged: ProjectionLayout,
        *,
        enabled_components: Sequence[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        bundle = self.write_bundle_manifest(
            staged,
            enabled_components=enabled_components,
            run_id=run_id,
        )
        self.manager.activate(staged)
        if run_id is not None:
            self.write_run_diagnostic(run_id=run_id, status="published", staged=staged, details=bundle)
        return bundle

    def discard(self, staged: ProjectionLayout) -> None:
        self.manager.discard(staged)

    def rollback(self, staged: ProjectionLayout | None = None) -> ProjectionLayout | None:
        if staged is not None:
            active = self.manager.active_layout()
            if active is None or active.root_path != staged.root_path.resolve():
                self.manager.discard(staged)
        restored = self.manager.rollback()
        if restored is not None:
            self.write_run_diagnostic(
                run_id=f"rollback-{restored.generation_id}",
                status="rolled_back",
                staged=restored,
            )
        return restored

    def _discover_components(self, staged: ProjectionLayout) -> tuple[str, ...]:
        found: list[str] = []
        for component in PROJECTION_COMPONENTS:
            manifest = staged.root_path / component / "manifest.json"
            if manifest.exists():
                found.append(component)
        return tuple(found)

    def _read_component_manifest(self, staged: ProjectionLayout, component: str) -> ProjectionComponentManifest:
        root = self.component_root(staged, component, create=False)
        manifest_path = root / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ProjectionGenerationError(f"projection component manifest is missing: {component}")
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectionGenerationError(f"projection component manifest is unreadable: {component}") from exc
        if not isinstance(payload, dict) or payload.get("format") != PROJECTION_COMPONENT_FORMAT:
            raise ProjectionGenerationError(f"projection component manifest is incompatible: {component}")
        if payload.get("generation_id") != staged.generation_id or payload.get("component") != component:
            raise ProjectionGenerationError(f"projection component identity mismatch: {component}")
        status = payload.get("status")
        if status != "ready":
            raise ProjectionGenerationError(f"projection component is not ready: {component}")
        schema_version = payload.get("schema_version")
        revision = payload.get("revision")
        source_snapshot = payload.get("source_snapshot")
        contract = payload.get("contract")
        source_snapshot_id = payload.get("source_snapshot_id")
        if (
            isinstance(source_snapshot, dict)
            and isinstance(source_snapshot_id, str)
            and source_snapshot_id != _snapshot_id(source_snapshot)
        ):
            raise ProjectionGenerationError(f"projection component source snapshot identity mismatch: {component}")
        if (
            not isinstance(schema_version, str)
            or not schema_version
            or not isinstance(revision, str)
            or not revision
            or not isinstance(source_snapshot, dict)
            or not isinstance(contract, dict)
            or not isinstance(source_snapshot_id, str)
        ):
            raise ProjectionGenerationError(f"projection component manifest is incomplete: {component}")
        return ProjectionComponentManifest(
            generation_id=staged.generation_id,
            component=component,
            schema_version=schema_version,
            revision=revision,
            source_snapshot=source_snapshot,
            source_snapshot_id=source_snapshot_id,
            contract=contract,
            status=status,
        )


def _atomic_write_json(path: Path, payload: Mapping[str, object], *, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    except OSError as exc:
        raise ProjectionGenerationError(f"cannot write projection manifest: {path.name}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _layout_from_payload(graph_home_path: Path, payload: object) -> ProjectionLayout | None:
    if not isinstance(payload, dict):
        raise ProjectionGenerationError("projection manifest must contain an object")
    generation_id = payload.get("generation_id")
    relative_path = payload.get("generation_path")
    if not isinstance(generation_id, str) or not isinstance(relative_path, str):
        raise ProjectionGenerationError("projection manifest is incomplete")
    manager = ProjectionGenerationManager(graph_home_path)
    candidate = manager._validated_generation_path(relative_path)
    if candidate.name != generation_id or not candidate.is_dir():
        raise ProjectionGenerationError("projection generation identity or directory is invalid")
    return ProjectionLayout(generation_id=generation_id, root_path=candidate)


def _validate_component_name(component: str) -> None:
    if component not in PROJECTION_COMPONENTS:
        raise ProjectionGenerationError(f"unsupported projection component: {component}")


def _validate_run_id(run_id: str) -> None:
    if not run_id or any(character not in _SAFE_RUN_ID_CHARACTERS for character in run_id):
        raise ProjectionGenerationError("projection run id is invalid")


def _json_mapping(value: Mapping[str, object], field_name: str) -> dict[str, object]:
    try:
        encoded = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
        loaded = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ProjectionGenerationError(f"{field_name} must be JSON serializable") from exc
    if not isinstance(loaded, dict):
        raise ProjectionGenerationError(f"{field_name} must be a JSON object")
    return loaded


def _snapshot_id(snapshot: Mapping[str, object]) -> str:
    canonical = json.dumps(dict(snapshot), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_safe_generation_id(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in "-_" for character in value)
