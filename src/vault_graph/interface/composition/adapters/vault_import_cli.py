"""``VaultImporter`` that runs Vault ``import-source`` as a subprocess (spec 2026-11-05 §4.4.5, path 4).

The command is ``import-source <note> --into raw/imports/claude-memory/ --json`` (Vault request S8), run
the same way as ``vault_publish_cli``: the vault-graph Python with ``-I -B``, the Vault root as the
working directory, and a time limit. The Vault command copies the note bytes and makes the source page.
vault-graph reads only the JSON object on standard output:

- ``{"status": "imported" | "exists", "raw_path", "source_page", "sha256", "created"}`` with exit 0.
  Both become ``published``: the copy exists now. ``exists`` wrote nothing.
- ``{"status": "error", "message"}`` with exit 1: the Vault refused the note, reported as ``rejected``.

Exit code 2 with an argparse "invalid choice" means the Vault tools predate request S8.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vault_graph.interface.composition.adapters.vault_publish_cli import CLI_RELATIVE_PATH, MAX_MESSAGE_LINES
from vault_graph.operation.memory.memory_ports import WriteOutcome

CLAUDE_MEMORY_IMPORT_DIR = "raw/imports/claude-memory/"
UPDATE_VAULT_TOOLS_MESSAGE = (
    "The Vault tools do not know import-source. Update the Vault tools (vault-builder) in this Vault, then retry."
)


class VaultImportCli:
    def __init__(self, *, python_executable: str = sys.executable) -> None:
        self._python = python_executable

    def import_source(self, vault_root: Path, note_path: Path, *, timeout_s: float) -> WriteOutcome:
        cli = vault_root / CLI_RELATIVE_PATH
        if not cli.is_file():
            return WriteOutcome(
                "error", messages=(f"This Vault has no import-source: {CLI_RELATIVE_PATH} is missing.",)
            )
        try:
            completed = subprocess.run(
                [
                    self._python,
                    "-I",
                    "-B",
                    str(cli),
                    "import-source",
                    str(note_path),
                    "--into",
                    CLAUDE_MEMORY_IMPORT_DIR,
                    "--json",
                ],
                cwd=vault_root,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return WriteOutcome(
                "error",
                messages=(
                    f"import-source did not finish in {timeout_s:g} seconds and was stopped. "
                    "The result is unknown; check the Vault git status.",
                ),
            )
        except OSError as exc:
            return WriteOutcome("error", messages=(f"import-source could not start: {exc}",))
        if completed.returncode == 2 and "invalid choice" in completed.stderr:
            return WriteOutcome("error", messages=(UPDATE_VAULT_TOOLS_MESSAGE,))
        outcome = _import_outcome(completed.stdout)
        if outcome is not None:
            return outcome
        return WriteOutcome(
            "error",
            messages=(
                f"import-source exited with {completed.returncode} without its JSON result. Last output lines follow.",
                *_last_lines(completed.stdout, completed.stderr),
            ),
        )


def _import_outcome(stdout: str) -> WriteOutcome | None:
    """Read the ``import-source --json`` object, or None for anything else."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    status = data.get("status")
    if status == "error":
        message = data.get("message")
        if not isinstance(message, str):
            return None
        return WriteOutcome("rejected", messages=("The Vault refused to import the note.", message))
    if status not in {"imported", "exists"}:
        return None
    raw_path = data.get("raw_path")
    source_page = data.get("source_page")
    created = data.get("created")
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or not isinstance(source_page, str)
        or not source_page
        or not isinstance(created, list)
        or not all(isinstance(item, str) for item in created)
    ):
        return None
    if status == "exists":
        message = f"Already imported as {raw_path} ({source_page}); nothing written."
    else:
        message = f"Imported as {raw_path} ({source_page})."
    return WriteOutcome(
        "published",
        written_paths=tuple(created),
        messages=(message,),
        raw_path=raw_path,
        source_page=source_page,
    )


def _last_lines(stdout: str, stderr: str) -> tuple[str, ...]:
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    return tuple(lines[-MAX_MESSAGE_LINES:])


__all__ = ["CLAUDE_MEMORY_IMPORT_DIR", "UPDATE_VAULT_TOOLS_MESSAGE", "VaultImportCli"]
