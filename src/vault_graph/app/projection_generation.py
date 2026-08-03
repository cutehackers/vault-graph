from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from vault_graph.errors import VaultGraphError


class ProjectionGenerationError(VaultGraphError):
    pass


@dataclass(frozen=True)
class ProjectionLayout:
    generation_id: str
    root_path: Path


class ProjectionGenerationManager:
    """Stages rebuildable projections and atomically selects the readable generation."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path.expanduser().resolve()
        self._projection_root = self._state_path / "projections"
        self._generations_root = self._projection_root / "generations"
        self._active_manifest = self._projection_root / "active.json"

    def stage(self) -> ProjectionLayout:
        generation_id = uuid.uuid4().hex
        root_path = self._generations_root / generation_id
        root_path.mkdir(parents=True, exist_ok=False)
        return ProjectionLayout(generation_id=generation_id, root_path=root_path)

    def active_layout(self) -> ProjectionLayout | None:
        if not self._active_manifest.exists():
            return None
        payload = json.loads(self._active_manifest.read_text(encoding="utf-8"))
        generation_id = str(payload.get("generation_id", ""))
        relative_path = str(payload.get("generation_path", ""))
        if not generation_id or not relative_path:
            raise ProjectionGenerationError("active projection manifest is incomplete")
        candidate = self._validated_generation_path(relative_path)
        if candidate.name != generation_id:
            raise ProjectionGenerationError("active projection generation identity mismatch")
        if not candidate.is_dir():
            raise ProjectionGenerationError("active projection generation is missing")
        return ProjectionLayout(generation_id=generation_id, root_path=candidate)

    def activate(self, staged: ProjectionLayout) -> None:
        expected = self._validated_generation_path(staged.root_path.relative_to(self._state_path).as_posix())
        if expected != staged.root_path.resolve() or not expected.is_dir():
            raise ProjectionGenerationError("staged projection generation is invalid")
        self._projection_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "generation_id": staged.generation_id,
            "generation_path": staged.root_path.relative_to(self._state_path).as_posix(),
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=".active-", suffix=".json", dir=self._projection_root)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self._active_manifest)
        finally:
            temporary_path.unlink(missing_ok=True)

    def discard(self, staged: ProjectionLayout) -> None:
        active = self.active_layout()
        if active is not None and active.root_path == staged.root_path.resolve():
            raise ProjectionGenerationError("cannot discard the active projection generation")
        validated = self._validated_generation_path(staged.root_path.relative_to(self._state_path).as_posix())
        if validated.exists():
            shutil.rmtree(validated)

    def _validated_generation_path(self, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise ProjectionGenerationError("projection generation path escapes state root")
        candidate = (self._state_path / raw).resolve()
        generations_root = self._generations_root.resolve()
        if candidate.parent != generations_root or candidate.is_symlink():
            raise ProjectionGenerationError("projection generation path is not a direct generation child")
        return candidate
