"""In-memory evidence selection for a context pack budget."""

from __future__ import annotations

from typing import Literal

from vault_graph.context.pack.context_pack import ContextEvidence, ContextEvidenceRef, ContextPackBudget

EvidenceRefAction = Literal["reused", "resolve", "omitted"]
ItemSelectionStatus = Literal["kept", "missing", "budget"]


class ContextEvidenceSelection:
    """Select whole result items while accounting for shared evidence once."""

    def __init__(self, budget: ContextPackBudget) -> None:
        self._budget = budget
        self.evidence_by_ref: dict[ContextEvidenceRef, ContextEvidence] = {}
        self.used_tokens = 0
        self.omitted_for_evidence_limit = 0
        self.omitted_for_token_limit = 0
        self.omitted_missing = 0
        self._pending_evidence: dict[ContextEvidenceRef, ContextEvidence] = {}
        self._kept_refs: list[ContextEvidenceRef] = []
        self._pending_tokens = 0
        self._omitted_by_budget = False

    def begin_item(self) -> None:
        self._pending_evidence = {}
        self._kept_refs = []
        self._pending_tokens = 0
        self._omitted_by_budget = False

    def check_ref(self, ref: ContextEvidenceRef) -> EvidenceRefAction:
        if ref in self.evidence_by_ref or ref in self._pending_evidence:
            self._kept_refs.append(ref)
            return "reused"
        if len(self.evidence_by_ref) + len(self._pending_evidence) >= self._budget.max_evidence_items:
            self.omitted_for_evidence_limit += 1
            self._omitted_by_budget = True
            return "omitted"
        return "resolve"

    def add_evidence(self, evidence: ContextEvidence) -> bool:
        if self.used_tokens + self._pending_tokens + evidence.excerpt_token_count > self._budget.max_tokens:
            self.omitted_for_token_limit += 1
            self._omitted_by_budget = True
            return False
        self._pending_evidence[evidence.ref] = evidence
        self._kept_refs.append(evidence.ref)
        self._pending_tokens += evidence.excerpt_token_count
        return True

    def finish_item(self) -> tuple[ItemSelectionStatus, tuple[ContextEvidenceRef, ...]]:
        if self._omitted_by_budget:
            return "budget", ()
        if not self._kept_refs:
            self.omitted_missing += 1
            return "missing", ()
        self.used_tokens += self._pending_tokens
        self.evidence_by_ref.update(self._pending_evidence)
        return "kept", tuple(self._kept_refs)

    @property
    def omitted_items(self) -> int:
        return self.omitted_for_evidence_limit + self.omitted_for_token_limit + self.omitted_missing
