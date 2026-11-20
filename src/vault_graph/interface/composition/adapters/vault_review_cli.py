"""Run the Vault tool's ``review resolve --json`` as a subprocess (spec 2026-11-20 D1, D9, I5).

This is the sixth Vault write path. Only ``interface/cli/review_commands.py`` may import this module
(spec 2026-11-20 I2): a person typing ``vg review`` is the only caller.

The command is built like ``vault_publish_cli.py``: the vault-graph Python with ``-I -B``, the Vault root as
the working directory, and a time limit. vault-graph writes no Vault file itself.

Only ``status``, ``reason``, ``written_paths`` and ``messages`` of the ``vault-review-result/v1`` object on
standard output are read. The outcome is ``resolved`` only when the Vault says ``resolved``. Everything else is
a failure: ``rejected`` when the Vault refused, ``error`` when no contract object came back. Exit code 2 means
argparse refused the command: the Vault tools predate contract 4.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vault_graph.interface.composition.adapters.vault_publish_cli import (
    CLI_RELATIVE_PATH,
    MAX_MESSAGE_LINES,
    REVIEW_RESULT_FORMAT,
)
from vault_graph.operation.memory.memory_write_service import PUBLISH_TIMEOUT_SECONDS

ResolveStatus = Literal["accepted", "rejected"]
ResolveOutcomeStatus = Literal["resolved", "rejected", "error"]

COMMAND = "review resolve"
TARGET_CHANGED_REASON = "target-changed"
TARGET_CHANGED_GUIDANCE = (
    "The target page changed after this proposal was made. Reject this proposal, then propose it again."
)
RESOLVE_MIGRATE_MESSAGE = (
    "The Vault tools do not support review resolve --json (Vault contract below 4). "
    "Migrate the Vault to contract 4: run `vault-builder audit --target <vault> --plan-out <plan.json>`, "
    "review the plan, then run `vault-builder apply --target <vault> --plan <plan.json>`."
)
TIMEOUT_GUIDANCE = "Run `vg review list` and check the Vault git status to see whether the proposal was resolved."


@dataclass(frozen=True)
class ReviewResolveOutcome:
    """What the Vault tool reported for one ``review resolve``.

    ``reason`` and ``written_paths`` are the Vault's own values. ``messages`` are the Vault's lines unchanged, or the
    adapter's description when no contract object came back. ``guidance`` is what the person should do next.
    """

    status: ResolveOutcomeStatus
    reason: str | None = None
    written_paths: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()
    guidance: tuple[str, ...] = ()


class VaultReviewCli:
    def __init__(self, *, python_executable: str = sys.executable) -> None:
        self._python = python_executable

    def resolve(
        self,
        vault_root: Path,
        review_path: str,
        *,
        status: ResolveStatus,
        resolution: str,
        timeout_s: float = PUBLISH_TIMEOUT_SECONDS,
    ) -> ReviewResolveOutcome:
        """Accept or reject one review item. ``review_path`` is the item path as the Vault names it."""
        cli = vault_root / CLI_RELATIVE_PATH
        if not cli.is_file():
            return ReviewResolveOutcome(
                "error", messages=(f"This Vault has no {COMMAND}: {CLI_RELATIVE_PATH} is missing.",)
            )
        arguments = ["review", "resolve", review_path, "--status", status, "--resolution", resolution, "--json"]
        try:
            completed = subprocess.run(
                [self._python, "-I", "-B", str(cli), *arguments],
                cwd=vault_root,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ReviewResolveOutcome(
                "error",
                messages=(
                    f"{COMMAND} did not finish in {timeout_s:g} seconds and was stopped. The result is unknown.",
                ),
                guidance=(TIMEOUT_GUIDANCE,),
            )
        except OSError as exc:
            return ReviewResolveOutcome("error", messages=(f"{COMMAND} could not start: {exc}",))
        if completed.returncode == 2:
            return ReviewResolveOutcome(
                "error", messages=_last_lines("", completed.stderr), guidance=(RESOLVE_MIGRATE_MESSAGE,)
            )
        result = _resolve_result(completed.stdout)
        if result is None:
            return ReviewResolveOutcome(
                "error",
                messages=(
                    f"{COMMAND} exited with {completed.returncode} without a {REVIEW_RESULT_FORMAT} JSON object. "
                    "Last output lines follow.",
                    *_last_lines(completed.stdout, completed.stderr),
                ),
            )
        vault_status, reason, written_paths, messages = result
        if vault_status == "resolved":
            return ReviewResolveOutcome("resolved", reason=reason, written_paths=written_paths, messages=messages)
        # The lint-gated branch of the Vault tool reports its refusal on standard error and leaves
        # ``messages`` empty. Those lines are shown as they are, never parsed.
        shown = messages or _last_lines("", completed.stderr)
        guidance = (TARGET_CHANGED_GUIDANCE,) if reason == TARGET_CHANGED_REASON else ()
        return ReviewResolveOutcome(
            "rejected", reason=reason, written_paths=written_paths, messages=shown, guidance=guidance
        )


def _resolve_result(stdout: str) -> tuple[str, str | None, tuple[str, ...], tuple[str, ...]] | None:
    """Return (status, reason, written_paths, messages) from a resolve result object, or None for anything else."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if not isinstance(data, dict) or data.get("format") != REVIEW_RESULT_FORMAT:
        return None
    status = data.get("status")
    reason = data.get("reason")
    if status not in {"resolved", "rejected"} or not (reason is None or isinstance(reason, str)):
        return None
    written_paths = _strings(data.get("written_paths"))
    messages = _strings(data.get("messages"))
    if written_paths is None or messages is None:
        return None
    return str(status), reason, written_paths, messages


def _strings(value: object) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _last_lines(stdout: str, stderr: str) -> tuple[str, ...]:
    lines = [line for line in (stdout + "\n" + stderr).splitlines() if line.strip()]
    return tuple(lines[-MAX_MESSAGE_LINES:])


__all__ = [
    "COMMAND",
    "RESOLVE_MIGRATE_MESSAGE",
    "TARGET_CHANGED_GUIDANCE",
    "TARGET_CHANGED_REASON",
    "TIMEOUT_GUIDANCE",
    "ResolveOutcomeStatus",
    "ResolveStatus",
    "ReviewResolveOutcome",
    "VaultReviewCli",
]
