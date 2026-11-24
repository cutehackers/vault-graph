"""Read and write the dreaming settings file `<graph-home>/configs/dream.json` (spec 2026-11-19 OD2, OD3, OD4).

The file holds `version`, `enabled`, `model`, the five limits of a dream run and `run_at`, the local "HH:MM" time
of the scheduled run (spec 2026-11-24-dream-schedule-time D1, D6). A version 1 file written before `run_at` existed
reads as "01:00" (I5); every save writes the key. A missing file means dreaming is
off with the default limits (OD2: the user turns it on with `vg dream on`). A broken file also means off, and the
reading carries the reason so `vg dream status` can show it.

The limits (OD3):

- `pending_cap`: no run while the write Vault has this many memory proposals waiting for review.
- `proposals_per_run`: the most proposals one run sends.
- `interval_hours`: the shortest time between two runs for one project.
- `bundle_limit`: the most session exchanges one run judges.
- `due_exchanges`: a run is due when this many exchanges were never judged, or the backlog is overdue.

This module also names the other Graph Home paths of dreaming, so the worker and `vg dream status` use the same
paths. It does not read those.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from vault_graph.errors import CatalogError

DREAM_MODEL = "claude-sonnet-5-5"
"""Model the dream judge runs (OD4)."""

_FORMAT_VERSION = 1
_MAX_BYTES = 4096
_LIMIT_KEYS = ("pending_cap", "proposals_per_run", "interval_hours", "bundle_limit", "due_exchanges")
_KEYS = frozenset({"version", "enabled", "model", *_LIMIT_KEYS})
_OPTIONAL_KEYS = frozenset({"run_at"})
DEFAULT_RUN_AT = "01:00"
"""Local time of the scheduled run when the user has not chosen one (D1)."""
_RUN_AT = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", re.ASCII)

DreamSettingsSource = Literal["default", "file", "broken"]


@dataclass(frozen=True)
class DreamSettings:
    enabled: bool = False
    model: str = DREAM_MODEL
    pending_cap: int = 10
    proposals_per_run: int = 10
    interval_hours: int = 24
    bundle_limit: int = 40
    due_exchanges: int = 20
    run_at: str = DEFAULT_RUN_AT


@dataclass(frozen=True)
class DreamSettingsReading:
    """The settings to act on, where they came from, and why the file was rejected when it was."""

    settings: DreamSettings
    source: DreamSettingsSource
    problem: str | None = None


def dream_settings_path(graph_home_path: Path) -> Path:
    """The only place that names the dreaming settings file inside a Graph Home."""
    return graph_home_path / "configs" / "dream.json"


def dream_judged_path(graph_home_path: Path) -> Path:
    """Candidates a dream run judged without proposing. Only the dream worker reads it."""
    return graph_home_path / "dream" / "judged.jsonl"


def dream_runs_path(graph_home_path: Path) -> Path:
    """One line per dream run, with the review paths of the proposals it sent."""
    return graph_home_path / "logs" / "dream-runs.jsonl"


def read_dream_settings(path: Path) -> DreamSettingsReading:
    """Return the settings to act on. Never raises for file problems.

    A missing file is not created and reads as off with the default limits. Any other problem also reads as off,
    with the reason in `problem`.
    """
    try:
        settings = _load(path)
    except CatalogError as exc:
        return DreamSettingsReading(settings=DreamSettings(), source="broken", problem=str(exc))
    if settings is None:
        return DreamSettingsReading(settings=DreamSettings(), source="default")
    return DreamSettingsReading(settings=settings, source="file")


def save_dream_settings(path: Path, settings: DreamSettings) -> None:
    """Write the settings through a temporary file and `os.replace`. Invalid settings raise `CatalogError`."""
    payload: dict[str, Any] = {"version": _FORMAT_VERSION, "enabled": settings.enabled, "model": settings.model}
    payload.update({key: getattr(settings, key) for key in _LIMIT_KEYS})
    payload["run_at"] = settings.run_at
    _settings_from_payload(path, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".dream-", suffix=".tmp", delete=False
        ) as stream:
            temporary = stream.name
            json.dump(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def _load(path: Path) -> DreamSettings | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CatalogError(f"dream settings file is not a readable regular file: {path}") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CatalogError(f"dream settings file is not a regular file: {path}")
            raw = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise CatalogError(f"dream settings file cannot be read: {path}") from exc
    if len(raw) > _MAX_BYTES:
        raise CatalogError(f"dream settings file is larger than {_MAX_BYTES} bytes: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"dream settings file is not valid JSON: {path}") from exc
    return _settings_from_payload(path, payload)


def _settings_from_payload(path: Path, payload: Any) -> DreamSettings:
    if not isinstance(payload, dict):
        raise CatalogError(f"dream settings file must contain a JSON object: {path}")
    keys = set(payload)
    if unknown := sorted(keys - _KEYS - _OPTIONAL_KEYS):
        raise CatalogError(f"dream settings file has unknown keys {unknown}: {path}")
    if missing := sorted(_KEYS - keys):
        raise CatalogError(f"dream settings file is missing keys {missing}: {path}")
    version = payload["version"]
    if type(version) is not int or version != _FORMAT_VERSION:
        raise CatalogError(f"dream settings file version must be {_FORMAT_VERSION}, got {version!r}: {path}")
    enabled = payload["enabled"]
    if type(enabled) is not bool:
        raise CatalogError(f"dream settings file enabled must be true or false: {path}")
    model = payload["model"]
    if not isinstance(model, str) or not model:
        raise CatalogError(f"dream settings file model must be a non-empty string: {path}")
    for key in _LIMIT_KEYS:
        value = payload[key]
        if type(value) is not int or value < 1:
            raise CatalogError(f"dream settings file {key} must be a whole number of at least 1: {path}")
    run_at = payload.get("run_at", DEFAULT_RUN_AT)
    if not is_valid_run_at(run_at):
        raise CatalogError(f"dream settings file run_at must be HH:MM from 00:00 to 23:59, got {run_at!r}: {path}")
    return DreamSettings(enabled=enabled, model=model, run_at=run_at, **{key: payload[key] for key in _LIMIT_KEYS})


def is_valid_run_at(value: object) -> bool:
    """True when `value` is a two-digit hour 00-23, a colon and a two-digit minute 00-59 (D6)."""
    return isinstance(value, str) and _RUN_AT.fullmatch(value) is not None


__all__ = [
    "DEFAULT_RUN_AT",
    "DREAM_MODEL",
    "DreamSettings",
    "DreamSettingsReading",
    "DreamSettingsSource",
    "dream_judged_path",
    "dream_runs_path",
    "dream_settings_path",
    "is_valid_run_at",
    "read_dream_settings",
    "save_dream_settings",
]
