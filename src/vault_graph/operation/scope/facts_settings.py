"""Read and write the session fact extraction settings file `<graph-home>/configs/facts.json`.

Spec 2026-11-16 D18, D19, F13 and spec 2026-11-25-facts-extractor-auto D4, D7. The file holds `version`,
`enabled`, `extractor` (`auto`, `claude` or `llama-server`), `endpoint` and `model`. A missing file means extraction
is on with the `auto` extractor. A broken file means extraction is off, and the reading carries the reason so
`vg facts status` can show it (F13).

`auto` uses `llama-server` at `endpoint` with `model` when that server answers, otherwise `claude` with
`CLAUDE_FACTS_MODEL`. `resolve_facts_settings` turns `auto` into the settings of the extractor that runs; whoever
calls it decides how to check the server (`interface/composition/adapters/llama_health.py`).

This module also names the other Graph Home paths of fact extraction, the job queue folder and the failure
log, so the worker and `vg facts status` use the same paths. It does not read those two.
"""

from __future__ import annotations

import json
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

from vault_graph.errors import CatalogError

FACT_EXTRACTORS = ("auto", "claude", "llama-server")
"""Extractor names the settings file may name. `auto` picks `llama-server` when it answers, else `claude`."""

CLAUDE_FACTS_MODEL = "claude-sonnet-5-5"
"""Model the Claude CLI extractor runs (D17)."""

LOCAL_FACTS_ENDPOINT = "http://127.0.0.1:8080"
"""Default `llama-server` address (its own default port)."""

_FORMAT_VERSION = 1
_MAX_BYTES = 4096
_KEYS = frozenset({"version", "enabled", "extractor", "endpoint", "model"})

FactsSettingsSource = Literal["default", "file", "broken"]


@dataclass(frozen=True)
class FactsSettings:
    enabled: bool
    extractor: str
    endpoint: str | None
    model: str


@dataclass(frozen=True)
class FactsSettingsReading:
    """The settings to act on, where they came from, and why the file was rejected when it was."""

    settings: FactsSettings
    source: FactsSettingsSource
    problem: str | None = None


def facts_settings_path(graph_home_path: Path) -> Path:
    """The only place that names the fact extraction settings file inside a Graph Home."""
    return graph_home_path / "configs" / "facts.json"


def facts_queue_dir(graph_home_path: Path) -> Path:
    """Folder of fact extraction job files written after a capture (spec 2026-11-16 §4 B.1)."""
    return graph_home_path / "facts" / "queue"


def facts_failures_path(graph_home_path: Path) -> Path:
    """Failure log of the fact worker (spec 2026-11-16 F7)."""
    return graph_home_path / "logs" / "facts-failures.json"


def facts_last_job_path(graph_home_path: Path) -> Path:
    """Record of the last job that chose an extractor (spec 2026-11-25-facts-extractor-auto D9)."""
    return graph_home_path / "logs" / "facts-last-job.json"


def local_facts_model() -> str:
    """Default local model file for `llama-server` (D18)."""
    return str(Path.home() / "llm" / "models" / "Qwen3.5-27B-Q4_K_M.gguf")


def default_facts_settings(extractor: str) -> FactsSettings:
    """Turned-on settings with the default endpoint and model of `extractor`."""
    if extractor == "claude":
        return FactsSettings(enabled=True, extractor="claude", endpoint=None, model=CLAUDE_FACTS_MODEL)
    if extractor in ("auto", "llama-server"):
        return FactsSettings(
            enabled=True, extractor=extractor, endpoint=LOCAL_FACTS_ENDPOINT, model=local_facts_model()
        )
    raise CatalogError(f"unknown fact extractor {extractor!r}; available: {', '.join(FACT_EXTRACTORS)}")


