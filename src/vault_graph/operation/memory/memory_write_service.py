"""Add, update and retire memories through the Vault tool (spec 2026-11-02 V3, 결정12, 결정S5, 결정S6, 결정S8).

vault-graph never writes Vault files itself. Each operation checks the agent's fields, picks one
Vault without guessing, builds a draft in the operating system's temporary directory, and hands the
draft to a ``VaultWriter``. The draft directory is removed after every outcome.

Only ``basis="stated"`` reaches the Vault in this version. ``basis="inferred"`` is rejected without
any Vault command until the inferred path (V3, task 19) sends it to Vault review instead.
"""

from __future__ import annotations

import json
import tempfile
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path

from vault_graph.operation.memory.memory_drafts import build_remember_draft, build_retire_draft, build_update_draft
from vault_graph.operation.memory.memory_ports import VaultPageReader, VaultWriter, WriteOutcome
from vault_graph.operation.memory.memory_requests import (
    MemoryWriteResult,
    RememberRequest,
    RetireRequest,
    UpdateRequest,
    VaultCandidate,
    validate_remember,
    validate_retire,
    validate_update,
)
from vault_graph.operation.memory.memory_target import (
    Choice,
    VaultRequired,
    WriteRefusal,
    choose_page_vault,
    choose_write_vault,
)
from vault_graph.project.context.project_binding_reader import MappedVault, VaultMapReader

PUBLISH_TIMEOUT_SECONDS = 120.0  # Same as the llm-wiki router CLI_TIMEOUT_SECONDS.
NEXT_INDEX_MESSAGE = "The recorded page becomes searchable after the next index run (vg index)."
INFERRED_NOT_SUPPORTED_MESSAGE = (
    "basis inferred is not written yet: only facts the user stated are recorded. "
    "Ask the user to confirm the fact, then call again with basis stated."
)
PAGE_CHANGED_MESSAGE = (
    "The page changed after vault-graph read it, so the update was not sent. Please read it again and retry."
)

_LOCKS_GUARD = threading.Lock()
_VAULT_LOCKS: dict[str, threading.Lock] = {}


def _vault_lock(vault_root: Path) -> threading.Lock:
    """Return the process-wide lock for one Vault so writes to it run one at a time."""
    with _LOCKS_GUARD:
        return _VAULT_LOCKS.setdefault(str(vault_root), threading.Lock())


