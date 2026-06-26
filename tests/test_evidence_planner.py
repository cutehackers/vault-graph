from __future__ import annotations

from dataclasses import replace

from tests.test_mcp_tool_serialization import make_search_response
from tests.test_mcp_tools import make_decision_trace_response
from vault_graph.answer.answer_plan import AnswerRequest
from vault_graph.answer.evidence_planner import EvidencePlanner
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse
from vault_graph.retrieval.search_response import SearchResponse, SearchWarning


class RecordingRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> SearchResponse:
        self.calls.append(kwargs)
        return self.response


class RecordingGraphService:
    def __init__(self, response: DecisionTraceResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def decision_trace(self, **kwargs: object) -> DecisionTraceResponse:
        self.calls.append(kwargs)
        return self.response


def request(*, max_evidence_tokens: int = 8000) -> AnswerRequest:
    return AnswerRequest(
        question="Why GraphRAG?",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        max_evidence_tokens=max_evidence_tokens,
    )


def test_planner_always_plans_required_search_step() -> None:
    planner = EvidencePlanner(retrieval_service=RecordingRetrievalService(make_search_response()))

    plan = planner.plan(request())

    assert plan.steps[0].kind == "search"
    assert plan.steps[0].required is True
    assert plan.steps[0].query == "Why GraphRAG?"


def test_gather_calls_retrieval_service_with_json_output() -> None:
    retrieval = RecordingRetrievalService(make_search_response())
    planner = EvidencePlanner(retrieval_service=retrieval)

    planned = planner.gather(planner.plan(request()))

    assert retrieval.calls[0]["output_format"] == "json"
    assert retrieval.calls[0]["query_text"] == "Why GraphRAG?"
    assert planned.actual_scopes == make_search_response().actual_scopes


def test_search_result_maps_to_answer_evidence() -> None:
    planner = EvidencePlanner(retrieval_service=RecordingRetrievalService(make_search_response(path="wiki/page.md")))

    planned = planner.gather(planner.plan(request()))

    evidence = planned.evidence[0]
    assert evidence.source_kind == "search_result"
    assert evidence.vault_id == "main"
    assert evidence.path == "wiki/page.md"
    assert evidence.excerpt == "Body"
    assert evidence.retrieval_reason == "keyword"
    assert evidence.signals[0].kind == "keyword"
    assert planned.reasoning_trace[0].kept_evidence_ids == (evidence.evidence_id,)


def test_search_warnings_map_to_answer_warnings() -> None:
    response = replace(
        make_search_response(),
        warnings=(
            SearchWarning(
                code="vector_unavailable",
                message="Vector backend unavailable.",
                severity="warning",
                affected_vault_ids=("main",),
            ),
        ),
        degraded=True,
    )
    planner = EvidencePlanner(retrieval_service=RecordingRetrievalService(response))

    planned = planner.gather(planner.plan(request()))

    assert planned.warnings[0].code == "vector_unavailable"
    assert planned.warnings[0].severity == "warning"
    assert planned.reasoning_trace[0].warning_codes == ("vector_unavailable",)


def test_missing_search_evidence_returns_insufficient_evidence_warning() -> None:
    response = replace(make_search_response(), results=(), result_count=0, candidate_count=0)
    planner = EvidencePlanner(retrieval_service=RecordingRetrievalService(response))

    planned = planner.gather(planner.plan(request()))

    assert planned.evidence == ()
    assert planned.warnings[0].code == "insufficient_evidence"


def test_evidence_budget_drops_lower_ranked_evidence_with_warning() -> None:
    response = make_search_response()
    first_result = replace(response.results[0], summary=" ".join(["first"] * 900))
    second_result = replace(
        response.results[0],
        result_id="main:chunk-2",
        rank=2,
        summary=" ".join(["second"] * 900),
        evidence=(replace(response.results[0].evidence[0], chunk_id="chunk-2"),),
    )
    response = replace(response, results=(first_result, second_result), result_count=2, candidate_count=2)
    planner = EvidencePlanner(retrieval_service=RecordingRetrievalService(response))

    planned = planner.gather(planner.plan(request(max_evidence_tokens=1000)))

    assert len(planned.evidence) == 1
    assert planned.dropped_evidence_count == 1
    assert any(warning.code == "evidence_budget_exhausted" for warning in planned.warnings)


def test_include_graph_gathers_decision_trace_evidence_for_decision_question() -> None:
    retrieval = RecordingRetrievalService(make_search_response())
    graph = RecordingGraphService(make_decision_trace_response())
    planner = EvidencePlanner(retrieval_service=retrieval, graph_service=graph)
    graph_request = AnswerRequest(
        question="Why was Phase 5 decision adopted?",
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        include_graph=True,
    )

    planned = planner.gather(planner.plan(graph_request))

    assert graph.calls[0]["output_format"] == "json"
    assert any(evidence.source_kind == "decision_trace" for evidence in planned.evidence)
    assert any(step.kind == "decision_trace" for step in planned.reasoning_trace)
