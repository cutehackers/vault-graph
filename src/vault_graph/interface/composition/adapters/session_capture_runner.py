"""Normalize a Claude Code session and hand it to the Vault hook launcher (spec 2026-11-05 §4.2.5, §6).

``vg hook capture`` (``capture_hook``):

1. Reads ``transcript_path`` and ``hook_event_name`` from the hook JSON. SessionEnd normalizes with
   ``session_ended=True``, any other event (PreCompact) with ``False``, so the last exchange stays open.
2. Writes the ``vg-session-jsonl/1`` file. With Graph Home ``configs/session-export.json`` naming
   ``claude-code``, the same run exports the session to that folder (raw copy as the settings say)
   and passes the exported file. Otherwise the file goes to a new OS temporary folder that is
   removed after the launcher ends. A missing export folder, one inside a Vault, or unreadable
   settings skip only the export with one warning.
3. Runs ``vault_hooks.py capture --direct --normalized <file>`` with the hook JSON unchanged on stdin.
   Exit code 2 means the launcher or Vault tool does not know ``--normalized``: the same hook JSON
   goes to ``capture --direct`` again so the Vault writes a v1 file. When normalization fails, only
   ``capture --direct`` runs. Both runs share one time limit.

``vg session export --recapture`` (``recapture_session``) runs
``capture --direct --normalized <file> --rerender`` once per exported session, with no v1 fallback.
``--rerender`` is added nowhere else (spec §4.2.12-5).

vg never chooses the Vault: the launcher and the Vault tool do. This module writes only the
normalized file and the export folder, both outside every Vault.
"""

from __future__ import annotations

import json
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from vault_graph.errors import CatalogError, VaultGraphError
from vault_graph.interface.composition.adapters.session_export_files import (
    ClaudeCodeSession,
    export_claude_code_session,
    valid_session_id,
    vault_containing,
)
from vault_graph.interface.composition.adapters.vault_capture_cli import LAUNCHER_NAME, CaptureOutcome, run_capture
from vault_graph.operation.integration.vault_map import open_vault_map
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.session_export_settings import (
    load_session_export_settings,
    session_export_settings_path,
)
from vault_graph.operation.sessions.claude_code_adapter import CLAUDE_CODE_AGENT

UNKNOWN_OPTION_EXIT_CODE = 2
"""Exit code of a launcher or Vault tool that does not know ``--normalized`` (argparse usage error)."""

SESSION_END_EVENT = "SessionEnd"
PRE_COMPACT_EVENT = "PreCompact"
# A person runs recapture once per migration. Rerendering a whole session may take longer than a hook.
RECAPTURE_TIMEOUT_S = 120.0


@dataclass(frozen=True)
class HookCapture:
    """One ``vg hook capture`` run. ``normalized`` is True when the outcome came from the ``--normalized`` run."""

    outcome: CaptureOutcome
    normalized: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _ExportFolder:
    path: Path
    raw: bool


def capture_hook(
    hook_json: bytes, *, launcher: Path, vault_map: Path, graph_home: Path, timeout_s: float
) -> HookCapture:
    """Normalize the hook's transcript, run the launcher with ``--normalized``, and fall back to v1."""

    deadline = monotonic() + timeout_s
    warnings: list[str] = []
    session = _hook_session(hook_json)
    with ExitStack() as cleanup:
        normalized: Path | None = None
        if session is not None:
            export = _export_folder(graph_home, vault_map, warnings)
            normalized = _normalize(session, export, cleanup, warnings)
        if normalized is not None:
            outcome = _run(hook_json, launcher, deadline, timeout_s, ("--normalized", str(normalized)))
            if not launcher_rejected_normalized(outcome):
                return HookCapture(outcome=outcome, normalized=True, warnings=tuple(warnings))
        outcome = _run(hook_json, launcher, deadline, timeout_s, ())
    return HookCapture(outcome=outcome, normalized=False, warnings=tuple(warnings))


def launcher_rejected_normalized(outcome: CaptureOutcome) -> bool:
    """True when the launcher or Vault tool does not know ``--normalized``, so nothing was captured.

    A current launcher exits 2. A launcher installed before 요청S10 prints its usage line and exits 0
    without a capture result, so that answer counts as a rejection too.
    """
    if outcome.exit_code == UNKNOWN_OPTION_EXIT_CODE:
        return True
    return outcome.exit_code == 0 and outcome.status in (None, "unknown") and "usage: vault_hooks.py" in outcome.stderr