def read_facts_settings(path: Path) -> FactsSettingsReading:
    """Return the settings to act on. Never raises for file problems.

    A missing file is not created and reads as on with `auto`. Any other problem reads as off, with the
    reason in `problem`.
    """
    try:
        settings = _load(path)
    except CatalogError as exc:
        off = replace(default_facts_settings("auto"), enabled=False)
        return FactsSettingsReading(settings=off, source="broken", problem=str(exc))
    if settings is None:
        return FactsSettingsReading(settings=default_facts_settings("auto"), source="default")
    return FactsSettingsReading(settings=settings, source="file")


def resolve_facts_settings(settings: FactsSettings, *, local_answers: Callable[[str], bool]) -> FactsSettings:
    """The settings of the extractor that runs. Never `auto`.

    `auto` becomes `llama-server` with its endpoint and model when `local_answers(endpoint)` is true, otherwise
    `claude` with `CLAUDE_FACTS_MODEL`. Other settings come back unchanged and `local_answers` is not called.
    """
    if settings.extractor != "auto":
        return settings
    endpoint = settings.endpoint or LOCAL_FACTS_ENDPOINT
    if local_answers(endpoint):
        return FactsSettings(
            enabled=settings.enabled, extractor="llama-server", endpoint=endpoint, model=settings.model
        )
    return FactsSettings(enabled=settings.enabled, extractor="claude", endpoint=None, model=CLAUDE_FACTS_MODEL)


def save_facts_settings(path: Path, settings: FactsSettings) -> None:
    """Write the settings through a temporary file and `os.replace`. Invalid settings raise `CatalogError`."""
    payload = {
        "version": _FORMAT_VERSION,
        "enabled": settings.enabled,
        "extractor": settings.extractor,
        "endpoint": settings.endpoint,
        "model": settings.model,
    }
    _settings_from_payload(path, payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".facts-", suffix=".tmp", delete=False
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


def _load(path: Path) -> FactsSettings | None:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise CatalogError(f"facts settings file is not a readable regular file: {path}") from exc
    try:
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise CatalogError(f"facts settings file is not a regular file: {path}")
            raw = stream.read(_MAX_BYTES + 1)
    except OSError as exc:
        raise CatalogError(f"facts settings file cannot be read: {path}") from exc
    if len(raw) > _MAX_BYTES:
        raise CatalogError(f"facts settings file is larger than {_MAX_BYTES} bytes: {path}")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"facts settings file is not valid JSON: {path}") from exc
    return _settings_from_payload(path, payload)


def _settings_from_payload(path: Path, payload: Any) -> FactsSettings:
    if not isinstance(payload, dict):
        raise CatalogError(f"facts settings file must contain a JSON object: {path}")
    keys = set(payload)
    if unknown := sorted(keys - _KEYS):
        raise CatalogError(f"facts settings file has unknown keys {unknown}: {path}")
    if missing := sorted(_KEYS - keys):
        raise CatalogError(f"facts settings file is missing keys {missing}: {path}")
    version = payload["version"]
    if type(version) is not int or version != _FORMAT_VERSION:
        raise CatalogError(f"facts settings file version must be {_FORMAT_VERSION}, got {version!r}: {path}")
    enabled = payload["enabled"]
    if type(enabled) is not bool:
        raise CatalogError(f"facts settings file enabled must be true or false: {path}")
    extractor = payload["extractor"]
    if extractor not in FACT_EXTRACTORS:
        raise CatalogError(f"facts settings file extractor must be one of {list(FACT_EXTRACTORS)}: {path}")
    model = payload["model"]
    if not isinstance(model, str) or not model:
        raise CatalogError(f"facts settings file model must be a non-empty string: {path}")
    endpoint = payload["endpoint"]
    if extractor == "claude" and endpoint is not None:
        raise CatalogError(f"facts settings file endpoint must be null for the claude extractor: {path}")
    if extractor in ("auto", "llama-server") and (
        not isinstance(endpoint, str) or not endpoint.startswith(("http://", "https://"))
    ):
        raise CatalogError(f"facts settings file endpoint must be an http(s) URL for {extractor}: {path}")
    return FactsSettings(enabled=enabled, extractor=extractor, endpoint=endpoint, model=model)
