"""Install static Vault Graph coding guidance into an explicitly selected file."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.errors import HarnessGuidanceError
from vault_graph.mcp.mcp_prompts import HARNESS_GUIDANCE_END_MARKER, HARNESS_GUIDANCE_START_MARKER

HarnessInstructionFile = Literal["AGENTS.md", "CLAUDE.md"]
SUPPORTED_INSTRUCTION_FILES: tuple[HarnessInstructionFile, ...] = ("AGENTS.md", "CLAUDE.md")

__all__ = [
    "HARNESS_GUIDANCE_END_MARKER",
    "HARNESS_GUIDANCE_START_MARKER",
    "HarnessGuidanceError",
    "HarnessGuidanceReport",
    "HarnessGuidanceRequest",
    "HarnessGuidanceService",
    "SUPPORTED_INSTRUCTION_FILES",
]

_GUIDANCE_BLOCK = "\n".join(
    (
        HARNESS_GUIDANCE_START_MARKER,
        "## Vault Graph project evidence",
        "Call `explore_project` first for bounded, read-only code and Vault evidence.",
        "Treat its output as working evidence, inspect warnings, and re-read live source lines before changing code.",
        "Code projections are derived views; the registered repository remains authoritative for current code.",
        "Publish durable knowledge only through Vault's source capture, validation, release gate, and Git workflow.",
        "If MCP is unavailable, use the safe `vg code search`, `vg code symbol`, `vg code outline`,",
        "`vg code callers`, `vg code callees`, and `vg code impact` commands instead.",
        HARNESS_GUIDANCE_END_MARKER,
        "",
    )
)


@dataclass(frozen=True)
class HarnessGuidanceRequest:
    target: Path
    file_name: HarnessInstructionFile
    backup_path: Path | None = None
    preview: bool = False


@dataclass(frozen=True)
class HarnessGuidanceReport:
    action: Literal["install", "remove", "preview"]
    target_path: Path
    backup_path: Path | None
    changed: bool
    preview: bool
    content: str


class HarnessGuidanceService:
    """Own the small, explicit write boundary for coding-harness instructions."""

    def __init__(self, *, vault_roots: tuple[Path, ...] = ()) -> None:
        self._vault_roots = tuple(root.expanduser().resolve() for root in vault_roots)

    def preview(self, request: HarnessGuidanceRequest) -> HarnessGuidanceReport:
        target_path = self._resolve_instruction_path(request)
        current = _read_instruction(target_path)
        marker_state = _marker_state(current)
        if marker_state == "tampered":
            raise HarnessGuidanceError("harness_guidance_marker_tampered")
        return HarnessGuidanceReport(
            action="preview",
            target_path=target_path,
            backup_path=None,
            changed=marker_state == "missing",
            preview=True,
            content=_with_guidance(current) if marker_state == "missing" else current,
        )

    def install(self, request: HarnessGuidanceRequest) -> HarnessGuidanceReport:
        target_path = self._resolve_instruction_path(request)
        current = _read_instruction(target_path)
        marker_state = _marker_state(current)
        if marker_state == "tampered":
            raise HarnessGuidanceError("harness_guidance_marker_tampered")
        if marker_state == "installed":
            return HarnessGuidanceReport(
                action="install",
                target_path=target_path,
                backup_path=None,
                changed=False,
                preview=request.preview,
                content=current,
            )
        next_content = _with_guidance(current)
        if request.preview:
            return HarnessGuidanceReport(
                action="install",
                target_path=target_path,
                backup_path=None,
                changed=True,
                preview=True,
                content=next_content,
            )
        backup_path = self._resolve_backup_path(request, target_path, action="install")
        _write_atomically(backup_path, current)
        _write_atomically(target_path, next_content)
        return HarnessGuidanceReport(
            action="install",
            target_path=target_path,
            backup_path=backup_path,
            changed=True,
            preview=False,
            content=next_content,
        )

    def remove(self, request: HarnessGuidanceRequest) -> HarnessGuidanceReport:
        if request.backup_path is not None:
            raise HarnessGuidanceError("harness_guidance_remove_backup_not_supported")
        target_path = self._resolve_instruction_path(request)
        current = _read_instruction(target_path)
        marker_state = _marker_state(current)
        if marker_state == "missing":
            raise HarnessGuidanceError("harness_guidance_marker_missing")
        if marker_state == "tampered":
            raise HarnessGuidanceError("harness_guidance_marker_tampered")
        next_content = _without_guidance(current)
        if request.preview:
            return HarnessGuidanceReport(
                action="remove",
                target_path=target_path,
                backup_path=None,
                changed=True,
                preview=True,
                content=next_content,
            )
        backup_path = self._resolve_backup_path(request, target_path, action="remove")
        _write_atomically(backup_path, current)
        _write_atomically(target_path, next_content)
        return HarnessGuidanceReport(
            action="remove",
            target_path=target_path,
            backup_path=backup_path,
            changed=True,
            preview=False,
            content=next_content,
        )

    def _resolve_instruction_path(self, request: HarnessGuidanceRequest) -> Path:
        if not self._vault_roots:
            raise HarnessGuidanceError("harness_guidance_vault_scope_required")
        if request.file_name not in SUPPORTED_INSTRUCTION_FILES:
            raise HarnessGuidanceError("harness_guidance_unsupported_file_name")
        target = _canonical_existing_directory(request.target)
        instruction_path = target / request.file_name
        if instruction_path.exists() and instruction_path.is_symlink():
            raise HarnessGuidanceError("harness_guidance_symlink_not_allowed")
        self._assert_outside_vaults(instruction_path)
        return instruction_path

    def _resolve_backup_path(
        self,
        request: HarnessGuidanceRequest,
        target_path: Path,
        *,
        action: Literal["install", "remove"],
    ) -> Path:
        raw_backup = request.backup_path or target_path.with_name(f"{target_path.name}.{action}.bak")
        backup = _canonical_new_file_path(raw_backup)
        if backup.exists():
            raise HarnessGuidanceError("harness_guidance_backup_exists")
        self._assert_outside_vaults(backup)
        return backup

    def _assert_outside_vaults(self, path: Path) -> None:
        for vault_root in self._vault_roots:
            if path == vault_root or vault_root in path.parents:
                raise HarnessGuidanceError("harness_guidance_target_inside_vault")


def _canonical_existing_directory(path: Path) -> Path:
    expanded = path.expanduser()
    _reject_symlink_components(expanded)
    try:
        resolved = expanded.resolve(strict=True)
    except FileNotFoundError as exc:
        raise HarnessGuidanceError("harness_guidance_target_missing") from exc
    if not resolved.is_dir():
        raise HarnessGuidanceError("harness_guidance_target_not_directory")
    return resolved


def _canonical_new_file_path(path: Path) -> Path:
    expanded = path.expanduser()
    _reject_symlink_components(expanded)
    if not expanded.parent.exists():
        raise HarnessGuidanceError("harness_guidance_backup_parent_missing")
    parent = expanded.parent.resolve(strict=True)
    if not parent.is_dir():
        raise HarnessGuidanceError("harness_guidance_backup_parent_missing")
    return parent / expanded.name


def _reject_symlink_components(path: Path) -> None:
    candidate = path.absolute()
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise HarnessGuidanceError("harness_guidance_symlink_not_allowed")


def _read_instruction(path: Path) -> str:
    if not path.exists():
        return ""
    if not path.is_file():
        raise HarnessGuidanceError("harness_guidance_target_not_file")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HarnessGuidanceError("harness_guidance_target_not_utf8") from exc


def _marker_state(content: str) -> Literal["missing", "installed", "tampered"]:
    start_count = content.count(HARNESS_GUIDANCE_START_MARKER)
    end_count = content.count(HARNESS_GUIDANCE_END_MARKER)
    if start_count == 0 and end_count == 0:
        return "missing"
    if start_count != 1 or end_count != 1:
        return "tampered"
    start = content.find(HARNESS_GUIDANCE_START_MARKER)
    end = content.find(HARNESS_GUIDANCE_END_MARKER)
    if start > end:
        return "tampered"
    end += len(HARNESS_GUIDANCE_END_MARKER)
    return "installed" if content[start:end] == _GUIDANCE_BLOCK.rstrip("\n") else "tampered"


def _with_guidance(content: str) -> str:
    return _GUIDANCE_BLOCK if not content else f"{content.rstrip()}\n\n{_GUIDANCE_BLOCK}"


def _without_guidance(content: str) -> str:
    start = content.find(HARNESS_GUIDANCE_START_MARKER)
    end = content.find(HARNESS_GUIDANCE_END_MARKER) + len(HARNESS_GUIDANCE_END_MARKER)
    before = content[:start]
    after = content[end:]
    if before.endswith("\n\n"):
        before = before[:-1]
    if after.startswith("\n"):
        after = after[1:]
    return before + after


def _write_atomically(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except OSError as exc:
        raise HarnessGuidanceError("harness_guidance_write_failed") from exc
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
