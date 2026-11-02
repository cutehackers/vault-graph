"""Run the Vault hook launcher ``vault_hooks.py capture --direct`` (spec 2026-11-02 V5, 계약6).

vault-graph decides only when capture runs. The launcher and the Vault's own ``sessions capture``
decide which Vault and what to save. This adapter passes the hook JSON unchanged, reads the result
JSON line, and never writes a file.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

LAUNCHER_NAME = "vault_hooks.py"


@dataclass(frozen=True)
class CaptureOutcome:
    """What one launcher run did.

    ``finished`` is True when the launcher ended with exit code 0. ``status`` is the
    ``sessions capture --json`` status, or ``"unknown"`` when stdout had no readable result.
    ``problem`` says why the launcher did not finish (missing, failed to start, timed out, non-zero exit).
    """

    finished: bool
    status: str | None = None
    vault: str | None = None
    path: str | None = None
    problem: str | None = None
    stderr: str = ""


def run_capture(hook_json: bytes, *, launcher: Path, timeout_s: float) -> CaptureOutcome:
    """Run ``<python> -I -B <launcher> capture --direct`` with ``hook_json`` on stdin.

    The launcher runs in its own process group so a timeout also stops ``sessions capture``.
    """

    if not launcher.is_file():
        return CaptureOutcome(finished=False, problem=f"no {LAUNCHER_NAME} at {launcher}.")
    command = [sys.executable, "-I", "-B", str(launcher), "capture", "--direct"]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return CaptureOutcome(finished=False, problem=f"cannot start {launcher}: {exc.strerror or exc}.")
    try:
        stdout, stderr = process.communicate(hook_json, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _stop(process)
        _, stderr = process.communicate()
        return CaptureOutcome(
            finished=False,
            problem=f"{LAUNCHER_NAME} did not finish in {timeout_s:g} seconds and was stopped.",
            stderr=_text(stderr),
        )
    if process.returncode != 0:
        return CaptureOutcome(
            finished=False,
            problem=f"{LAUNCHER_NAME} ended with exit code {process.returncode}.",
            stderr=_text(stderr),
        )
    status, vault, path = _result(_text(stdout))
    return CaptureOutcome(finished=True, status=status, vault=vault, path=path, stderr=_text(stderr))


def _stop(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except OSError:
        process.kill()


def _result(stdout: str) -> tuple[str, str | None, str | None]:
    """Read the last JSON object line of stdout as the ``sessions capture --json`` result."""

    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("status"), str):
            return payload["status"], _optional(payload.get("vault")), _optional(payload.get("path"))
    return "unknown", None, None


def _optional(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


__all__ = ["LAUNCHER_NAME", "CaptureOutcome", "run_capture"]
