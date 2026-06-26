from __future__ import annotations

import hashlib
from typing import Protocol

from vault_graph.answer.answer_plan import AnswerPlan, AnswerRequest, EvidencePlanStep, PlannedEvidence
from vault_graph.answer.answer_response import (
    AnswerEvidence,
    AnswerReasoningStep,
    AnswerSignal,
    AnswerStoreRevision,
    AnswerWarning,
)
from vault_graph.errors import AnswerError
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse, GraphOutputFormat
from vault_graph.retrieval.search_response import SearchOutputFormat, SearchResponse

_DECISION_TERMS = (
    "why",
    "decision",
    "tradeoff",
    "trade-off",
    "choose",
    "chosen",
    "adopt",
    "adopted",
    "revisit",
    "because",
)


class AnswerRetrievalService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "text",
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> SearchResponse: ...


class AnswerGraphService(Protocol):
    def decision_trace(
        self,
        *,
        topic: str,
        requested_scope: QueryScope,
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "text",
    ) -> DecisionTraceResponse: ...


class AnswerProjectMemoryService(Protocol):
    def summarize(self, *, requested_scope: QueryScope, limit: int = 10) -> object: ...


class AnswerOpenQuestionsService(Protocol):
    def open_questions(self, *, requested_scope: QueryScope, limit: int = 20) -> object: ...


