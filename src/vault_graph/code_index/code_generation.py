"""Independent generation management for the rebuildable code projection.

The code projection deliberately has its own active manifest.  The existing
``ProjectionGenerationManager`` owns Vault metadata/vector/graph generations;
calling it from code indexing would accidentally switch the Vault projection
and violate the source-of-truth boundary.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from vault_graph.errors import VaultGraphError


class CodeGenerationError(VaultGraphError):
    """Raised when a code generation layout or manifest is unsafe."""


@dataclass(frozen=True)
class CodeGenerationLayout:
    generation_id: str
    root_path: Path
    repository_ids: tuple[str, ...]

    @property
    def database_path(self) -> Path:
        return self.root_path / "code.sqlite3"


class CodeProjectionGenerationManager:
    """Stage and atomically activate code projection generations."""

    def __init__(self, state_path: Path) -> None:
        self._state_path = state_path.expanduser().resolve()
        self._projection_root = self._state_path / "projections" / "code"
        self._generations_root = self._projection_root / "generations"
        self._active_manifest = self._projection_root / "active.json"

    def stage(self, repository_ids: tuple[str, ...]) -> CodeGenerationLayout:
        repositories = _normalize_repository_ids(repository_ids)
        self._assert_roots_are_local()
        self._generations_root.mkdir(parents=True, exist_ok=True)
        generation_id = uuid.uuid4().hex
        root_path = self._generations_root / generation_id
        root_path.mkdir(parents=False, exist_ok=False)
        return CodeGenerationLayout(
            generation_id=generation_id,
            root_path=root_path,
            repository_ids=repositories,
        )

    def active_layout(self, repository_ids: tuple[str, ...]) -> CodeGenerationLayout | None:
        repositories = _normalize_repository_ids(repository_ids)
        if not self._active_manifest.exists():
            return None
        if self._active_manifest.is_symlink():
            raise CodeGenerationError("code active manifest must not be a symlink")
        try:
            payload = json.loads(self._active_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CodeGenerationError("code active manifest is unreadable") from exc
        if not isinstance(payload, dict):
            raise CodeGenerationError("code active manifest must contain an object")
        generation_id = _required_text(payload.get("generation_id"), "generation_id")
        relative_path = _required_text(payload.get("generation_path"), "generation_path")
        manifest_repositories = _normalize_repository_ids(payload.get("repository_ids", ()))
        if repositories and not set(repositories).issubset(manifest_repositories):
            return None
        candidate = self._validated_generation_path(relative_path)
        if candidate.name != generation_id or not candidate.is_dir():
            raise CodeGenerationError("active code generation identity or directory is invalid")
        return CodeGenerationLayout(
            generation_id=generation_id,
            root_path=candidate,
            repository_ids=manifest_repositories,
        )

    def activate(self, staged: CodeGenerationLayout) -> None:
        candidate = self._validate_staged_layout(staged)
        self._assert_roots_are_local()
        self._projection_root.mkdir(parents=True, exist_ok=True)
        payload = {
            "generation_id": staged.generation_id,
            "generation_path": candidate.relative_to(self._state_path).as_posix(),
            "repository_ids": list(staged.repository_ids),
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".code-active-",
            suffix=".json",
            dir=self._projection_root,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self._active_manifest)
        except OSError as exc:
            raise CodeGenerationError("cannot activate code generation") from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    def discard(self, staged: CodeGenerationLayout) -> None:
        candidate = self._validate_staged_layout(staged)
        active = self.active_layout(())
        if active is not None and active.root_path == candidate:
            raise CodeGenerationError("cannot discard the active code generation")
        try:
            shutil.rmtree(candidate)
        except OSError as exc:
            raise CodeGenerationError("cannot discard code generation") from exc

    def _validate_staged_layout(self, staged: CodeGenerationLayout) -> Path:
        if not isinstance(staged, CodeGenerationLayout):
            raise CodeGenerationError("staged layout is invalid")
        if not _is_safe_generation_id(staged.generation_id):
            raise CodeGenerationError("generation_id is invalid")
        repositories = _normalize_repository_ids(staged.repository_ids)
        if repositories != staged.repository_ids:
            raise CodeGenerationError("repository_ids are not normalized")
        raw_path = staged.root_path.expanduser()
        if raw_path.is_symlink():
            raise CodeGenerationError("staged code generation must not be a symlink")
        try:
            relative_path = raw_path.resolve().relative_to(self._state_path).as_posix()
        except ValueError as exc:
            raise CodeGenerationError("staged code generation escapes state root") from exc
        candidate = self._validated_generation_path(relative_path)
        if candidate != staged.root_path.expanduser().resolve() or not candidate.is_dir():
            raise CodeGenerationError("staged code generation is invalid")
        return candidate

    def _validated_generation_path(self, relative_path: str) -> Path:
        raw = Path(relative_path)
        if raw.is_absolute() or ".." in raw.parts:
            raise CodeGenerationError("code generation path escapes state root")
        expected_prefix = Path("projections") / "code" / "generations"
        if raw.parent != expected_prefix or not raw.name or not _is_safe_generation_id(raw.name):
            raise CodeGenerationError("code generation path is not a direct generation child")
        self._assert_roots_are_local()
        raw_candidate = self._state_path / raw
        if raw_candidate.is_symlink():
            raise CodeGenerationError("code generation path must not be a symlink")
        candidate = raw_candidate.resolve()
        generations_root = self._generations_root.resolve()
        if raw_candidate.parent.resolve() != generations_root or candidate.parent != generations_root:
            raise CodeGenerationError("code generation path is not a direct generation child")
        return candidate

    def _assert_roots_are_local(self) -> None:
        for root in (self._projection_root, self._generations_root):
            if root.is_symlink():
                raise CodeGenerationError("code projection state directories must not be symlinks")


def _normalize_repository_ids(repository_ids: object) -> tuple[str, ...]:
    if repository_ids is None:
        return ()
    if not isinstance(repository_ids, (tuple, list)):
        raise CodeGenerationError("repository_ids must be a tuple or list")
    normalized = tuple(str(repository_id).strip() for repository_id in repository_ids)
    if any(not repository_id for repository_id in normalized):
        raise CodeGenerationError("repository_ids must not contain empty values")
    if len(set(normalized)) != len(normalized):
        raise CodeGenerationError("repository_ids must be unique")
    return normalized


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CodeGenerationError(f"code active manifest is missing {field_name}")
    return value


def _is_safe_generation_id(value: str) -> bool:
    return bool(value) and all(character.isalnum() or character in "-_" for character in value)
