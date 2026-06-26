from __future__ import annotations

from typing import TYPE_CHECKING

from vault_graph.answer.answer_plan import AnswerRequest
from vault_graph.context.context_pack import ContextPackBudget, ContextPackRequest
from vault_graph.http.http_errors import HttpRequestError, HttpServerConfig, map_exception_to_http_error
from vault_graph.http.http_explanation_serialization import (
    explanation_records_for_answer,
    explanation_records_for_context_pack,
    explanation_records_for_decision_trace,
    explanation_records_for_related,
    explanation_records_for_search,
)
from vault_graph.http.http_serialization import domain_to_json_dict
from vault_graph.http.http_service_factory import HttpServiceFactory
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.memory.result_explanation import ExplainResultService, explanation_record_to_dict
from vault_graph.memory.result_explanation_cache import ResultExplanationCache

if TYPE_CHECKING:
    from fastapi import FastAPI


def create_http_app(
    config: HttpServerConfig,
    *,
    service_factory: HttpServiceFactory | None = None,
    result_explanation_cache: ResultExplanationCache | None = None,
) -> FastAPI:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Vault Graph", version="0.1.0")
    services_factory = service_factory or HttpServiceFactory(state_path=config.state_path)
    explanation_cache = result_explanation_cache or ResultExplanationCache(max_entries=256)
    explain_result_service = ExplainResultService(cache=explanation_cache)

    @app.exception_handler(Exception)
    async def handle_exception(_request: Request, exc: Exception) -> JSONResponse:
        error = map_exception_to_http_error(exc)
        return JSONResponse(status_code=error.status_code, content=error.payload.to_json_dict())

    @app.get("/health")
    def health() -> dict[str, object]:
        services_factory.open_read_only()
        return {"ok": True, "service": "vault-graph", "transport": "http"}

    @app.get("/status")
    def status() -> dict[str, object]:
        services = services_factory.open_read_only()
        report = services_factory.open_status_service().status(scope=services.catalog.default_scope())
        return domain_to_json_dict(report)

    @app.post("/search")
    def search(payload: dict[str, object]) -> dict[str, object]:
        query = _required_string(payload.get("query"), "query")
        include_graph = _bool(payload.get("include_graph"), default=False)
        include_cross_vault = _bool(payload.get("include_cross_vault"), default=False)
        services = services_factory.open_read_only()
        scope = _scope_from_payload(
            payload.get("scope"),
            catalog=services.catalog,
            include_cross_vault=include_cross_vault,
            allow_cross_vault=include_graph,
        )
        response = services_factory.open_retrieval_service(include_graph=include_graph).search(
            query_text=query,
            requested_scope=scope,
            limit=_limit(payload.get("limit"), default=10),
            output_format="json",
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
        )
        explanation_cache.put_many(explanation_records_for_search(response))
        return domain_to_json_dict(response)

    @app.post("/context")
    def context(payload: dict[str, object]) -> dict[str, object]:
        goal = _required_string(payload.get("goal"), "goal")
        include_graph = _bool(payload.get("include_graph"), default=False)
        include_cross_vault = _bool(payload.get("include_cross_vault"), default=False)
        services = services_factory.open_read_only()
        scope = _scope_from_payload(
            payload.get("scope"),
            catalog=services.catalog,
            include_cross_vault=include_cross_vault,
            allow_cross_vault=include_graph,
        )
        request = ContextPackRequest(
            goal=goal,
            requested_scope=scope,
            budget=ContextPackBudget(max_tokens=_positive_int(payload.get("max_tokens"), default=8000)),
            retrieval_limit=_limit(payload.get("limit"), default=10),
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
        )
        pack = services_factory.open_context_pack_builder(include_graph=include_graph).build(request)
        explanation_cache.put_many(explanation_records_for_context_pack(pack))
        return domain_to_json_dict(pack)

    @app.post("/ask")
    def ask(payload: dict[str, object]) -> dict[str, object]:
        question = _required_string(payload.get("question"), "question")
        include_graph = _bool(payload.get("include_graph"), default=False)
        include_cross_vault = _bool(payload.get("include_cross_vault"), default=False)
        services = services_factory.open_read_only()
        scope = _scope_from_payload(
            payload.get("scope"),
            catalog=services.catalog,
            include_cross_vault=include_cross_vault,
            allow_cross_vault=include_graph,
        )
        response = services_factory.open_answer_service(include_graph=include_graph).ask(
            AnswerRequest(
                question=question,
                requested_scope=scope,
                retrieval_limit=_limit(payload.get("limit"), default=10),
                max_evidence_tokens=_positive_int(payload.get("max_evidence_tokens"), default=8000),
                include_graph=include_graph,
                include_cross_vault=include_cross_vault,
            )
        )
        explanation_cache.put_many(explanation_records_for_answer(response))
        return domain_to_json_dict(response)

    @app.post("/related")
    def related(payload: dict[str, object]) -> dict[str, object]:
        target = _required_string(payload.get("target"), "target")
        include_cross_vault = _bool(payload.get("include_cross_vault"), default=False)
        services = services_factory.open_read_only()
        scope = _scope_from_payload(
            payload.get("scope"),
            catalog=services.catalog,
            include_cross_vault=include_cross_vault,
            allow_cross_vault=True,
        )
        response = services_factory.open_graph_retrieval_service().related(
            target=target,
            requested_scope=scope,
            depth=_positive_int(payload.get("depth"), default=1),
            relationship_types=tuple(_string_list(payload.get("relationship_types"))),
            include_cross_vault=include_cross_vault,
            limit=_limit(payload.get("limit"), default=10),
            output_format="json",
        )
        explanation_cache.put_many(explanation_records_for_related(response))
        return domain_to_json_dict(response)

    @app.post("/decision-trace")
    def decision_trace(payload: dict[str, object]) -> dict[str, object]:
        topic = _required_string(payload.get("decision_or_topic"), "decision_or_topic")
        include_cross_vault = _bool(payload.get("include_cross_vault"), default=False)
        services = services_factory.open_read_only()
        scope = _scope_from_payload(
            payload.get("scope"),
            catalog=services.catalog,
            include_cross_vault=include_cross_vault,
            allow_cross_vault=True,
        )
        response = services_factory.open_graph_retrieval_service().decision_trace(
            topic=topic,
            requested_scope=scope,
            include_cross_vault=include_cross_vault,
            limit=_limit(payload.get("limit"), default=10),
            output_format="json",
        )
        explanation_cache.put_many(explanation_records_for_decision_trace(response))
        return domain_to_json_dict(response)

    @app.get("/memory/project")
    def project_memory(limit: int = 10) -> dict[str, object]:
        services = services_factory.open_read_only()
        projection = services_factory.open_project_memory_service().summarize(
            requested_scope=services.catalog.default_scope(),
            limit=_limit(limit, default=10),
        )
        return domain_to_json_dict(projection)

    @app.get("/memory/open-questions")
    def open_questions(limit: int = 20) -> dict[str, object]:
        services = services_factory.open_read_only()
        projection = services_factory.open_issue_memory_service().open_questions(
            requested_scope=services.catalog.default_scope(),
            limit=_limit(limit, default=20),
        )
        return domain_to_json_dict(projection)

    @app.get("/memory/recent-changes")
    def recent_changes(since: str | None = None, limit: int = 20) -> dict[str, object]:
        services = services_factory.open_read_only()
        projection = services_factory.open_timeline_memory_service().recent_changes(
            requested_scope=services.catalog.default_scope(),
            since=since,
            limit=_limit(limit, default=20),
        )
        return domain_to_json_dict(projection)

    @app.post("/explain-result")
    def explain_result(payload: dict[str, object]) -> dict[str, object]:
        result_id = _result_id(payload.get("result_id"))
        return explanation_record_to_dict(explain_result_service.explain(result_id=result_id))

    return app