def recapture_session(
    session: ClaudeCodeSession, normalized: Path, *, launcher: Path, timeout_s: float = RECAPTURE_TIMEOUT_S
) -> CaptureOutcome:
    """Run ``capture --direct --normalized <normalized> --rerender`` with a hook JSON built for ``session``.

    The hook JSON carries what the launcher reads to choose the Vault: ``session_id``,
    ``transcript_path``, ``cwd`` from the normalized session line, and ``hook_event_name``
    (SessionEnd for an ended session, PreCompact for the newest one, which may still run).
    """

    hook: dict[str, str] = {
        "session_id": session.session_id,
        "transcript_path": str(session.main_file),
        "hook_event_name": PRE_COMPACT_EVENT if session.newest else SESSION_END_EVENT,
    }
    cwd = _session_cwd(normalized)
    if cwd is not None:
        hook["cwd"] = cwd
    return run_capture(
        json.dumps(hook).encode("utf-8"),
        launcher=launcher,
        timeout_s=timeout_s,
        extra_args=("--normalized", str(normalized), "--rerender"),
    )


def _hook_session(hook_json: bytes) -> ClaudeCodeSession | None:
    """The Claude Code session named by ``transcript_path``, or None when there is no readable transcript."""

    try:
        payload = json.loads(hook_json)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    transcript = payload.get("transcript_path")
    if not isinstance(transcript, str) or not transcript:
        return None
    path = Path(transcript).expanduser()
    if path.suffix != ".jsonl" or not valid_session_id(path.stem):
        return None
    try:
        if not path.is_file() or path.is_symlink():
            return None
        modified_at = path.stat().st_mtime
    except OSError:
        return None
    return ClaudeCodeSession(
        session_id=path.stem,
        project_dir=path.parent,
        modified_at=modified_at,
        newest=payload.get("hook_event_name") != SESSION_END_EVENT,
    )


def _export_folder(graph_home: Path, vault_map: Path, warnings: list[str]) -> _ExportFolder | None:
    settings_path = session_export_settings_path(graph_home)
    try:
        settings = load_session_export_settings(settings_path)
    except CatalogError as exc:
        warnings.append(f"session export skipped: {exc}")
        return None
    if settings is None or CLAUDE_CODE_AGENT not in settings.agents:
        return None
    if not settings.path.is_dir():
        warnings.append(f"session export skipped: export folder {settings.path} does not exist")
        return None
    try:
        vault = vault_containing(settings.path, _vault_roots(graph_home, vault_map))
    except VaultGraphError as exc:
        warnings.append(f"session export skipped: cannot check whether {settings.path} is inside a Vault: {exc}")
        return None
    if vault is not None:
        warnings.append(f"session export skipped: export folder {settings.path} is inside Vault {vault}")
        return None
    return _ExportFolder(path=settings.path, raw=settings.raw)


def _vault_roots(graph_home: Path, vault_map: Path) -> list[Path]:
    roots: list[Path] = []
    if (graph_home / "configs" / "vaults.yaml").exists():
        roots.extend(entry.root_path for entry in CatalogService(graph_home_path=graph_home).load_catalog().entries())
    opening = open_vault_map(vault_map)
    if opening.state == "invalid":
        raise VaultGraphError(opening.warning or f"{vault_map} is invalid")
    if opening.vault_map is not None:
        roots.extend(vault.path for vault in opening.vault_map.vaults)
    return roots


def _normalize(
    session: ClaudeCodeSession, export: _ExportFolder | None, cleanup: ExitStack, warnings: list[str]
) -> Path | None:
    """Write the normalized file and return its path, or None so the transcript goes to v1 capture."""

    try:
        if export is not None:
            try:
                return export_claude_code_session(session, export.path, raw=export.raw).normalized_path
            except OSError as exc:
                warnings.append(f"session export skipped: cannot write to {export.path}: {exc}")
        folder = Path(cleanup.enter_context(tempfile.TemporaryDirectory(prefix="vg-capture-")))
        return export_claude_code_session(session, folder, raw=False).normalized_path
    except Exception as exc:  # any normalization failure falls back to v1 capture (spec §6)
        warnings.append(f"cannot normalize {session.main_file}, capturing the transcript instead: {exc}")
        return None


def _run(
    hook_json: bytes, launcher: Path, deadline: float, budget_s: float, extra_args: tuple[str, ...]
) -> CaptureOutcome:
    remaining = deadline - monotonic()
    if remaining <= 0:
        return CaptureOutcome(finished=False, problem=f"{LAUNCHER_NAME} had no time left of {budget_s:g} seconds.")
    return run_capture(hook_json, launcher=launcher, timeout_s=remaining, extra_args=extra_args, budget_s=budget_s)


def _session_cwd(normalized: Path) -> str | None:
    """``cwd`` of the first (session) line of a normalized file, or None."""

    try:
        with normalized.open(encoding="utf-8") as stream:
            first = stream.readline()
        payload = json.loads(first)
    except (OSError, ValueError):
        return None
    cwd = payload.get("cwd") if isinstance(payload, dict) else None
    return cwd if isinstance(cwd, str) and cwd else None


__all__ = [
    "PRE_COMPACT_EVENT",
    "RECAPTURE_TIMEOUT_S",
    "SESSION_END_EVENT",
    "UNKNOWN_OPTION_EXIT_CODE",
    "launcher_rejected_normalized",
    "HookCapture",
    "capture_hook",
    "recapture_session",
]
