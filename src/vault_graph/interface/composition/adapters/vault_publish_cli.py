"""``VaultWriter`` that runs the Vault tool's ``publish-draft --json`` as a subprocess (spec 2026-11-02 V3 어댑터).

The command matches how the llm-wiki router runs Vault CLI commands
(``$HOME/.claude/vault-builder/llm_wiki_router.py`` 839-845): the vault-graph Python with
``-I -B``, the Vault root as the working directory, and a time limit. ``--report`` is never
passed because it writes a report under the Vault ``scratch/reports/``.

Only the 계약1 JSON object on standard output is read (``format: vault-publish-result/v1``). Human
text is never parsed. Exit code 2 with ``unrecognized arguments`` means the Vault tools predate
contract 4 and do not know ``--json``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vault_graph.operation.memory.memory_ports import WriteOutcome

CLI_RELATIVE_PATH = Path("tools") / "wiki" / "cli.py"
PUBLISH_RESULT_FORMAT = "vault-publish-result/v1"
MAX_MESSAGE_LINES = 20
MIGRATE_MESSAGE = (
    "The Vault tools do not support publish-draft --json (Vault contract below 4). "
    "Migrate the Vault to contract 4 with vault-builder tools/vault_migration/cli.py audit, then apply."
)
LINT_DIRTY_MESSAGE = "Vault lint was already failing before the write. Fix the Vault lint first, then retry."


class VaultPublishCli:
    def __init__(self, *, python_executable: str = sys.executable) -> None:
        self._python = python_executable

    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        cli = vault_root / CLI_RELATIVE_PATH
        if not cli.is_file():
            return WriteOutcome(
                "error", messages=(f"This Vault has no publish-draft: {CLI_RELATIVE_PATH} is missing.",)
            )
        try:
            completed = subprocess.run(
                [self._python, "-I", "-B", str(cli), "publish-draft", str(draft_path), "--json"],
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
                    f"publish-draft did not finish in {timeout_s:g} seconds and was stopped. "
                    "The result is unknown; check the Vault git status.",
                ),
            )
        except OSError as exc:
            return WriteOutcome("error", messages=(f"publish-draft could not start: {exc}",))

        if completed.returncode == 2 and "unrecognized arguments" in completed.stderr:
            return WriteOutcome("error", messages=(MIGRATE_MESSAGE,))
        result = _contract_result(completed.stdout)
        if result is None:
            return WriteOutcome(
                "error",
                messages=(
                    f"publish-draft exited with {completed.returncode} without a {PUBLISH_RESULT_FORMAT} JSON object. "
                    "Last output lines follow.",
                    *_last_lines(completed.stdout, completed.stderr),
                ),
            )
        status, reason, written_paths, messages = result
        if status == "published":
            return WriteOutcome("published", written_paths=written_paths, messages=messages)
        notes: list[str] = [f"The Vault rejected the draft ({reason})."]
        if reason == "lint-dirty-before":
            notes.append(LINT_DIRTY_MESSAGE)
        return WriteOutcome("rejected", messages=(*notes, *messages), reason=reason)


def _contract_result(stdout: str) -> tuple[str, str | None, tuple[str, ...], tuple[str, ...]] | None:
    """Return (status, reason, written_paths, messages) from a 계약1 object, or None for anything else."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("format") != PUBLISH_RESULT_FORMAT:
        return None
    status = data.get("status")
    reason = data.get("reason")
    written = data.get("written_paths")
    messages = data.get("messages")
    if status not in {"published", "rejected"} or not (reason is None or isinstance(reason, str)):
        return None
    written_paths = _strings(written)
    message_lines = _strings(messages)
    if written_paths is None or message_lines is None:
        return None
    return status, reason, written_paths, message_lines


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _last_lines(stdout: str, stderr: str) -> tuple[str, ...]:
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    return tuple(lines[-MAX_MESSAGE_LINES:])


__all__ = ["CLI_RELATIVE_PATH", "MAX_MESSAGE_LINES", "MIGRATE_MESSAGE", "PUBLISH_RESULT_FORMAT", "VaultPublishCli"]