def run_http_server(config: HttpServerConfig) -> None:
    import uvicorn

    uvicorn.run(create_http_app(config), host=config.host, port=config.port)


def _scope_from_payload(
    value: object,
    *,
    catalog: VaultCatalog,
    include_cross_vault: bool,
    allow_cross_vault: bool,
) -> QueryScope:
    if include_cross_vault and not allow_cross_vault:
        raise HttpRequestError(code="invalid_scope", message="include_cross_vault requires graph-enabled route")
    if value is None:
        base = catalog.default_scope()
    elif not isinstance(value, dict):
        raise HttpRequestError(code="invalid_scope", message="scope must be an object")
    else:
        all_vaults = _bool(value.get("all_vaults"), default=False)
        vault_ids = _string_list(value.get("vault_ids"))
        if all_vaults and vault_ids:
            raise HttpRequestError(code="invalid_scope", message="Use either all_vaults or vault_ids, not both.")
        if all_vaults:
            base = catalog.scope_for_all_enabled()
        elif vault_ids:
            base = catalog.scope_for_vault_ids(vault_ids)
        else:
            base = catalog.default_scope()
    if include_cross_vault:
        return QueryScope(
            vault_ids=base.vault_ids,
            content_scopes=base.content_scopes,
            include_cross_vault=True,
        )
    return base


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HttpRequestError(code="invalid_request", message=f"{field_name} is required")
    return value.strip()


def _result_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HttpRequestError(
            code="invalid_result_id",
            message="result_id is required",
            status_code=400,
            recovery_hint="Pass a non-empty result_id from a current Vault Graph response.",
        )
    return value.strip()


def _bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise HttpRequestError(code="invalid_request", message="boolean field has invalid value")
    return value


def _limit(value: object, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 50:
        raise HttpRequestError(code="invalid_request", message="limit must be between 1 and 50")
    return value


def _positive_int(value: object, *, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise HttpRequestError(code="invalid_request", message="positive integer field has invalid value")
    return value


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise HttpRequestError(code="invalid_request", message="expected a list of strings")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HttpRequestError(code="invalid_request", message="expected a list of strings")
        strings.append(item.strip())
    return strings
