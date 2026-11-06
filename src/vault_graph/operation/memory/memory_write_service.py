"""Add, update, retire, supersede and restore memories through the Vault tool (spec 2026-11-02 V3, 결정12,
결정S5, 결정S6, 결정S8, spec 2026-11-05 §4.4.4, §4.4.5, §4.4.13).

vault-graph never writes Vault files itself. Each operation checks the agent's fields, picks one
Vault without guessing, builds a draft, has ``DraftFiles`` write it outside every Vault, and hands
the draft file to a ``VaultWriter``. The draft file is removed after every outcome.

``basis="stated"`` publishes the draft (계약1). ``basis="inferred"`` sends the same draft to the Vault
review queue (계약4 ``review propose``) and returns ``proposed`` with the review item path and the
command a person runs to accept it. vault-graph does not index ``scratch/review/``, so a proposal is
not in recall or search until it is accepted and the next index run picks up the page.

``import_auto_memory`` hands one auto-memory note to Vault ``import-source`` (path 4). A write that names a
``candidate_key`` records it in the Graph Home review log when the result is ``published`` or
``proposed``, so the cleanup bundle does not offer it again. One cleanup sends at most
``INFERRED_PROPOSAL_LIMIT`` inferred proposals: a cleanup runs from one ``start_curation`` call
(``list_memory_candidates``) to the next in one server process.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from pathlib import Path

from vault_graph.operation.memory.memory_drafts import (
    build_remember_draft,
    build_restore_draft,
    build_retire_draft,
    build_supersede_claim_draft,
    build_update_draft,
)
from vault_graph.operation.memory.memory_ports import (
    DraftFiles,
    ReviewedLog,
    VaultImporter,
    VaultPageReader,
    VaultWriter,
    WriteOutcome,
)
from vault_graph.operation.memory.memory_requests import (
    PROJECT_KIND,
    ImportRequest,
    MemoryWriteResult,
    RememberRequest,
    RestoreRequest,
    RetireRequest,
    SupersedeClaimRequest,
    UpdateRequest,
    VaultCandidate,
    validate_import,
    validate_remember,
    validate_restore,
    validate_retire,
    validate_supersede_claim,
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
INFERRED_PROPOSAL_LIMIT = 10  # 결정29, 목표3
PROPOSAL_LIMIT_MESSAGE = (
    f"This cleanup already sent {INFERRED_PROPOSAL_LIMIT} inferred proposals, the proposal limit of one cleanup. "
    "The proposal was not sent. Call list_memory_candidates to start the next cleanup."
)
SUPERSEDE_REJECTED_HINT = "To replace the whole page instead of one claim row, use retire_memory(replaced_by=...)."
NO_IMPORTER_MESSAGE = "This vault-graph server has no Vault import-source runner, so the note was not imported."
RECORDED_OUTCOMES = frozenset({"published", "proposed"})

_LOCKS_GUARD = threading.Lock()
_VAULT_LOCKS: dict[str, threading.Lock] = {}


def _vault_lock(vault_root: Path) -> threading.Lock:
    """Return the process-wide lock for one Vault so writes to it run one at a time."""
    with _LOCKS_GUARD:
        return _VAULT_LOCKS.setdefault(str(vault_root), threading.Lock())


class InferredProposalBudget:
    """Count the inferred proposals of the current cleanup, thread safe.

    A proposal takes a place before it is sent and gives it back when the Vault did not queue it.
    """

    def __init__(self, limit: int = INFERRED_PROPOSAL_LIMIT) -> None:
        self._limit = limit
        self._used = 0
        self._lock = threading.Lock()

    def start_curation(self) -> None:
        with self._lock:
            self._used = 0

    def take(self) -> bool:
        with self._lock:
            if self._used >= self._limit:
                return False
            self._used += 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self._used = max(0, self._used - 1)


class MemoryWriteService:
    def __init__(
        self,
        *,
        vault_map: VaultMapReader | None,
        writer: VaultWriter,
        page_reader: VaultPageReader,
        drafts: DraftFiles,
        today: Callable[[], date] = date.today,
        timeout_s: float = PUBLISH_TIMEOUT_SECONDS,
        vault_map_problem: str | None = None,
        importer: VaultImporter | None = None,
        reviewed_log: ReviewedLog | None = None,
        proposal_budget: InferredProposalBudget | None = None,
    ) -> None:
        self._vault_map = vault_map
        self._writer = writer
        self._page_reader = page_reader
        self._today = today
        self._drafts = drafts
        self._timeout_s = timeout_s
        self._vault_map_problem = vault_map_problem
        self._importer = importer
        self._reviewed_log = reviewed_log
        # Composition passes one budget per server process (spec §6 "한 정리"). Without it the limit counts
        # this service's proposals only.
        self._proposal_budget = proposal_budget if proposal_budget is not None else InferredProposalBudget()

    def start_curation(self) -> None:
        """Start a new cleanup: the inferred proposal count goes back to zero."""
        self._proposal_budget.start_curation()

    def remember(self, request: RememberRequest) -> MemoryWriteResult:
        refused = _refuse_input(validate_remember(request), request.vault)
        if refused is not None:
            return refused
        if self._vault_map is None:
            return self._no_vault_map()
        chosen = choose_write_vault(request.vault, _cwd(request.cwd), self._vault_map)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)
        if request.kind == PROJECT_KIND and request.vault is not None:
            # A project brief lives only in the project's default write Vault; recall reads it there
            # (spec 2026-11-05 §4.4.7, §6 "brief 페이지가 두 Vault에 있음").
            default = choose_write_vault(None, _cwd(request.cwd), self._vault_map)
            if not isinstance(default, MappedVault) or default.name != chosen.name:
                return _result(
                    chosen,
                    WriteOutcome(
                        "rejected",
                        messages=(
                            "A project brief is written to the project's default write Vault only. Leave vault empty.",
                        ),
                    ),
                )

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
        return self._recorded(_result(chosen, outcome), request.candidate_key)

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
        return self._recorded(_result(chosen, outcome), request.candidate_key)

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
        return self._recorded(_result(chosen, outcome), request.candidate_key)

    def supersede_claim(self, request: SupersedeClaimRequest) -> MemoryWriteResult:
        """Replace one claim row with a ``patch-page`` ``supersede-claim`` edit. The Vault checks the row."""
        refused = _refuse_input(validate_supersede_claim(request), request.vault)
        if refused is not None:
            return refused
        chosen = self._page_vault(request.vault, request.cwd, request.path)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)

        with _vault_lock(chosen.path):
            if self._page_reader.read(chosen.path, request.path) is None:
                return _result(chosen, WriteOutcome("rejected", messages=(f"No page at {request.path}.",)))
            outcome = self._send(
                chosen.path,
                build_supersede_claim_draft(request),
                request.basis,
                f"Supersede claim in {request.path}: {request.claim.strip()}",
            )
        if outcome.status == "rejected" and PROPOSAL_LIMIT_MESSAGE not in outcome.messages:
            outcome = replace(outcome, messages=(*outcome.messages, SUPERSEDE_REJECTED_HINT))
        return self._recorded(_result(chosen, outcome), request.candidate_key)

    def restore(self, request: RestoreRequest) -> MemoryWriteResult:
        """Make a retired page current again. A page that is not retired is refused before the Vault runs."""
        refused = _refuse_input(validate_restore(request), request.vault)
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
                draft = build_restore_draft(request, current, today=self._today())
            except ValueError as exc:
                return _result(chosen, WriteOutcome("rejected", messages=(str(exc),)))

            def unchanged() -> bool:
                again = self._page_reader.read(chosen.path, request.path)
                return again is not None and again.sha256 == current.sha256

            outcome = self._send(
                chosen.path,
                draft,
                request.basis,
                f"Restore memory {request.path}: {request.reason.strip()}",
                before_send=unchanged,
            )
        return self._recorded(_result(chosen, outcome), request.candidate_key)

    def import_auto_memory(self, request: ImportRequest) -> MemoryWriteResult:
        """Have the chosen Vault keep a copy of one auto-memory note (path 4). vault-graph copies nothing."""
        refused = _refuse_input(validate_import(request), request.vault)
        if refused is not None:
            return refused
        if self._vault_map is None:
            return self._no_vault_map()
        chosen = choose_write_vault(request.vault, _cwd(request.cwd), self._vault_map)
        if not isinstance(chosen, MappedVault):
            return _choice_result(chosen)
        if self._importer is None:
            return _result(chosen, WriteOutcome("error", messages=(NO_IMPORTER_MESSAGE,)))

        with _vault_lock(chosen.path):
            try:
                outcome = self._importer.import_source(
                    chosen.path, Path(request.note.strip()), timeout_s=self._timeout_s
                )
            except Exception as exc:  # noqa: BLE001 - any importer failure is reported, never retried.
                outcome = WriteOutcome("error", messages=(f"import-source could not run: {exc}",))
        return self._recorded(_result(chosen, outcome), request.candidate_key)

    def _recorded(self, result: MemoryWriteResult, candidate_key: str | None) -> MemoryWriteResult:
        """Record ``candidate_key`` for a published or proposed result. A failed record keeps the result."""
        if candidate_key is None or result.status not in RECORDED_OUTCOMES:
            return result
        key = candidate_key.strip()
        if self._reviewed_log is None:
            return replace(
                result,
                messages=(*result.messages, f"Candidate {key} was not recorded as processed: no review log is set."),
            )
        try:
            self._reviewed_log.append([key], outcome=result.status)
        except (OSError, ValueError) as exc:
            return replace(
                result,
                messages=(*result.messages, f"Candidate {key} was not recorded as processed: {exc}"),
            )
        return result

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
        """Publish a stated draft or propose an inferred one. Both read the file ``DraftFiles`` staged."""
        with self._drafts.stage(draft) as draft_path:
            if before_send is not None and not before_send():
                return WriteOutcome("rejected", messages=(PAGE_CHANGED_MESSAGE,))
            if basis == "inferred":
                return self._propose(vault_root, draft_path, summary)
            try:
                return self._writer.publish(vault_root, draft_path, timeout_s=self._timeout_s)
            except Exception as exc:  # noqa: BLE001 - any writer failure is reported, never retried.
                return WriteOutcome("error", messages=(f"publish-draft could not run: {exc}",))

    def _propose(self, vault_root: Path, draft_path: Path, summary: str) -> WriteOutcome:
        """Send an inferred draft to the review queue when the cleanup still has room for one more proposal."""
        if not self._proposal_budget.take():
            return WriteOutcome("rejected", messages=(PROPOSAL_LIMIT_MESSAGE,))
        try:
            outcome = self._writer.propose(vault_root, draft_path, summary=summary, timeout_s=self._timeout_s)
        except Exception as exc:  # noqa: BLE001 - any writer failure is reported, never retried.
            outcome = WriteOutcome("error", messages=(f"review propose could not run: {exc}",))
        if outcome.status != "proposed":
            self._proposal_budget.give_back()
        return outcome


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
        raw_path=outcome.raw_path,
        source_page=outcome.source_page,
    )


__all__ = [
    "INFERRED_PROPOSAL_LIMIT",
    "NEXT_INDEX_MESSAGE",
    "NO_IMPORTER_MESSAGE",
    "PAGE_CHANGED_MESSAGE",
    "PROPOSAL_LIMIT_MESSAGE",
    "PROPOSED_MESSAGE",
    "PUBLISH_TIMEOUT_SECONDS",
    "SUPERSEDE_REJECTED_HINT",
    "InferredProposalBudget",
    "MemoryWriteService",
    "approval_command",
]
