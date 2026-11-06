"""Read and write the session export settings file `<graph-home>/configs/session-export.json`.

Spec 2026-11-05 §4.2.4 설정. The file holds ``path`` (absolute export folder outside every Vault),
``agents`` (which agents to export) and ``raw`` (copy the source files too, default true). When the
file exists, ``vg hook capture`` exports each captured session to the same folder. This module
checks only the file format. Whether ``path`` is inside a Vault is checked when an export runs.
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

SESSION_EXPORT_AGENTS = ("claude-code", "codex")
"""Agent names an export may name. Codex has no adapter until backlog B-1."""

_MAX_BYTES = 4096
_REQUIRED_KEYS = frozenset({"path", "agents"})
_KEYS = frozenset({"path", "agents", "raw"})


@dataclass(frozen=True)
class SessionExportSettings:
    path: Path
    agents: tuple[str, ...]
    raw: bool = True


def session_export_settings_path(graph_home: Path) -> Path:
    return graph_home / "configs" / "session-export.json"


def load_session_export_settings(path: Path) -> SessionExportSettings | None:
    """Return the settings, or None when the file does not exist. Other problems raise `CatalogError`."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CatalogError(f"session export settings file is not a readable regular file: {path}") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CatalogError(f"session export settings file is not a regular file: {path}")
            raw = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise CatalogError(f"session export settings file cannot be read: {path}") from exc
    if len(raw) > _MAX_BYTES:
        raise CatalogError(f"session export settings file is larger than {_MAX_BYTES} bytes: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"session export settings file is not valid JSON: {path}") from exc
    return _settings_from_payload(path, payload)


def save_session_export_settings(path: Path, settings: SessionExportSettings) -> None:
    """Write the settings with owner-only permission through a temporary file and `os.replace`."""
    _check_values(path, str(settings.path), list(settings.agents), settings.raw)
    payload = {"path": str(settings.path), "agents": list(settings.agents), "raw": settings.raw}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".session-export-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            os.chmod(temporary, 0o600)
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _settings_from_payload(path: Path, payload: Any) -> SessionExportSettings:
    if not isinstance(payload, dict):
        raise CatalogError(f"session export settings file must contain a JSON object: {path}")
    keys = set(payload)
    if unknown := sorted(keys - _KEYS):
        raise CatalogError(f"session export settings file has unknown keys {unknown}: {path}")
    if missing := sorted(_REQUIRED_KEYS - keys):
        raise CatalogError(f"session export settings file is missing keys {missing}: {path}")
    raw = payload.get("raw", True)
    _check_values(path, payload["path"], payload["agents"], raw)
    return SessionExportSettings(path=Path(payload["path"]), agents=tuple(payload["agents"]), raw=raw)


def _check_values(path: Path, export_path: object, agents: object, raw: object) -> None:
    if not isinstance(export_path, str) or not Path(export_path).is_absolute():
        raise CatalogError(f"session export settings path must be an absolute path string: {path}")
    if (
        not isinstance(agents, list)
        or not agents
        or any(agent not in SESSION_EXPORT_AGENTS for agent in agents)
        or len(set(agents)) != len(agents)
    ):
        raise CatalogError(
            "session export settings agents must be a non-empty list without repeats of "
            f"{list(SESSION_EXPORT_AGENTS)}: {path}"
        )
    if type(raw) is not bool:
        raise CatalogError(f"session export settings raw must be true or false: {path}")
