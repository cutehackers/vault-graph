"""Find and read Claude Code auto-memory (L1) folders (spec 2026-11-05 §4.4.5, A-24 adapter part).

The folder rule follows Claude Code 2.1.319 (read from its bundled source):

1. ``autoMemoryDirectory`` from the first settings file that has it, in the order policy
   (managed settings), local (``<project>/.claude/settings.local.json``), user
   (``<config dir>/settings.json``). Checked-in ``.claude/settings.json`` is not read: Claude Code
   documents that it ignores this key there. A leading ``~/`` is the home folder. The value is the
   memory folder itself. A value that is not an absolute path is unusable and Claude Code then
   uses the default folder, not the next settings file.
2. Otherwise ``<config dir>/projects/<key>/memory/`` where the config dir is ``$CLAUDE_CONFIG_DIR``
   or ``~/.claude`` and the key is the project root with every non-alphanumeric character replaced
   by ``-``. A key over 200 characters is cut to 200 and gets a hash suffix. vg does not compute
   that hash: it takes the single existing folder that starts with the cut key.

The project root is the ``root`` string of ``vault-map.json``, as in the Vault ``memory-scan``
(``vault-builder:tools/wiki/lib/memory_scan.py``). This module only reads files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

CLAUDE_CONFIG_ENV = "CLAUDE_CONFIG_DIR"
SETTING_KEY = "autoMemoryDirectory"
INDEX_NOTE = "MEMORY.md"
MEMORY_FOLDER = "memory"
MAX_KEY_LENGTH = 200
SOURCE_PAGES = Path("wiki") / "sources"

FolderSource = Literal["autoMemoryDirectory", "default"]


@dataclass(frozen=True)
class MemoryFolder:
    """Where one project's L1 notes live and which rule chose it."""

    project_root: str
    path: Path
    source: FolderSource
    settings_file: Path | None = None


@dataclass(frozen=True)
class MemoryNote:
    name: str
    path: Path
    sha256: str
    text: str


def claude_config_dir(environ: Mapping[str, str]) -> Path:
    configured = environ.get(CLAUDE_CONFIG_ENV)
    if configured:
        return Path(configured).expanduser()
    return _home(environ) / ".claude"


def default_managed_settings_path() -> Path:
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode/managed-settings.json")
    return Path("/etc/claude-code/managed-settings.json")


def memory_folder_key(project_root: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", project_root)


def locate_memory_folder(
    project_root: str,
    *,
    environ: Mapping[str, str] | None = None,
    managed_settings_path: Path | None = None,
) -> MemoryFolder:
    """Return the L1 folder of the project at ``project_root``. The folder may not exist."""

    env = os.environ if environ is None else environ
    config_dir = claude_config_dir(env)
    settings_files = [
        *([managed_settings_path] if managed_settings_path is not None else []),
        Path(project_root).expanduser() / ".claude" / "settings.local.json",
        config_dir / "settings.json",
    ]
    for settings_file in settings_files:
        value = _setting(settings_file)
        if value is None:
            continue
        configured = _configured_folder(value, env)
        if configured is not None:
            return MemoryFolder(project_root, configured, "autoMemoryDirectory", settings_file)
        break
    return MemoryFolder(project_root, _default_folder(config_dir / "projects", project_root), "default")


def read_memory_notes(folder: Path) -> tuple[MemoryNote, ...]:
    """Read every ``*.md`` note except ``MEMORY.md``, sorted by name. Nothing is written."""

    if not folder.is_dir():
        return ()
    notes = []
    for path in sorted(folder.glob("*.md")):
        if path.name == INDEX_NOTE or not path.is_file():
            continue
        data = path.read_bytes()
        notes.append(
            MemoryNote(
                name=path.name,
                path=path,
                sha256=hashlib.sha256(data).hexdigest(),
                text=data.decode("utf-8", errors="replace"),
            )
        )
    return tuple(notes)


def memory_folder_problem(folder: Path) -> str | None:
    """Why the L1 folder cannot be read, or None when it can. A missing folder counts (spec 2026-11-05 §6)."""

    try:
        if not folder.is_dir():
            return f"The L1 memory folder {folder} does not exist."
        with os.scandir(folder):
            pass
    except OSError as exc:
        return f"The L1 memory folder {folder} cannot be read: {exc.strerror or exc}."
    return None


def imported_raw_hashes(vault_root: Path) -> dict[str, tuple[str, ...]]:
    """Map each ``raw_sha256`` of ``wiki/sources/*.md`` to its pages, as the Vault ``memory-scan`` does."""

    sources = vault_root / SOURCE_PAGES
    if not sources.is_dir():
        return {}
    found: dict[str, list[str]] = {}
    for page in sorted(sources.glob("*.md")):
        try:
            block = split_frontmatter(page.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        value = parse_vault_frontmatter(block[0]).get("raw_sha256") if block is not None else None
        if isinstance(value, str) and value:
            found.setdefault(value, []).append(page.relative_to(vault_root).as_posix())
    return {digest: tuple(pages) for digest, pages in found.items()}


def _home(environ: Mapping[str, str]) -> Path:
    home = environ.get("HOME")
    return Path(home) if home else Path.home()


def _setting(settings_file: Path) -> str | None:
    try:
        data = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    value = data.get(SETTING_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def _configured_folder(value: str, environ: Mapping[str, str]) -> Path | None:
    """Expand ``~/`` and reject what Claude Code rejects: relative, too short, or escaping home."""

    text = value
    if text.startswith(("~/", "~\\")):
        rest = os.path.normpath(text[2:] or ".")
        if rest in {".", ".."} or rest.startswith(("../", "..\\")):
            return None
        text = str(_home(environ) / rest)
    normalized = os.path.normpath(text).rstrip("/\\")
    if not os.path.isabs(normalized) or len(normalized) < 3 or "\x00" in normalized:
        return None
    return Path(normalized)


def _default_folder(projects: Path, project_root: str) -> Path:
    key = memory_folder_key(project_root)
    if len(key) <= MAX_KEY_LENGTH:
        return projects / key / MEMORY_FOLDER
    prefix = key[:MAX_KEY_LENGTH]
    matches = sorted(path for path in projects.glob(f"{prefix}-*") if path.is_dir()) if projects.is_dir() else []
    if len(matches) == 1:
        return matches[0] / MEMORY_FOLDER
    return projects / prefix / MEMORY_FOLDER


__all__ = [
    "MemoryFolder",
    "MemoryNote",
    "claude_config_dir",
    "default_managed_settings_path",
    "imported_raw_hashes",
    "locate_memory_folder",
    "memory_folder_key",
    "memory_folder_problem",
    "read_memory_notes",
]
