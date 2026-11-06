"""Find agent session source files and write a session export folder (spec 2026-11-05 §4.2.4).

M19 (`operation/sessions/`) is pure code. This adapter reads the Claude Code source files, passes
their lines to the adapter as `SourceRecord`s, and writes the export folder:

- ``<out>/raw/<agent>/<session_id>/``: the main ``<session_id>.jsonl`` and ``subagents/`` byte for
  byte, without redaction (``--raw``).
- ``<out>/normalized/<agent>/<session_id>.jsonl``: the ``vg-session-jsonl/1`` file.

Folders this module creates get 0700 and files 0600. A file whose bytes would not change is not
written again, so a second export of the same session keeps every mtime. Source files are read
once, and the same bytes feed both the copy and the normalized file.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from vault_graph.operation.scope.git_command import run_git
from vault_graph.operation.sessions.claude_code_adapter import CLAUDE_CODE_AGENT, ClaudeCodeAdapter
from vault_graph.operation.sessions.models import SourceRecord
from vault_graph.operation.sessions.normalized_jsonl import encode_session

CLAUDE_CONFIG_ENV = "CLAUDE_CONFIG_DIR"
_SESSION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DIR_MODE = 0o700
_FILE_MODE = 0o600

# Folder names that sync services use on macOS, Linux and Windows home folders (spec §4.2.4).
_SYNC_FOLDER_PARTS = (
    ("Library", "Mobile Documents"),  # iCloud Drive
    ("Library", "CloudStorage"),  # Dropbox, Google Drive, OneDrive through File Provider
    ("iCloud Drive",),
    ("iCloudDrive",),
    ("Dropbox",),
    ("Google Drive",),
    ("My Drive",),
    ("OneDrive",),
)


class SessionExportError(Exception):
    """The export cannot start. Nothing has been written."""


@dataclass(frozen=True)
class ClaudeCodeSession:
    """One Claude Code session found under ``<config>/projects/<key>/``.

    ``newest`` is True for the most recently modified main transcript of its project folder. That
    session may still be running, so its last exchange stays open (contract doc, 세션 끝 판단).
    """

    session_id: str
    project_dir: Path
    modified_at: float
    newest: bool

    @property
    def main_file(self) -> Path:
        return self.project_dir / f"{self.session_id}.jsonl"

    @property
    def subagent_dir(self) -> Path:
        return self.project_dir / self.session_id / "subagents"


@dataclass(frozen=True)
class SessionExportResult:
    session_id: str
    normalized_path: Path
    normalized_written: bool
    raw_files_written: int
    raw_files_unchanged: int
    invalid_lines: int
    unknown_record_types: Mapping[str, int] = field(default_factory=dict)


def claude_config_dir(environ: Mapping[str, str] | None = None) -> Path:
    """``$CLAUDE_CONFIG_DIR`` when set and not empty, else ``~/.claude``."""
    env = os.environ if environ is None else environ
    value = env.get(CLAUDE_CONFIG_ENV)
    if value:
        return Path(value).expanduser().absolute()
    return Path("~/.claude").expanduser()


def valid_session_id(value: str) -> bool:
    return bool(_SESSION_ID.match(value)) and ".." not in value


def find_claude_code_sessions(projects_root: Path) -> tuple[tuple[ClaudeCodeSession, ...], tuple[str, ...]]:
    """Return sessions sorted by id, and ids found in more than one project folder (skipped)."""
    found: dict[str, list[ClaudeCodeSession]] = {}
    if not projects_root.is_dir():
        return (), ()
    for project_dir in sorted(path for path in projects_root.iterdir() if path.is_dir() and not path.is_symlink()):
        mains = [
            (path.stem, path.stat().st_mtime)
            for path in project_dir.glob("*.jsonl")
            if path.is_file() and not path.is_symlink() and valid_session_id(path.stem)
        ]
        newest = max(mains, key=lambda item: (item[1], item[0]))[0] if mains else None
        for session_id, modified_at in mains:
            found.setdefault(session_id, []).append(
                ClaudeCodeSession(
                    session_id=session_id,
                    project_dir=project_dir,
                    modified_at=modified_at,
                    newest=session_id == newest,
                )
            )
    sessions = tuple(items[0] for _, items in sorted(found.items()) if len(items) == 1)
    duplicates = tuple(session_id for session_id, items in sorted(found.items()) if len(items) > 1)
    return sessions, duplicates


def select_sessions(
    sessions: Sequence[ClaudeCodeSession], *, session_id: str | None, since: datetime | None
) -> tuple[ClaudeCodeSession, ...]:
    if session_id is not None:
        return tuple(session for session in sessions if session.session_id == session_id)
    if since is not None:
        cutoff = since.timestamp()
        return tuple(session for session in sessions if session.modified_at >= cutoff)
    return tuple(sessions)


def vault_containing(path: Path, vault_roots: Iterable[Path]) -> Path | None:
    """The first Vault root that is ``path`` or one of its parents, comparing real paths."""
    target = _real(path)
    for root in vault_roots:
        real_root = _real(root)
        if target == real_root or real_root in target.parents:
            return root
    return None


def location_warnings(path: Path, *, home: Path | None = None) -> tuple[str, ...]:
    """Warnings for an export folder inside a git work tree or a known sync folder. Writing goes on."""
    target = _real(path)
    warnings: list[str] = []
    existing = _nearest_existing(target)
    if run_git(existing, "rev-parse", "--is-inside-work-tree") == "true":
        top = run_git(existing, "rev-parse", "--show-toplevel") or str(existing)
        warnings.append(f"export folder is inside the git work tree {top}; raw copies are not redacted")
    home_path = _real(home if home is not None else Path.home())
    if home_path in target.parents:
        parts = target.relative_to(home_path).parts
        for marker in _SYNC_FOLDER_PARTS:
            if any(parts[index : index + len(marker)] == marker for index in range(len(parts))):
                warnings.append(f"export folder is inside the sync folder {'/'.join(marker)}; files leave this machine")
                break
    return tuple(warnings)


def export_claude_code_session(session: ClaudeCodeSession, out: Path, *, raw: bool) -> SessionExportResult:
    """Normalize one session and write it under ``out``. ``newest`` keeps the last exchange open."""
    sources = _read_sources(session)
    records = [record for relative, data in sources for record in _records(relative, data)]
    normalized = ClaudeCodeAdapter(session_ended=not session.newest).normalize_session(records)
    normalized_path = out / "normalized" / CLAUDE_CODE_AGENT / f"{session.session_id}.jsonl"
    normalized_written = _write_if_changed(normalized_path, encode_session(normalized.lines).encode("utf-8"))
    written = unchanged = 0
    if raw:
        raw_root = out / "raw" / CLAUDE_CODE_AGENT / session.session_id
        for relative, data in sources:
            target = raw_root / _raw_relative(relative, session.session_id)
            if _write_if_changed(target, data):
                written += 1
            else:
                unchanged += 1
    return SessionExportResult(
        session_id=session.session_id,
        normalized_path=normalized_path,
        normalized_written=normalized_written,
        raw_files_written=written,
        raw_files_unchanged=unchanged,
        invalid_lines=normalized.invalid_lines,
        unknown_record_types=dict(normalized.unknown_record_types),
    )


def _read_sources(session: ClaudeCodeSession) -> list[tuple[str, bytes]]:
    """``(path relative to the project folder, bytes)`` for the main transcript and subagent files."""
    sources = [(f"{session.session_id}.jsonl", session.main_file.read_bytes())]
    if session.subagent_dir.is_dir() and not session.subagent_dir.is_symlink():
        for path in sorted(session.subagent_dir.iterdir()):
            if path.is_file() and not path.is_symlink() and path.name.endswith((".jsonl", ".meta.json")):
                sources.append((f"{session.session_id}/subagents/{path.name}", path.read_bytes()))
    return sources


def _records(relative: str, data: bytes) -> list[SourceRecord]:
    text = data.decode("utf-8", errors="replace")
    if not relative.endswith(".jsonl"):
        return [SourceRecord(source_path=relative, line_no=1, text=text)]
    # Split on "\n" only: JSON text may hold U+2028 and other characters str.splitlines() breaks on.
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [SourceRecord(source_path=relative, line_no=number, text=line) for number, line in enumerate(lines, 1)]


def _raw_relative(relative: str, session_id: str) -> str:
    prefix = f"{session_id}/"
    return relative[len(prefix) :] if relative.startswith(prefix) else relative


def _write_if_changed(target: Path, data: bytes) -> bool:
    try:
        if target.is_file() and not target.is_symlink() and target.read_bytes() == data:
            return False
    except OSError:
        pass
    _make_dirs(target.parent)
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
    try:
        os.fchmod(descriptor, _FILE_MODE)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise
    return True


def _make_dirs(folder: Path) -> None:
    """Create ``folder`` and missing parents with 0700. Only folders this call creates are changed."""
    missing: list[Path] = []
    current = folder
    while not current.exists():
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for path in reversed(missing):
        path.mkdir(mode=_DIR_MODE, exist_ok=True)
        os.chmod(path, _DIR_MODE)  # mkdir mode is narrowed by umask, never widened


def _real(path: Path) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    existing = _nearest_existing(absolute)
    return existing.resolve() / absolute.relative_to(existing)


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists() and current.parent != current:
        current = current.parent
    return current