class MemoryWriteService:
    def __init__(
        self,
        *,
        vault_map: VaultMapReader | None,
        writer: VaultWriter,
        page_reader: VaultPageReader,
        today: Callable[[], date] = date.today,
        temp_root: Path | None = None,
        timeout_s: float = PUBLISH_TIMEOUT_SECONDS,
        vault_map_problem: str | None = None,
    ) -> None:
        self._vault_map = vault_map
        self._writer = writer
        self._page_reader = page_reader
        self._today = today
        self._temp_root = temp_root
        self._timeout_s = timeout_s
        self._vault_map_problem = vault_map_problem

    def remember(self, request: RememberRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_remember(request), request.basis, request.vault)
        if refused is not None:
            return refused
        if self._vault_map is None:
            return self._no_vault_map()
        chosen = choose_write_vault(request.vault, _cwd(request.cwd), self._vault_map)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)

        draft = build_remember_draft(request, today=self._today())
        target = str(draft["path"])
        # The existence check runs under the lock so concurrent calls for one page cannot both pass it.
        with _vault_lock(chosen.path):
            if self._page_reader.read(chosen.path, target) is not None:
                return _result(
                    chosen,
                    WriteOutcome(
                        "rejected",
                        messages=(
                            f"A page already exists at {target}. remember only adds new pages; "
                            "use update_memory to change it.",
                        ),
                    ),
                )
            outcome = self._publish(chosen.path, draft)
        return _result(chosen, outcome)

    def update(self, request: UpdateRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_update(request), request.basis, request.vault)
        if refused is not None:
            return refused
        chosen = self._page_vault(request.vault, request.cwd, request.path)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)

        with _vault_lock(chosen.path):
            current = self._page_reader.read(chosen.path, request.path)
            if current is None:
                return _result(chosen, WriteOutcome("rejected", messages=(f"No page at {request.path}.",)))
            try:
                draft = build_update_draft(request, current, today=self._today())
            except ValueError as exc:
                return _result(chosen, WriteOutcome("rejected", messages=(str(exc),)))

            def unchanged() -> bool:
                again = self._page_reader.read(chosen.path, request.path)
                return again is not None and again.sha256 == current.sha256

            outcome = self._publish(chosen.path, draft, before_publish=unchanged)
        return _result(chosen, outcome)

    def retire(self, request: RetireRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_retire(request), request.basis, request.vault)
        if refused is not None:
            return refused
        chosen = self._page_vault(request.vault, request.cwd, request.path)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)

        with _vault_lock(chosen.path):
            if self._page_reader.read(chosen.path, request.path) is None:
                return _result(chosen, WriteOutcome("rejected", messages=(f"No page at {request.path}.",)))
            replaced_by = request.replaced_by
            if replaced_by is not None and self._page_reader.read(chosen.path, replaced_by) is None:
                return _result(
                    chosen,
                    WriteOutcome(
                        "rejected",
                        messages=(
                            f"replaced_by {replaced_by} is not a page in Vault {chosen.name}. "
                            "A replacement must be in the same Vault as the retired page.",
                        ),
                    ),
                )
            outcome = self._publish(chosen.path, build_retire_draft(request, today=self._today()))
        return _result(chosen, outcome)

    def _page_vault(self, vault: str | None, cwd: str | None, path: str) -> Choice | MemoryWriteResult:
        if self._vault_map is None:
            return self._no_vault_map()
        return choose_page_vault(
            vault,
            _cwd(cwd),
            self._vault_map,
            path=path,
            has_page=lambda candidate: self._page_reader.read(candidate.path, path) is not None,
        )

    def _no_vault_map(self) -> MemoryWriteResult:
        reason = self._vault_map_problem or "vault-map.json is missing or unusable."
        return MemoryWriteResult("error", None, (), (f"Cannot choose the target Vault: {reason}",))

    def _publish(
        self,
        vault_root: Path,
        draft: dict[str, object],
        *,
        before_publish: Callable[[], bool] | None = None,
    ) -> WriteOutcome:
        with tempfile.TemporaryDirectory(prefix="vault-graph-memory-", dir=self._temp_root) as folder:
            draft_path = Path(folder) / "draft.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if before_publish is not None and not before_publish():
                return WriteOutcome("rejected", messages=(PAGE_CHANGED_MESSAGE,))
            try:
                return self._writer.publish(vault_root, draft_path, timeout_s=self._timeout_s)
            except Exception as exc:  # noqa: BLE001 - any writer failure is reported, never retried.
                return WriteOutcome("error", messages=(f"publish-draft could not run: {exc}",))


def _refuse_input(problems: tuple[str, ...], basis: object, vault: str | None) -> MemoryWriteResult | None:
    if problems:
        return MemoryWriteResult("rejected", vault, (), problems)
    if basis == "inferred":
        return MemoryWriteResult("rejected", vault, (), (INFERRED_NOT_SUPPORTED_MESSAGE,))
    return None


def _cwd(cwd: str | None) -> Path | None:
    return None if cwd is None else Path(cwd)


def _choice_result(choice: Choice | MemoryWriteResult) -> MemoryWriteResult:
    if isinstance(choice, MemoryWriteResult):
        return choice
    if isinstance(choice, VaultRequired):
        return MemoryWriteResult(
            "vault_required",
            None,
            (),
            (choice.message,),
            candidates=tuple(VaultCandidate(name=vault.name, role=vault.role) for vault in choice.candidates),
        )
    if isinstance(choice, WriteRefusal):
        return MemoryWriteResult(choice.status, None, (), choice.messages)
    raise TypeError(f"unexpected Vault choice: {choice!r}")


def _result(vault: MappedVault, outcome: WriteOutcome) -> MemoryWriteResult:
    messages = outcome.messages
    if outcome.status == "published":
        messages = (*messages, NEXT_INDEX_MESSAGE)
    return MemoryWriteResult(outcome.status, vault.name, outcome.written_paths, messages, vault_role=vault.role)


__all__ = [
    "INFERRED_NOT_SUPPORTED_MESSAGE",
    "NEXT_INDEX_MESSAGE",
    "PAGE_CHANGED_MESSAGE",
    "PUBLISH_TIMEOUT_SECONDS",
    "MemoryWriteService",
]
