"""Record one stated memory in a Vault through the Vault tool's publish-draft (spec 4.2.4, 결정8, S5, S6, V1).

vault-graph never writes Vault files itself. This service checks the agent's fields, picks one
Vault without guessing, builds a draft in the operating system's temporary directory, and
hands the draft to a ``VaultPublisher``. The draft directory is removed after every outcome.
"""

from __future__ import annotations

import json
import tempfile
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path

from vault_graph.operation.memory.memory_drafts import build_draft
from vault_graph.operation.memory.memory_ports import PublishOutcome, VaultPublisher
from vault_graph.operation.memory.memory_requests import MemoryWriteResult, RememberRequest, validate_request
from vault_graph.project.context.project_binding_reader import MappedVault, VaultMapReader

PUBLISH_TIMEOUT_SECONDS = 120.0  # Same as the llm-wiki router CLI_TIMEOUT_SECONDS.
NEXT_INDEX_MESSAGE = "The recorded page becomes searchable after the next index run (vg index)."

_LOCKS_GUARD = threading.Lock()
_VAULT_LOCKS: dict[str, threading.Lock] = {}


def _vault_lock(vault_root: Path) -> threading.Lock:
    """Return the process-wide lock for one Vault so calls for it run one at a time."""
    with _LOCKS_GUARD:
        return _VAULT_LOCKS.setdefault(str(vault_root), threading.Lock())


class MemoryWriteService:
    def __init__(
        self,
        *,
        vault_map: VaultMapReader | None,
        publisher: VaultPublisher,
        today: Callable[[], date] = date.today,
        temp_root: Path | None = None,
        timeout_s: float = PUBLISH_TIMEOUT_SECONDS,
        vault_map_problem: str | None = None,
    ) -> None:
        self._vault_map = vault_map
        self._publisher = publisher
        self._today = today
        self._temp_root = temp_root
        self._timeout_s = timeout_s
        self._vault_map_problem = vault_map_problem

    def remember(self, request: RememberRequest) -> MemoryWriteResult:
        problems = validate_request(request)
        if problems:
            return MemoryWriteResult("rejected", request.vault, (), problems)

        selected = self._select_vault(request)
        if isinstance(selected, str):
            return MemoryWriteResult("error", None, (), (selected,))

        draft = build_draft(request, today=self._today())
        target = str(draft["path"])
        # The existence check runs under the lock so concurrent calls for one page cannot both pass it.
        with _vault_lock(selected.path):
            if (selected.path / target).exists():
                return MemoryWriteResult(
                    "rejected",
                    selected.name,
                    (),
                    (f"A page already exists at {target}. remember only adds new pages.",),
                )
            outcome = self._publish(selected.path, draft)
        messages = outcome.messages
        if outcome.status == "published":
            messages = (*messages, NEXT_INDEX_MESSAGE)
        return MemoryWriteResult(outcome.status, selected.name, outcome.written_paths, messages)

    def _publish(self, vault_root: Path, draft: dict[str, object]) -> PublishOutcome:
        with tempfile.TemporaryDirectory(prefix="vault-graph-remember-", dir=self._temp_root) as folder:
            draft_path = Path(folder) / f"{Path(str(draft['path'])).stem}.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                return self._publisher.publish_draft(vault_root, draft_path, timeout_s=self._timeout_s)
            except Exception as exc:  # noqa: BLE001 - any publisher failure is reported, never retried.
                return PublishOutcome("error", (), (f"publish-draft could not run: {exc}",))

    def _select_vault(self, request: RememberRequest) -> MappedVault | str:
        if self._vault_map is None:
            reason = self._vault_map_problem or "vault-map.json is missing or unusable."
            return f"Cannot choose the target Vault: {reason}"
        if request.vault is not None:
            for vault in self._vault_map.vaults:
                if vault.name == request.vault:
                    return vault
            return f"Cannot choose the target Vault: no Vault named {request.vault} in vault-map.json."
        if request.cwd is None:
            return "Cannot choose the target Vault: pass vault or cwd."
        match = self._vault_map.find_project(Path(request.cwd))
        if len(match.vaults) == 1:
            return match.vaults[0]
        if len(match.vaults) > 1:
            names = ", ".join(vault.name for vault in match.vaults)
            return f"Cannot choose the target Vault: the project links several Vaults ({names}). Pass vault."
        reason = match.reason or f"{request.cwd} is not linked to a Vault."
        return f"Cannot choose the target Vault: {reason}"


__all__ = ["NEXT_INDEX_MESSAGE", "PUBLISH_TIMEOUT_SECONDS", "MemoryWriteService"]