class EvidencePlanner:
    def __init__(
        self,
        *,
        retrieval_service: AnswerRetrievalService,
        graph_service: AnswerGraphService | None = None,
        project_memory_service: AnswerProjectMemoryService | None = None,
        open_questions_service: AnswerOpenQuestionsService | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._graph_service = graph_service
        self._project_memory_service = project_memory_service
        self._open_questions_service = open_questions_service

    def plan(self, request: AnswerRequest) -> AnswerPlan:
        steps = [
            EvidencePlanStep(
                step_id="search:1",
                kind="search",
                query=request.question.strip(),
                required=True,
                include_graph=request.include_graph,
                include_cross_vault=request.include_cross_vault,
                limit=request.retrieval_limit,
            )
        ]
        if request.include_graph and self._graph_service is not None and _is_decision_oriented(request.question):
            steps.append(
                EvidencePlanStep(
                    step_id="decision_trace:1",
                    kind="decision_trace",
                    query=request.question.strip(),
                    required=False,
                    include_graph=True,
                    include_cross_vault=request.include_cross_vault,
                    limit=min(request.retrieval_limit, 10),
                )
            )
        if self._project_memory_service is not None:
            steps.append(
                EvidencePlanStep(
                    step_id="project_memory:1",
                    kind="project_memory",
                    query=request.question.strip(),
                    required=False,
                    limit=min(request.retrieval_limit, 10),
                )
            )
        if self._open_questions_service is not None:
            steps.append(
                EvidencePlanStep(
                    step_id="open_question:1",
                    kind="open_question",
                    query=request.question.strip(),
                    required=False,
                    limit=min(request.retrieval_limit, 20),
                )
            )
        return AnswerPlan(request=request, steps=tuple(steps))

    def gather(self, plan: AnswerPlan) -> PlannedEvidence:
        evidence: list[AnswerEvidence] = []
        warnings: list[AnswerWarning] = []
        reasoning_trace: list[AnswerReasoningStep] = []
        actual_scopes: tuple[QueryScope, ...] | None = None
        dropped_evidence_count = 0
        for step in plan.steps:
            if step.kind == "search":
                search_response = self._retrieval_service.search(
                    query_text=step.query,
                    requested_scope=plan.request.requested_scope,
                    limit=step.limit,
                    output_format="json",
                    include_graph=step.include_graph,
                    include_cross_vault=step.include_cross_vault,
                )
                actual_scopes = search_response.actual_scopes
                mapped_warnings = tuple(
                    AnswerWarning(
                        code=warning.code,
                        message=warning.message,
                        severity=warning.severity,
                        affected_vault_ids=warning.affected_vault_ids,
                        recovery_hint=None,
                    )
                    for warning in search_response.warnings
                )
                warnings.extend(mapped_warnings)
                mapped = _evidence_from_search_response(search_response, start_rank=len(evidence) + 1)
                evidence.extend(mapped)
                reasoning_trace.append(
                    AnswerReasoningStep(
                        step_id=step.step_id,
                        kind="search",
                        service="RetrievalService.search",
                        status="warning" if mapped_warnings else "ok",
                        query=step.query,
                        result_count=search_response.result_count,
                        kept_evidence_ids=tuple(item.evidence_id for item in mapped),
                        dropped_count=search_response.dropped_candidate_count,
                        warning_codes=tuple(warning.code for warning in mapped_warnings),
                    )
                )
            elif step.kind == "decision_trace" and self._graph_service is not None:
                trace_response = self._graph_service.decision_trace(
                    topic=step.query,
                    requested_scope=plan.request.requested_scope,
                    include_cross_vault=step.include_cross_vault,
                    limit=step.limit,
                    output_format="json",
                )
                actual_scopes = actual_scopes or trace_response.actual_scopes
                mapped_warnings = tuple(
                    AnswerWarning(
                        code=warning.code,
                        message=warning.message,
                        severity=warning.severity,
                        affected_vault_ids=warning.affected_vault_ids,
                        recovery_hint=None,
                    )
                    for warning in trace_response.warnings
                )
                warnings.extend(mapped_warnings)
                mapped = _evidence_from_decision_trace_response(trace_response, start_rank=len(evidence) + 1)
                evidence.extend(mapped)
                reasoning_trace.append(
                    AnswerReasoningStep(
                        step_id=step.step_id,
                        kind="decision_trace",
                        service="GraphRetrievalService.decision_trace",
                        status="warning" if mapped_warnings else "ok",
                        query=step.query,
                        result_count=len(trace_response.steps),
                        kept_evidence_ids=tuple(item.evidence_id for item in mapped),
                        dropped_count=0,
                        warning_codes=tuple(warning.code for warning in mapped_warnings),
                    )
                )
            elif step.kind == "project_memory" and self._project_memory_service is not None:
                projection = self._project_memory_service.summarize(
                    requested_scope=plan.request.requested_scope,
                    limit=step.limit,
                )
                reasoning_trace.append(
                    AnswerReasoningStep(
                        step_id=step.step_id,
                        kind="project_memory",
                        service="ProjectMemoryService.summarize",
                        status="ok",
                        query=step.query,
                        result_count=_projection_result_count(projection),
                        kept_evidence_ids=(),
                        dropped_count=0,
                        warning_codes=(),
                    )
                )
            elif step.kind == "open_question" and self._open_questions_service is not None:
                projection = self._open_questions_service.open_questions(
                    requested_scope=plan.request.requested_scope,
                    limit=step.limit,
                )
                reasoning_trace.append(
                    AnswerReasoningStep(
                        step_id=step.step_id,
                        kind="open_question",
                        service="IssueMemoryService.open_questions",
                        status="ok",
                        query=step.query,
                        result_count=_projection_result_count(projection),
                        kept_evidence_ids=(),
                        dropped_count=0,
                        warning_codes=(),
                    )
                )

        if actual_scopes is None:
            actual_scopes = (plan.request.requested_scope,)
        deduped = _dedupe_evidence(tuple(evidence))
        budgeted, budget_dropped = _enforce_budget(deduped, max_tokens=plan.request.max_evidence_tokens)
        dropped_evidence_count += budget_dropped
        if budget_dropped:
            warnings.append(
                AnswerWarning(
                    code="evidence_budget_exhausted",
                    message="Evidence exceeded the answer evidence budget.",
                    severity="warning",
                    affected_vault_ids=plan.request.requested_scope.vault_ids,
                    recovery_hint="Increase --max-evidence-tokens or ask a narrower question.",
                )
            )
        if not budgeted:
            warnings.append(
                AnswerWarning(
                    code="insufficient_evidence",
                    message="No indexed evidence matched the question.",
                    severity="warning",
                    affected_vault_ids=plan.request.requested_scope.vault_ids,
                    recovery_hint="Run vg index for the selected Vault, then retry the question.",
                )
            )
        kept_ids = {item.evidence_id for item in budgeted}
        reasoning_trace = [
            _filter_reasoning_step_evidence_ids(step, kept_ids=kept_ids, budget_dropped=budget_dropped)
            for step in reasoning_trace
        ]
        return PlannedEvidence(
            plan=plan,
            actual_scopes=actual_scopes,
            evidence=budgeted,
            reasoning_trace=tuple(reasoning_trace),
            warnings=tuple(warnings),
            dropped_evidence_count=dropped_evidence_count,
        )


def _evidence_from_search_response(response: SearchResponse, *, start_rank: int) -> tuple[AnswerEvidence, ...]:
    evidence_items: list[AnswerEvidence] = []
    rank = start_rank
    for result in response.results:
        for evidence_ref in result.evidence:
            evidence_id = _evidence_id(
                rank=rank,
                vault_id=evidence_ref.vault_id,
                document_id=evidence_ref.document_id,
                chunk_id=evidence_ref.chunk_id,
                source_kind="search_result",
            )
            signal_kinds = tuple(dict.fromkeys(signal.kind for signal in result.signals))
            evidence_items.append(
                AnswerEvidence(
                    evidence_id=evidence_id,
                    source_kind="search_result",
                    result_id=result.result_id,
                    vault_id=evidence_ref.vault_id,
                    document_id=evidence_ref.document_id,
                    chunk_id=evidence_ref.chunk_id,
                    path=evidence_ref.path,
                    section=evidence_ref.section,
                    anchor=evidence_ref.anchor,
                    content_hash=evidence_ref.content_hash,
                    raw_sha256=evidence_ref.raw_sha256,
                    metadata_index_revision=evidence_ref.metadata_index_revision,
                    vault_revision=evidence_ref.vault_revision,
                    excerpt=result.summary,
                    retrieval_reason=",".join(signal_kinds) if signal_kinds else "search",
                    relationship_status=result.relationship_status,
                    signals=tuple(
                        AnswerSignal(
                            kind=signal.kind,
                            rank=signal.rank,
                            score=signal.score,
                            backend=signal.backend,
                            index_revision=signal.index_revision,
                            explanation=signal.explanation,
                        )
                        for signal in result.signals
                    ),
                    store_revisions=tuple(
                        _store_revision_from_any(revision, default_vault_id=evidence_ref.vault_id)
                        for revision in (*response.store_revisions, *result.store_revisions)
                    ),
                )
            )
            rank += 1
    return tuple(evidence_items)


def _evidence_from_decision_trace_response(
    response: DecisionTraceResponse,
    *,
    start_rank: int,
) -> tuple[AnswerEvidence, ...]:
    evidence_items: list[AnswerEvidence] = []
    rank = start_rank
    for step in response.steps:
        for evidence_ref in step.evidence:
            evidence_id = _evidence_id(
                rank=rank,
                vault_id=evidence_ref.vault_id,
                document_id=evidence_ref.document_id,
                chunk_id=evidence_ref.chunk_id,
                source_kind="decision_trace",
            )
            evidence_items.append(
                AnswerEvidence(
                    evidence_id=evidence_id,
                    source_kind="decision_trace",
                    result_id=f"decision_trace:{response.topic}:{step.rank}",
                    vault_id=evidence_ref.vault_id,
                    document_id=evidence_ref.document_id,
                    chunk_id=evidence_ref.chunk_id,
                    path=evidence_ref.path,
                    section=evidence_ref.section,
                    anchor=evidence_ref.anchor,
                    content_hash=evidence_ref.content_hash,
                    raw_sha256=evidence_ref.raw_sha256,
                    metadata_index_revision=evidence_ref.metadata_index_revision,
                    vault_revision=evidence_ref.vault_revision,
                    excerpt=step.explanation,
                    retrieval_reason=f"decision_trace:{step.role}",
                    relationship_status=step.relationship_status,
                    signals=(
                        AnswerSignal(
                            kind="graph",
                            rank=step.rank,
                            score=1.0,
                            backend="graph",
                            index_revision=response.projection_build_id or response.graph_projection_version,
                            explanation=step.explanation,
                        ),
                    ),
                    store_revisions=tuple(
                        _store_revision_from_any(
                            revision,
                            default_kind="graph",
                            default_revision=response.graph_projection_version,
                            default_scope_key="graph",
                            default_vault_id=evidence_ref.vault_id,
                        )
                        for revision in response.store_revisions
                    ),
                )
            )
            rank += 1
    return tuple(evidence_items)


def _filter_reasoning_step_evidence_ids(
    step: AnswerReasoningStep,
    *,
    kept_ids: set[str],
    budget_dropped: int,
) -> AnswerReasoningStep:
    from dataclasses import replace

    return replace(
        step,
        kept_evidence_ids=tuple(evidence_id for evidence_id in step.kept_evidence_ids if evidence_id in kept_ids),
        dropped_count=step.dropped_count + budget_dropped,
    )


def _dedupe_evidence(evidence: tuple[AnswerEvidence, ...]) -> tuple[AnswerEvidence, ...]:
    seen: set[tuple[str, str, str, str]] = set()
    kept: list[AnswerEvidence] = []
    for item in evidence:
        key = (item.vault_id, item.document_id, item.chunk_id, item.source_kind)
        if key in seen:
            continue
        seen.add(key)
        kept.append(item)
    return tuple(kept)


def _enforce_budget(evidence: tuple[AnswerEvidence, ...], *, max_tokens: int) -> tuple[tuple[AnswerEvidence, ...], int]:
    kept: list[AnswerEvidence] = []
    used = 0
    dropped = 0
    for item in evidence:
        token_count = max(1, len(item.excerpt.split()))
        if used + token_count > max_tokens:
            dropped += 1
            continue
        used += token_count
        kept.append(item)
    return tuple(kept), dropped


def _projection_result_count(projection: object) -> int:
    vaults = getattr(projection, "vaults", ())
    if isinstance(vaults, tuple | list):
        return len(vaults)
    return 0


def _store_revision_from_any(
    revision: object,
    *,
    default_vault_id: str,
    default_kind: str | None = None,
    default_revision: str | None = None,
    default_scope_key: str | None = None,
) -> AnswerStoreRevision:
    kind = _string_attr(revision, "kind", fallback=default_kind)
    revision_value = _string_attr(revision, "revision", fallback=default_revision)
    return AnswerStoreRevision(
        kind=kind,
        revision=revision_value,
        scope_key=_string_attr(revision, "scope_key", fallback=default_scope_key or kind),
        vault_id=_string_attr(revision, "vault_id", fallback=default_vault_id),
    )


def _string_attr(value: object, name: str, *, fallback: str | None) -> str:
    raw = getattr(value, name, None)
    if isinstance(raw, str) and raw:
        return raw
    if fallback is not None:
        return fallback
    raise AnswerError(f"store revision missing {name}")


def _evidence_id(*, rank: int, vault_id: str, document_id: str, chunk_id: str, source_kind: str) -> str:
    digest = hashlib.sha256(f"{vault_id}:{document_id}:{chunk_id}:{source_kind}".encode()).hexdigest()
    return f"ev_{rank}_{digest[:12]}"


def _is_decision_oriented(question: str) -> bool:
    normalized = question.casefold()
    return any(term in normalized for term in _DECISION_TERMS)
