"""Run the read-only Vault ``memory-scan --json`` and reconcile it with the vg L1 check (spec 2026-11-05 §4.4.5).

An index run calls ``scan_linked_vaults`` for the Vaults it indexed. For each Vault that
``vault-map.json`` links to a project, vg finds the L1 notes (``auto_memory_reader``) and marks a
note imported when its sha256 is a ``raw_sha256`` of a source page in a Vault linked to the same
project. It then runs the Vault ``memory-scan --json`` the way ``vault_publish_cli`` runs Vault
commands (the vg Python with ``-I -B``, the Vault root as working folder, a time limit) and keeps
the report at Graph Home ``memory/memory-scan-<vault>.json``.

The Vault owns the imported rule. When both saw a note, the Vault's ``imported`` value is used.
Notes only one side saw (for example when ``autoMemoryDirectory`` moves the folder, which the Vault
scan does not read) are kept. Any difference gives one warning line. When the scan fails or its
output is not the expected report, the vg check is used, one warning line says why, and an older
saved report is removed so the file always belongs to the last run. Nothing is written to a Vault
or an L1 folder.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vault_graph.interface.composition.adapters.auto_memory_reader import (
    imported_raw_hashes,
    locate_memory_folder,
    read_memory_notes,
)
from vault_graph.operation.integration.vault_map import VaultMapError, load_vault_map

CLI_RELATIVE_PATH = Path("tools") / "wiki" / "cli.py"
MEMORY_SCAN_FOLDER = "memory"
DEFAULT_TIMEOUT_S = 60.0

WriteTargetCheck = Callable[[Path], None]


@dataclass(frozen=True)
class MemoryScanRun:
    """The parsed ``memory-scan --json`` report, or a one-line reason there is none."""

    report: dict[str, Any] | None
    problem: str | None = None


@dataclass(frozen=True)
class L1NoteState:
    project_id: str
    name: str
    path: str
    sha256: str
    imported: bool


@dataclass(frozen=True)
class MemoryScanOutcome:
    vault_id: str
    notes: tuple[L1NoteState, ...]
    scan_file: Path | None
    warning: str | None = None

    @property
    def unimported(self) -> tuple[L1NoteState, ...]:
        return tuple(note for note in self.notes if not note.imported)


@dataclass(frozen=True)
class _LinkedProject:
    project_id: str
    root: str
    vault_paths: tuple[Path, ...]


def memory_scan_path(graph_home: Path, vault_id: str) -> Path:
    return graph_home / MEMORY_SCAN_FOLDER / f"memory-scan-{vault_id}.json"


def run_memory_scan(
    vault_root: Path,
    *,
    timeout_s: float,
    python_executable: str = sys.executable,
    environ: Mapping[str, str] | None = None,
) -> MemoryScanRun:
    cli = vault_root / CLI_RELATIVE_PATH
    if not cli.is_file():
        return MemoryScanRun(None, f"the Vault has no {CLI_RELATIVE_PATH.as_posix()}")
    try:
        completed = subprocess.run(
            [python_executable, "-I", "-B", str(cli), "memory-scan", "--json"],
            cwd=vault_root,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=dict(environ) if environ is not None else None,
        )
    except subprocess.TimeoutExpired:
        return MemoryScanRun(None, f"memory-scan did not finish in {timeout_s:g} seconds and was stopped")
    except OSError as exc:
        return MemoryScanRun(None, f"memory-scan could not start: {exc}")
    if completed.returncode != 0:
        detail = _first_line(completed.stderr) or _first_line(completed.stdout)
        return MemoryScanRun(None, f"memory-scan ended with exit code {completed.returncode}: {detail}".rstrip(": "))
    try:
        data = json.loads(completed.stdout)
    except ValueError:
        data = None
    if not _is_report(data):
        return MemoryScanRun(None, "memory-scan printed no memory-scan JSON report")
    return MemoryScanRun(data)


def scan_linked_vaults(
    vaults: Iterable[tuple[str, Path]],
    *,
    vault_map_path: Path,
    graph_home: Path,
    environ: Mapping[str, str] | None = None,
    managed_settings_path: Path | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    python_executable: str = sys.executable,
    check_write_target: WriteTargetCheck | None = None,
) -> tuple[MemoryScanOutcome, ...]:
    """Scan each ``(vault_id, root)`` that the map links to a project. A missing or bad map scans nothing."""

    outcomes = []
    for vault_id, vault_root in vaults:
        outcome = scan_vault_memory(
            vault_id=vault_id,
            vault_root=vault_root,
            vault_map_path=vault_map_path,
            graph_home=graph_home,
            environ=environ,
            managed_settings_path=managed_settings_path,
            timeout_s=timeout_s,
            python_executable=python_executable,
            check_write_target=check_write_target,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return tuple(outcomes)


def scan_vault_memory(
    *,
    vault_id: str,
    vault_root: Path,
    vault_map_path: Path,
    graph_home: Path,
    environ: Mapping[str, str] | None = None,
    managed_settings_path: Path | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    python_executable: str = sys.executable,
    check_write_target: WriteTargetCheck | None = None,
) -> MemoryScanOutcome | None:
    """Return the reconciled L1 notes of one Vault, or None when no project links it."""

    projects = _linked_projects(vault_map_path, vault_root)
    if not projects:
        return None
    env = os.environ if environ is None else environ
    vg_notes = _vg_notes(projects, environ=env, managed_settings_path=managed_settings_path)
    run = run_memory_scan(vault_root, timeout_s=timeout_s, python_executable=python_executable, environ=env)
    scan_file = memory_scan_path(graph_home, vault_id)
    if check_write_target is not None:
        check_write_target(scan_file)
    if run.report is None:
        scan_file.unlink(missing_ok=True)
        failed = f"memory-scan for Vault {vault_id} gave no result ({run.problem}); using the vg sha256 check only."
        return MemoryScanOutcome(vault_id, vg_notes, None, failed)
    _save(scan_file, run.report)
    notes, differences = _reconcile(vg_notes, _report_notes(run.report))
    warning = (
        f"memory-scan for Vault {vault_id} disagrees with the vg check on {differences} L1 note(s); "
        "using the Vault result."
        if differences
        else None
    )
    return MemoryScanOutcome(vault_id, notes, scan_file, warning)


def _linked_projects(vault_map_path: Path, vault_root: Path) -> tuple[_LinkedProject, ...]:
    try:
        vault_map = load_vault_map(vault_map_path)
        raw_projects = json.loads(vault_map_path.read_text(encoding="utf-8"))["projects"]
    except (VaultMapError, OSError, ValueError, KeyError):
        return ()
    paths = {vault.name: vault.path for vault in vault_map.vaults}
    target = _resolve(vault_root)
    names = {name for name, path in paths.items() if path == target}
    if not names:
        return ()
    return tuple(
        _LinkedProject(
            project_id=project_id,
            root=entry["root"],
            vault_paths=tuple(paths[name] for name in dict.fromkeys(entry["vaults"]) if name in paths),
        )
        for project_id, entry in sorted(raw_projects.items())
        if names.intersection(entry["vaults"])
    )


def _vg_notes(
    projects: Iterable[_LinkedProject], *, environ: Mapping[str, str], managed_settings_path: Path | None
) -> tuple[L1NoteState, ...]:
    hashes: dict[Path, set[str]] = {}
    states: list[L1NoteState] = []
    for project in projects:
        imported: set[str] = set()
        for path in project.vault_paths:
            if path not in hashes:
                hashes[path] = set(imported_raw_hashes(path))
            imported |= hashes[path]
        folder = locate_memory_folder(project.root, environ=environ, managed_settings_path=managed_settings_path)
        states.extend(
            L1NoteState(project.project_id, note.name, str(note.path), note.sha256, note.sha256 in imported)
            for note in read_memory_notes(folder.path)
        )
    return tuple(states)


def _report_notes(report: Mapping[str, Any]) -> tuple[L1NoteState, ...]:
    return tuple(
        L1NoteState(project["id"], note["name"], note["path"], note["sha256"], note["imported"])
        for project in report["projects"]
        for note in project["notes"]
    )


def _reconcile(
    vg_notes: Iterable[L1NoteState], vault_notes: Iterable[L1NoteState]
) -> tuple[tuple[L1NoteState, ...], int]:
    ours = {(note.project_id, note.sha256): note for note in vg_notes}
    theirs = {(note.project_id, note.sha256): note for note in vault_notes}
    merged = []
    differences = 0
    for key in sorted(ours.keys() | theirs.keys()):
        mine, vault = ours.get(key), theirs.get(key)
        if mine is None or vault is None:
            differences += 1
            merged.append(mine or vault)
            continue
        if mine.imported != vault.imported:
            differences += 1
        merged.append(L1NoteState(mine.project_id, mine.name, mine.path, mine.sha256, vault.imported))
    notes = tuple(note for note in merged if note is not None)
    return tuple(sorted(notes, key=lambda note: (note.project_id, note.name, note.sha256))), differences


def _is_report(data: object) -> bool:
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        return False
    for project in data["projects"]:
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            return False
        notes = project.get("notes")
        if not isinstance(notes, list):
            return False
        for note in notes:
            if not isinstance(note, dict) or not isinstance(note.get("imported"), bool):
                return False
            if not all(isinstance(note.get(field), str) for field in ("name", "path", "sha256")):
                return False
    return True


def _save(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except (OSError, RuntimeError):
        return path.expanduser().absolute()


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "L1NoteState",
    "MemoryScanOutcome",
    "MemoryScanRun",
    "memory_scan_path",
    "run_memory_scan",
    "scan_linked_vaults",
    "scan_vault_memory",
]
