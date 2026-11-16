"""Run the Vault command `sessions attach-facts` (spec 2026-11-16 D25, I7, F9).

Contract: docs/contracts/vault-session-facts-v1.md.

The command line is `<python> -I -B <vault>/tools/wiki/cli.py sessions attach-facts --session <part> --facts <input>
--json` with the Vault root as the working folder, the same way `vault_publish_cli.py` runs Vault commands. This
adapter writes nothing in the Vault: the Vault command writes the attachment. Only the last stdout line is read as the
result JSON.

Outcomes: `written`, `exists` and `rejected` come from the command. `writer_missing` means the Vault has no
`tools/wiki/cli.py` or the command does not know `attach-facts` (exit code 2, a Vault older than the contract).
`failed` is everything else: no result line, another exit code, a time-out, or a start failure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CLI_RELATIVE_PATH = Path("tools") / "wiki" / "cli.py"
ATTACH_FACTS_INPUT_SCHEMA = "vault-session-facts-input/1"
ATTACH_FACTS_TIMEOUT_S = 60.0
_USAGE_EXIT_CODE = 2

AttachStatus = Literal["written", "exists", "rejected", "writer_missing", "failed"]


@dataclass(frozen=True)
class AttachFactsOutcome:
    status: AttachStatus
    path: str | None = None
    reason: str | None = None
    """Vault reason code for `rejected`."""
    message: str | None = None
    """What went wrong for `writer_missing` and `failed`."""


def run_attach_facts(
    vault_root: Path,
    part_path: Path,
    input_path: Path,
    *,
    timeout_s: float = ATTACH_FACTS_TIMEOUT_S,
    python_executable: str = sys.executable,
) -> AttachFactsOutcome:
    cli = vault_root / CLI_RELATIVE_PATH
    if not cli.is_file():
        return AttachFactsOutcome("writer_missing", message=f"{CLI_RELATIVE_PATH} is missing in {vault_root}")
    command = [
        python_executable,
        "-I",
        "-B",
        str(cli),
        "sessions",
        "attach-facts",
        "--session",
        str(part_path),
        "--facts",
        str(input_path),
        "--json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=vault_root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return AttachFactsOutcome("failed", message=f"sessions attach-facts did not finish in {timeout_s:g} seconds")
    except OSError as exc:
        return AttachFactsOutcome("failed", message=f"sessions attach-facts could not start: {exc}")
    if completed.returncode == _USAGE_EXIT_CODE:
        message = f"the Vault tool does not know sessions attach-facts: {_last_line(completed.stderr)}"
        return AttachFactsOutcome("writer_missing", message=message)
    result = _result(completed.stdout)
    if result is None:
        return AttachFactsOutcome(
            "failed",
            message=f"sessions attach-facts exited with {completed.returncode} without a result line: "
            f"{_last_line(completed.stderr) or _last_line(completed.stdout)}",
        )
    status, path, reason = result
    if status == "written" and completed.returncode == 0:
        return AttachFactsOutcome("written", path=path)
    if status == "exists" and completed.returncode == 0:
        return AttachFactsOutcome("exists", path=path)
    if status == "rejected" and completed.returncode == 1:
        return AttachFactsOutcome("rejected", path=path, reason=reason or "unknown")
    return AttachFactsOutcome(
        "failed", message=f"sessions attach-facts returned {status} with exit code {completed.returncode}"
    )


def _result(stdout: str) -> tuple[str, str | None, str | None] | None:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if status not in ("written", "exists", "rejected"):
        return None
    path, reason = payload.get("path"), payload.get("reason")
    return status, path if isinstance(path, str) else None, reason if isinstance(reason, str) else None


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:300] if lines else ""
