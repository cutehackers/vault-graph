"""Re-capture sessions whose `vault-session/v1` parts no v2 part covers (spec 2026-11-25-v1-session-recapture).

``vg session migrate`` reads the session part files of each mapped Vault (frontmatter, and the
``vg:exchange`` meta lines of v2 parts), picks the sessions with an uncovered v1 part (D2), finds each
session's Claude Code source, normalizes it as an ended session into an OS temporary folder (D5) and runs
the Vault hook launcher with ``--normalized <file> --rerender`` through ``recapture_session`` (D3). The
launcher and the Vault tool choose the Vault and write the new part. This module writes nothing inside a
Vault (I1): it reads part files and writes only the temporary normalized file.

After a write it checks the Vault name (I4, stops the run on a mismatch), the exchange count (D7) and that
the session's v1 parts are now covered (F7). A session whose normalized first and last exchange ids already
match a v2 part is not written again (D8). It never touches the fact queue (D10).
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import time

from vault_graph.interface.composition.adapters.session_capture_runner import (
    launcher_rejected_normalized,
    recapture_session,
)
from vault_graph.interface.composition.adapters.session_export_files import (
    ClaudeCodeSession,
    find_claude_code_sessions,
    normalize_claude_code_session,
)
from vault_graph.interface.composition.adapters.vault_capture_cli import CaptureOutcome
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter
from vault_graph.operation.sessions.claude_code_adapter import CLAUDE_CODE_AGENT
from vault_graph.operation.sessions.models import SessionLine
from vault_graph.operation.sessions.normalized_jsonl import encode_session
from vault_graph.operation.sessions.v1_coverage import (
    V2_SCHEMA,
    PartHead,
    exchange_summary,
    exchange_time_range,
    uncovered_v1_parts,
)

SESSION_PARTS_DIR = Path("raw") / "sessions" / CLAUDE_CODE_AGENT
RECENT_SECONDS = 3600.0
"""A source changed within this many seconds may belong to a running session; it is skipped (D5)."""

WRITTEN = "written"
SOURCE_MISSING = "source_missing"
RECENT = "recent"
TARGET = "target"
"""Dry-run result of a session that a real run would re-capture."""

Recapture = Callable[..., CaptureOutcome]


@dataclass(frozen=True)
class MigrationVault:
    name: str
    root: Path


@dataclass(frozen=True)
class VaultParts:
    """Part heads of one Vault, and part files whose frontmatter could not be read (F9)."""

    vault: MigrationVault
    heads: tuple[PartHead, ...]
    unreadable_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionResult:
    vault: str
    session_id: str
    status: str
    v1_parts: int
    exchanges: int | None = None
    detail: str | None = None
    cwd_fallback: str | None = None
    path: str | None = None

    @property
    def failed(self) -> bool:
        return self.status.startswith("failed:") or self.status == "already_recaptured_uncovered"

    def line(self) -> str:
        parts = [
            self.vault,
            self.session_id,
            self.status,
            f"v1_parts={self.v1_parts}",
            f"exchanges={self.exchanges if self.exchanges is not None else '-'}",
        ]
        if self.cwd_fallback is not None:
            parts.append(f"cwd_fallback={self.cwd_fallback}")
        if self.path is not None:
            parts.append(f"path={self.path}")
        if self.detail:
            parts.append(self.detail)
        return " ".join(parts)


@dataclass(frozen=True)
class VaultSummary:
    vault: str
    v1_parts: int
    covered: int
    uncovered: int
    source_missing: int
    unreadable: int

    def line(self) -> str:
        return (
            f"vault={self.vault} v1_parts={self.v1_parts} covered={self.covered} uncovered={self.uncovered} "
            f"source_missing={self.source_missing} unreadable={self.unreadable}"
        )


@dataclass
class MigrationReport:
    sessions: list[SessionResult] = field(default_factory=list)
    summaries: list[VaultSummary] = field(default_factory=list)
    stopped: bool = False

    @property
    def failed(self) -> bool:
        return (
            self.stopped
            or any(result.failed for result in self.sessions)
            or any(summary.unreadable for summary in self.summaries)
        )


def read_vault_parts(vault: MigrationVault) -> VaultParts:
    """Read the session part heads under ``raw/sessions/claude-code/``. A missing folder gives no parts (F11)."""

    folder = vault.root / SESSION_PARTS_DIR
    if not folder.is_dir():
        return VaultParts(vault=vault, heads=())
    heads: list[PartHead] = []
    unreadable: list[str] = []
    for path in sorted(folder.glob("*.md")):
        if path.name.endswith(".facts.md") or not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(vault.root).as_posix()
        head = _part_head(vault.name, relative, path)
        if head is None:
            unreadable.append(relative)
        else:
            heads.append(head)
    return VaultParts(vault=vault, heads=tuple(heads), unreadable_files=tuple(unreadable))


def migrate(
    vaults: Sequence[MigrationVault],
    *,
    projects_root: Path,
    launcher: Path,
    dry_run: bool,
    on_result: Callable[[SessionResult], None] = lambda result: None,
    recapture: Recapture = recapture_session,
    now: Callable[[], float] = time,
) -> MigrationReport:
    """Re-capture every session with an uncovered v1 part, Vault by Vault, and summarize each Vault."""

    sources, duplicates = find_claude_code_sessions(projects_root)
    by_id = {session.session_id: session for session in sources}
    report = MigrationReport()
    for vault in vaults:
        parts = read_vault_parts(vault)
        if not report.stopped:
            for session_id, v1_heads in _targets(parts.heads):
                result = _migrate_session(
                    vault,
                    session_id,
                    v1_heads,
                    parts.heads,
                    source=by_id.get(session_id),
                    duplicate=session_id in duplicates,
                    launcher=launcher,
                    dry_run=dry_run,
                    recapture=recapture,
                    now=now(),
                )
                report.sessions.append(result)
                on_result(result)
                if result.status == "failed:vault_mismatch":
                    report.stopped = True
                    break
        final = read_vault_parts(vault) if not dry_run else parts
        missing_parts = sum(
            result.v1_parts
            for result in report.sessions
            if result.vault == vault.name and result.status == SOURCE_MISSING
        )
        coverage = uncovered_v1_parts(final.heads)
        report.summaries.append(
            VaultSummary(
                vault=vault.name,
                v1_parts=len(coverage.covered) + len(coverage.uncovered) + len(coverage.unreadable),
                covered=len(coverage.covered),
                uncovered=len(coverage.uncovered),
                source_missing=missing_parts,
                unreadable=len(coverage.unreadable) + len(final.unreadable_files),
            )
        )
    return report


def _targets(heads: Iterable[PartHead]) -> list[tuple[str, tuple[PartHead, ...]]]:
    """Sessions with an uncovered v1 part, sorted by session id, with those parts."""
    uncovered: dict[str, list[PartHead]] = {}
    for head in uncovered_v1_parts(heads).uncovered:
        assert head.session_id is not None  # uncovered parts always have one
        uncovered.setdefault(head.session_id, []).append(head)
    return [(session_id, tuple(items)) for session_id, items in sorted(uncovered.items())]


def _migrate_session(
    vault: MigrationVault,
    session_id: str,
    v1_heads: tuple[PartHead, ...],
    all_heads: tuple[PartHead, ...],
    *,
    source: ClaudeCodeSession | None,
    duplicate: bool,
    launcher: Path,
    dry_run: bool,
    recapture: Recapture,
    now: float,
) -> SessionResult:
    def result(status: str, **values: object) -> SessionResult:
        return SessionResult(vault=vault.name, session_id=session_id, status=status, v1_parts=len(v1_heads), **values)  # type: ignore[arg-type]

    if duplicate:
        return result("failed:duplicate_source", detail="the session id is in more than one project folder")
    if source is None:
        return result(SOURCE_MISSING)
    ended = ClaudeCodeSession(
        session_id=source.session_id, project_dir=source.project_dir, modified_at=source.modified_at, newest=False
    )
    if _changed_since(ended, now - RECENT_SECONDS):
        return result(RECENT, detail="the source changed within the last hour")
    if dry_run:
        return result(TARGET)

    try:
        normalized = normalize_claude_code_session(ended)
    except (OSError, ValueError) as exc:
        return result("failed:normalize", detail=str(exc))
    summary = exchange_summary(normalized.lines)
    v2_heads = [head for head in all_heads if head.schema == V2_SCHEMA and head.session_id == session_id]
    if summary.count and any(
        head.first_exchange_id == summary.first_exchange_id and head.last_exchange_id == summary.last_exchange_id
        for head in v2_heads
    ):
        return result("already_recaptured_uncovered", exchanges=summary.count)

    session_cwd = next((line.cwd for line in normalized.lines if isinstance(line, SessionLine)), None)
    fallback = _existing_parent(session_cwd)
    with tempfile.TemporaryDirectory(prefix="vg-migrate-") as folder:
        normalized_path = Path(folder) / f"{session_id}.jsonl"
        normalized_path.write_text(encode_session(normalized.lines), encoding="utf-8")
        outcome = recapture(ended, normalized_path, launcher=launcher, hook_cwd=fallback)

    values: dict[str, object] = {"exchanges": summary.count, "cwd_fallback": fallback, "path": outcome.path}
    if launcher_rejected_normalized(outcome):
        return result("failed:normalized_unsupported", detail=_detail(outcome), **values)
    if not outcome.finished:
        return result("failed:launcher", detail=outcome.problem or "the launcher did not finish", **values)
    if outcome.status != WRITTEN:
        return result(f"failed:{outcome.status}", detail=_detail(outcome), **values)
    if outcome.vault != vault.name:
        return result(
            "failed:vault_mismatch",
            detail=f"written to Vault {outcome.vault or '-'}; remove that part there by hand",
            **values,
        )
    if outcome.exchange_count != summary.count:
        got = outcome.exchange_count if outcome.exchange_count is not None else "-"
        return result("failed:exchange_count", detail=f"expected={summary.count} got={got}", **values)
    after = read_vault_parts(vault).heads
    left = [head for head in uncovered_v1_parts(after).uncovered if head.session_id == session_id]
    if left:
        return result("failed:uncovered", detail=" ".join(head.path for head in left), **values)
    return result(WRITTEN, **values)


def _part_head(vault: str, relative: str, path: Path) -> PartHead | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    split = split_frontmatter(text)
    if split is None:
        return None
    raw, body = split
    front = parse_vault_frontmatter(raw)
    schema = _text(front.get("schema"))
    if schema is None:
        return None
    started = ended = None
    if schema == V2_SCHEMA:
        span = exchange_time_range(body.splitlines())
        if span is not None:
            started, ended = span
    part = front.get("part")
    return PartHead(
        vault=vault,
        path=relative,
        schema=schema,
        agent=_text(front.get("agent")),
        session_id=_text(front.get("session_id")),
        part=part if isinstance(part, int) and not isinstance(part, bool) else None,
        first_turn_at=_text(front.get("first_turn_at")),
        last_turn_at=_text(front.get("last_turn_at")),
        first_exchange_id=_text(front.get("first_exchange_id")),
        last_exchange_id=_text(front.get("last_exchange_id")),
        exchange_started=started,
        exchange_ended=ended,
    )


def _changed_since(session: ClaudeCodeSession, cutoff: float) -> bool:
    files = [session.main_file]
    if session.subagent_dir.is_dir():
        files.extend(path for path in session.subagent_dir.iterdir() if path.is_file())
    for path in files:
        try:
            if path.stat().st_mtime >= cutoff:
                return True
        except OSError:
            continue
    return False


def _existing_parent(cwd: str | None) -> str | None:
    """The nearest existing folder above ``cwd`` when ``cwd`` does not exist, else None (D6)."""
    if not cwd:
        return None
    path = Path(cwd).expanduser()
    if path.is_dir():
        return None
    for parent in path.parents:
        if parent.is_dir():
            return str(parent)
    return None


def _detail(outcome: CaptureOutcome) -> str | None:
    text = outcome.stderr.strip()
    return text.splitlines()[-1] if text else None


def _text(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


__all__ = [
    "RECENT_SECONDS",
    "SESSION_PARTS_DIR",
    "MigrationReport",
    "MigrationVault",
    "SessionResult",
    "VaultParts",
    "VaultSummary",
    "migrate",
    "read_vault_parts",
]
