"""Read and write the rerank settings file `<graph-home>/configs/reranker.json`.

The file holds `version`, `enabled`, and `model`. A missing file means reranking is off. The model folder is
not stored here: reranking uses the `models_dir` of `configs/embedding.json`. This module checks only the
file format. It does not know the preset list, so an unknown preset name is reported by the code that builds
the reranker.
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

_FORMAT_VERSION = 1
_MAX_BYTES = 4096
_KEYS = frozenset({"version", "enabled", "model"})


@dataclass(frozen=True)
class RerankerSelection:
    enabled: bool
    model: str | None


def reranker_config_path(graph_home_path: Path) -> Path:
    """The only place that names the rerank settings file inside a Graph Home."""
    return graph_home_path / "configs" / "reranker.json"


def load_reranker_selection(path: Path) -> RerankerSelection:
    """Return the saved selection, or "off" when the file does not exist.

    A missing file is not created. Any other problem raises `CatalogError` naming the path.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return RerankerSelection(enabled=False, model=None)
    except OSError as exc:
        raise CatalogError(f"reranker settings file is not a readable regular file: {path}") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise CatalogError(f"reranker settings file is not a regular file: {path}")
            raw = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise CatalogError(f"reranker settings file cannot be read: {path}") from exc
    if len(raw) > _MAX_BYTES:
        raise CatalogError(f"reranker settings file is larger than {_MAX_BYTES} bytes: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"reranker settings file is not valid JSON: {path}") from exc
    return _selection_from_payload(path, payload)


def save_reranker_selection(path: Path, selection: RerankerSelection) -> None:
    """Write the selection through a temporary file and `os.replace`."""
    if not selection.model:
        raise CatalogError(f"reranker model must be a non-empty string to save {path}")
    payload = {"version": _FORMAT_VERSION, "enabled": selection.enabled, "model": selection.model}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".reranker-", suffix=".tmp", delete=False
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


def _selection_from_payload(path: Path, payload: Any) -> RerankerSelection:
    if not isinstance(payload, dict):
        raise CatalogError(f"reranker settings file must contain a JSON object: {path}")
    keys = set(payload)
    if unknown := sorted(keys - _KEYS):
        raise CatalogError(f"reranker settings file has unknown keys {unknown}: {path}")
    if missing := sorted(_KEYS - keys):
        raise CatalogError(f"reranker settings file is missing keys {missing}: {path}")
    version = payload["version"]
    if type(version) is not int or version != _FORMAT_VERSION:
        raise CatalogError(f"reranker settings file version must be {_FORMAT_VERSION}, got {version!r}: {path}")
    enabled = payload["enabled"]
    if type(enabled) is not bool:
        raise CatalogError(f"reranker settings file enabled must be true or false: {path}")
    model = payload["model"]
    if not isinstance(model, str) or not model:
        raise CatalogError(f"reranker settings file model must be a non-empty string: {path}")
    return RerankerSelection(enabled=enabled, model=model)
