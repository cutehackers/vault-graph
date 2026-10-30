"""Run the Vault tool's ``publish-draft`` as a subprocess (spec 4.2.4).

The command matches how the llm-wiki router runs Vault CLI commands
(``$HOME/.claude/vault-builder/llm_wiki_router.py`` 839-845): the vault-graph Python with
``-I -B``, the Vault root as the working directory, and a time limit. ``--report`` is never
passed because it writes a report under the Vault ``scratch/reports/``.

Output reading follows Vault ``tools/wiki/cli.py`` ``_publish_draft``: exit code 0 means the
draft was applied and lint passed, and each ``Applied draft: <path>`` line names a written page.
Any other exit code means validation or lint failed and publish-draft rolled back its changes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from vault_graph.operation.integration.remember_service import PublishOutcome

CLI_RELATIVE_PATH = Path("tools") / "wiki" / "cli.py"
APPLIED_PREFIX = "Applied draft: "
LINT_ABORT_MARKER = "Publish aborted: wiki lint must be clean"
MAX_MESSAGE_LINES = 20


class VaultPublishCli:
    def __init__(self, *, python_executable: str = sys.executable) -> None:
        self._python = python_executable

    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome:
        cli = vault_root / CLI_RELATIVE_PATH
        if not cli.is_file():
            return PublishOutcome("error", (), (f"This Vault has no publish-draft: {CLI_RELATIVE_PATH} is missing.",))
        try:
            completed = subprocess.run(
                [self._python, "-I", "-B", str(cli), "publish-draft", str(draft_path)],
                cwd=vault_root,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return PublishOutcome(
                "error",
                (),
                (
                    f"publish-draft did not finish in {timeout_s:g} seconds and was stopped. "
                    "The result is unknown; check the Vault git status.",
                ),
            )
        except OSError as exc:
            return PublishOutcome("error", (), (f"publish-draft could not start: {exc}",))

        lines = [line for line in (completed.stdout + "\n" + completed.stderr).splitlines() if line.strip()]
        messages = tuple(lines[-MAX_MESSAGE_LINES:])
        if completed.returncode == 0:
            written = tuple(line[len(APPLIED_PREFIX) :].strip() for line in lines if line.startswith(APPLIED_PREFIX))
            return PublishOutcome("published", written, messages)
        if any(LINT_ABORT_MARKER in line for line in lines):
            messages = (*messages, "Vault lint was already failing before the write. Fix the Vault first.")
        return PublishOutcome("rejected", (), messages)


__all__ = ["APPLIED_PREFIX", "CLI_RELATIVE_PATH", "MAX_MESSAGE_LINES", "VaultPublishCli"]
