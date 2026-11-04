"""``VaultWriter`` that runs the Vault tool's CLI as a subprocess (spec 2026-11-02 V3 어댑터).

``publish`` runs ``publish-draft --json`` (계약1) and ``propose`` runs ``review propose --json``
(계약4). The command matches how the llm-wiki router runs Vault CLI commands
(``$HOME/.claude/vault-builder/llm_wiki_router.py`` 839-845): the vault-graph Python with
``-I -B``, the Vault root as the working directory, and a time limit. ``--report`` is never
passed because it writes a report under the Vault ``scratch/reports/``.

Only the contract JSON object on standard output is read (``format: vault-publish-result/v1`` or
``vault-review-result/v1``). Human text is never parsed. Exit code 2 means argparse refused the
command: the Vault tools predate contract 4 and do not know ``--json`` or ``review propose``.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from vault_graph.operation.memory.memory_ports import WriteOutcome

CLI_RELATIVE_PATH = Path("tools") / "wiki" / "cli.py"
PUBLISH_RESULT_FORMAT = "vault-publish-result/v1"
REVIEW_RESULT_FORMAT = "vault-review-result/v1"
MAX_MESSAGE_LINES = 20
MIGRATE_MESSAGE = (
    "The Vault tools do not support publish-draft --json (Vault contract below 4). "
    "Migrate the Vault to contract 4: run `vault-builder audit --target <vault>`, then `vault-builder apply`."
)
PROPOSE_MIGRATE_MESSAGE = (
    "The Vault tools do not support review propose --json (Vault contract below 4). "
    "Migrate the Vault to contract 4: run `vault-builder audit --target <vault>`, then `vault-builder apply`."
)
LINT_DIRTY_MESSAGE = "Vault lint was already failing before the write. Fix the Vault lint first, then retry."


class VaultPublishCli:
    def __init__(self, *, python_executable: str = sys.executable) -> None:
        self._python = python_executable

    def publish(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        completed = self._run(vault_root, "publish-draft", ["publish-draft", str(draft_path), "--json"], timeout_s)
        if isinstance(completed, WriteOutcome):
            return completed
        if completed.returncode == 2 and "unrecognized arguments" in completed.stderr:
            return WriteOutcome("error", messages=(MIGRATE_MESSAGE,))
        result = _publish_result(completed.stdout)
        if result is None:
            return _not_contract_json("publish-draft", PUBLISH_RESULT_FORMAT, completed)
        status, reason, written_paths, messages = result
        if status == "published":
            return WriteOutcome("published", written_paths=written_paths, messages=messages)
        notes: list[str] = [f"The Vault rejected the draft ({reason})."]
        if reason == "lint-dirty-before":
            notes.append(LINT_DIRTY_MESSAGE)
        return WriteOutcome("rejected", messages=(*notes, *messages), reason=reason)

    def propose(self, vault_root: Path, draft_path: Path, *, summary: str, timeout_s: float) -> WriteOutcome:
        completed = self._run(
            vault_root,
            "review propose",
            ["review", "propose", "--draft", str(draft_path), "--summary", summary, "--json"],
            timeout_s,
        )
        if isinstance(completed, WriteOutcome):
            return completed
        if completed.returncode == 2:
            return WriteOutcome("error", messages=(PROPOSE_MIGRATE_MESSAGE, *_last_lines("", completed.stderr)))
        result = _review_result(completed.stdout)
        if result is None:
            return _not_contract_json("review propose", REVIEW_RESULT_FORMAT, completed)
        status, review_path, messages = result
        if status == "proposed":
            return WriteOutcome("proposed", messages=messages, review_path=review_path)
        return WriteOutcome("rejected", messages=("The Vault refused the memory proposal.", *messages))

    def _run(
        self, vault_root: Path, command: str, arguments: list[str], timeout_s: float
    ) -> subprocess.CompletedProcess[str] | WriteOutcome:
        cli = vault_root / CLI_RELATIVE_PATH
        if not cli.is_file():
            return WriteOutcome("error", messages=(f"This Vault has no {command}: {CLI_RELATIVE_PATH} is missing.",))
        try:
            return subprocess.run(
                [self._python, "-I", "-B", str(cli), *arguments],
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
                    f"{command} did not finish in {timeout_s:g} seconds and was stopped. "
                    "The result is unknown; check the Vault git status.",
                ),
            )
        except OSError as exc:
            return WriteOutcome("error", messages=(f"{command} could not start: {exc}",))


def _not_contract_json(command: str, result_format: str, completed: subprocess.CompletedProcess[str]) -> WriteOutcome:
    return WriteOutcome(
        "error",
        messages=(
            f"{command} exited with {completed.returncode} without a {result_format} JSON object. "
            "Last output lines follow.",
            *_last_lines(completed.stdout, completed.stderr),
        ),
    )


def _contract_object(stdout: str, result_format: str) -> dict[str, object] | None:
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("format") != result_format:
        return None
    return data


def _publish_result(stdout: str) -> tuple[str, str | None, tuple[str, ...], tuple[str, ...]] | None:
    """Return (status, reason, written_paths, messages) from a 계약1 object, or None for anything else."""
    data = _contract_object(stdout, PUBLISH_RESULT_FORMAT)
    if data is None:
        return None
    status = data.get("status")
    reason = data.get("reason")
    if status not in {"published", "rejected"} or not (reason is None or isinstance(reason, str)):
        return None
    written_paths = _strings(data.get("written_paths"))
    message_lines = _strings(data.get("messages"))
    if written_paths is None or message_lines is None:
        return None
    return str(status), reason, written_paths, message_lines


def _review_result(stdout: str) -> tuple[str, str | None, tuple[str, ...]] | None:
    """Return (status, review_path, messages) from a 계약4 object, or None for anything else.

    ``proposed`` must name a non-empty ``review_path``.
    """
    data = _contract_object(stdout, REVIEW_RESULT_FORMAT)
    if data is None:
        return None
    status = data.get("status")
    review_path = data.get("review_path")
    message_lines = _strings(data.get("messages"))
    if status not in {"proposed", "rejected"} or message_lines is None:
        return None
    if status == "proposed":
        if not isinstance(review_path, str) or not review_path:
            return None
        return "proposed", review_path, message_lines
    return "rejected", None, message_lines


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _last_lines(stdout: str, stderr: str) -> tuple[str, ...]:
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    return tuple(lines[-MAX_MESSAGE_LINES:])


__all__ = [
    "CLI_RELATIVE_PATH",
    "MAX_MESSAGE_LINES",
    "MIGRATE_MESSAGE",
    "PROPOSE_MIGRATE_MESSAGE",
    "PUBLISH_RESULT_FORMAT",
    "REVIEW_RESULT_FORMAT",
    "VaultPublishCli",
]
