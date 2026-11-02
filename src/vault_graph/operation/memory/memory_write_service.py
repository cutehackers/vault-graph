"""Add, update and retire memories through the Vault tool (spec 2026-11-02 V3, 결정12, 결정S5, 결정S6, 결정S8).

vault-graph never writes Vault files itself. Each operation checks the agent's fields, picks one
Vault without guessing, builds a draft in the operating system's temporary directory, and hands the
draft to a ``VaultWriter``. The draft directory is removed after every outcome.

``basis="stated"`` publishes the draft (계약1). ``basis="inferred"`` sends the same draft to the Vault
review queue (계약4 ``review propose``) and returns ``proposed`` with the review item path and the
command a person runs to accept it. vault-graph does not index ``scratch/review/``, so a proposal is
not in recall or search until it is accepted and the next index run picks up the page.
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
PROPOSED_MESSAGE = (
    "basis inferred: the fact waits in the Vault review queue and is not in recall or search until a person accepts it."
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
        refused = _refuse_input(validate_remember(request), request.vault)
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
            outcome = self._send(chosen.path, draft, request.basis, f"Add memory: {request.title.strip()}")
        return _result(chosen, outcome)

    def update(self, request: UpdateRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_update(request), request.vault)
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

            outcome = self._send(
                chosen.path, draft, request.basis, f"Update memory {request.path}", before_send=unchanged
            )
        return _result(chosen, outcome)

    def retire(self, request: RetireRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_retire(request), request.vault)
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
            outcome = self._send(
                chosen.path,
                build_retire_draft(request, today=self._today()),
                request.basis,
                f"Retire memory {request.path}: {request.reason.strip()}",
            )
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

    def _send(
        self,
        vault_root: Path,
        draft: dict[str, object],
        basis: str,
        summary: str,
        *,
        before_send: Callable[[], bool] | None = None,
    ) -> WriteOutcome:
        """Publish a stated draft or propose an inferred one. Both read the draft from the OS temp folder."""
        with tempfile.TemporaryDirectory(prefix="vault-graph-memory-", dir=self._temp_root) as folder:
            draft_path = Path(folder) / "draft.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if before_send is not None and not before_send():
                return WriteOutcome("rejected", messages=(PAGE_CHANGED_MESSAGE,))
            if basis == "inferred":
                try:
                    return self._writer.propose(vault_root, draft_path, summary=summary, timeout_s=self._timeout_s)
                except Exception as exc:  # noqa: BLE001 - any writer failure is reported, never retried.
                    return WriteOutcome("error", messages=(f"review propose could not run: {exc}",))
            try:
                return self._writer.publish(vault_root, draft_path, timeout_s=self._timeout_s)
            except Exception as exc:  # noqa: BLE001 - any writer failure is reported, never retried.
                return WriteOutcome("error", messages=(f"publish-draft could not run: {exc}",))


def _refuse_input(problems: tuple[str, ...], vault: str | None) -> MemoryWriteResult | None:
    if problems:
        return MemoryWriteResult("rejected", vault, (), problems)
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


def approval_command(review_path: str) -> str:
    """The Vault command a person runs, from the Vault root, to accept a memory proposal."""
    return f'python3 tools/wiki/cli.py review resolve {review_path} --status accepted --resolution "<reason>"'


def _result(vault: MappedVault, outcome: WriteOutcome) -> MemoryWriteResult:
    messages = outcome.messages
    review_path = None
    if outcome.status == "published":
        messages = (*messages, NEXT_INDEX_MESSAGE)
    elif outcome.status == "proposed":
        if outcome.review_path is None:
            return MemoryWriteResult(
                "error",
                vault.name,
                (),
                (*messages, "The Vault reported a proposal without a review_path."),
                vault_role=vault.role,
            )
        review_path = outcome.review_path
        messages = (
            *messages,
            PROPOSED_MESSAGE,
            f"To accept it, run in Vault {vault.name}: {approval_command(review_path)}",
        )
    return MemoryWriteResult(
        outcome.status,
        vault.name,
        outcome.written_paths,
        messages,
        review_path=review_path,
        vault_role=vault.role,
    )


__all__ = [
    "NEXT_INDEX_MESSAGE",
    "PAGE_CHANGED_MESSAGE",
    "PROPOSED_MESSAGE",
    "PUBLISH_TIMEOUT_SECONDS",
    "MemoryWriteService",
    "approval_command",
]
