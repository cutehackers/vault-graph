"""Read and write the embedding settings file `<graph-home>/configs/embedding.json`.

This module checks only the file format. It does not know the preset list, so an
unknown preset name is reported by the code that builds the embedding provider.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vault_graph.errors import CatalogError

DEFAULT_MODELS_DIR = Path("~/llm/models")
"""The only place that defines the default model folder."""

_FORMAT_VERSION = 1
_MAX_BYTES = 4096
_KEYS = frozenset({"version", "model", "models_dir"})


@dataclass(frozen=True)
class EmbeddingSelection:
    model: str | None
    models_dir: Path


def load_embedding_selection(path: Path) -> EmbeddingSelection:
    """Return the saved selection, or the default when the file does not exist.

    A missing file is not created. Any other problem raises `CatalogError` naming the path.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return EmbeddingSelection(model=None, models_dir=DEFAULT_MODELS_DIR)
    except OSError as exc:
        raise CatalogError(f"embedding settings file is not a readable regular file: {path}") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise CatalogError(f"embedding settings file is not a regular file: {path}")
            raw = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise CatalogError(f"embedding settings file cannot be read: {path}") from exc
    if len(raw) > _MAX_BYTES:
        raise CatalogError(f"embedding settings file is larger than {_MAX_BYTES} bytes: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"embedding settings file is not valid JSON: {path}") from exc
    return _selection_from_payload(path, payload)


def save_embedding_selection(path: Path, selection: EmbeddingSelection) -> None:
    """Write the selection through a temporary file and `os.replace`."""
    if not selection.models_dir.is_absolute():
        raise CatalogError(f"models_dir must be an absolute path to save {path}: {selection.models_dir}")
    payload = {"version": _FORMAT_VERSION, "model": selection.model, "models_dir": str(selection.models_dir)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".embedding-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _selection_from_payload(path: Path, payload: Any) -> EmbeddingSelection:
    if not isinstance(payload, dict):
        raise CatalogError(f"embedding settings file must contain a JSON object: {path}")
    keys = set(payload)
    if unknown := sorted(keys - _KEYS):
        raise CatalogError(f"embedding settings file has unknown keys {unknown}: {path}")
    if missing := sorted(_KEYS - keys):
        raise CatalogError(f"embedding settings file is missing keys {missing}: {path}")
    version = payload["version"]
    if type(version) is not int or version != _FORMAT_VERSION:
        raise CatalogError(f"embedding settings file version must be {_FORMAT_VERSION}, got {version!r}: {path}")
    model = payload["model"]
    if model is not None and (not isinstance(model, str) or not model):
        raise CatalogError(f"embedding settings file model must be a non-empty string or null: {path}")
    models_dir = payload["models_dir"]
    if not isinstance(models_dir, str) or not Path(models_dir).is_absolute():
        raise CatalogError(f"embedding settings file models_dir must be an absolute path string: {path}")
    return EmbeddingSelection(model=model, models_dir=Path(models_dir))
