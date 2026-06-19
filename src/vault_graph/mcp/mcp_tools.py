from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from vault_graph.context.context_pack import (
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    ContextPackBudget,
    ContextPackRequest,
)
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError, map_exception_to_mcp_error
from vault_graph.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices
from vault_graph.mcp.mcp_uri import encode_resource_segment
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.memory.result_explanation import ExplainResultService
from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_RELATED_DEPTH,
    DEFAULT_GRAPH_RESULT_LIMIT,
    MAX_GRAPH_PROJECTION_DEPTH,
)

McpToolName = Literal[
    "search_vault",
    "build_context_pack",
    "find_related",
    "get_decision_trace",
    "check_index_status",
    "explain_result",
]
MAX_MCP_TOOL_LIMIT = 50


class McpToolServer(Protocol):
    def tool(
        self,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        annotations: Any | None = None,
        icons: list[Any] | None = None,
        meta: dict[str, Any] | None = None,
        structured_output: bool | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        raise NotImplementedError


@dataclass(frozen=True)
class McpResourceLink:
    rel: str
    uri: str
    title: str | None = None
    vault_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "rel": self.rel,
            "uri": self.uri,
            "title": self.title,
            "vault_id": self.vault_id,
            "document_id": self.document_id,
            "chunk_id": self.chunk_id,
        }


@dataclass(frozen=True)
class McpToolBody:
    tool_name: McpToolName
    payload: dict[str, object]
    resource_links: tuple[McpResourceLink, ...]
    warnings: tuple[McpErrorPayload, ...]
    text: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "tool_name": self.tool_name,
            "payload": self.payload,
            "resource_links": [link.to_json_dict() for link in self.resource_links],
            "warnings": [_warning_to_dict(warning) for warning in self.warnings],
            "text": self.text,
        }


def _warning_to_dict(warning: McpErrorPayload) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }


@dataclass(frozen=True)
class SearchVaultInput:
    query: str
    scope: McpScopeInput | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False


@dataclass(frozen=True)
class BuildContextPackInput:
    goal: str
    scope: McpScopeInput | None = None
    max_tokens: int | None = None
    limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    include_graph: bool = False
    include_cross_vault: bool = False


@dataclass(frozen=True)
class FindRelatedInput:
    target: str
    scope: McpScopeInput | None = None
    depth: int = DEFAULT_GRAPH_RELATED_DEPTH
    kinds: tuple[str, ...] = ()
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False


@dataclass(frozen=True)
class DecisionTraceInput:
    decision_or_topic: str
    scope: McpScopeInput | None = None
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False


@dataclass(frozen=True)
class CheckIndexStatusInput:
    scope: McpScopeInput | None = None


@dataclass(frozen=True)
class ExplainResultInput:
    result_id: str


class McpToolRegistry:
    tool_names: tuple[McpToolName, ...]

    def __init__(
        self,
        *,
        services: McpServices,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
        result_explanation_cache: ResultExplanationCache,
    ) -> None:
        self._services = services
        self._service_factory = service_factory
        self._context_pack_cache = context_pack_cache
        self._result_explanation_cache = result_explanation_cache
        self._explain_result_service = ExplainResultService(cache=result_explanation_cache)
        self.tool_names = (
            "search_vault",
            "build_context_pack",
            "find_related",
            "get_decision_trace",
            "check_index_status",
            "explain_result",
        )

    def search_vault(self, request: SearchVaultInput) -> McpToolBody:
        try:
            _validate_search_vault_request(request)
            selected_scope = _scope_for_tool(
                request.scope,
                catalog=self._services.catalog,
                allow_graph_cross_vault=request.include_graph,
            )
            _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
            retrieval_service = (
                self._service_factory.open_retrieval_service(include_graph=True)
                if request.include_graph
                else self._services.retrieval_service
            )
            response = retrieval_service.search(
                query_text=request.query,
                requested_scope=selected_scope,
                limit=request.limit,
                output_format="json",
                include_graph=request.include_graph,
                include_cross_vault=request.include_cross_vault,
            )
            from vault_graph.mcp.mcp_tool_serialization import (
                explanation_records_for_search,
                mcp_warning_from_search,
                resource_links_for_search,
                search_response_to_payload,
            )

            records = explanation_records_for_search(response)
            body = _tool_body(
                tool_name="search_vault",
                payload=search_response_to_payload(response),
                resource_links=resource_links_for_search(response),
                warnings=tuple(mcp_warning_from_search(warning) for warning in response.warnings),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def build_context_pack(self, request: BuildContextPackInput) -> McpToolBody:
        try:
            _validate_build_context_pack_request(request)
            selected_scope = _scope_for_tool(
                request.scope,
                catalog=self._services.catalog,
                allow_graph_cross_vault=request.include_graph,
            )
            _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
            pack_request = ContextPackRequest(
                goal=request.goal,
                requested_scope=selected_scope,
                budget=ContextPackBudget(max_tokens=request.max_tokens or DEFAULT_CONTEXT_MAX_TOKENS),
                retrieval_limit=request.limit,
                include_graph=request.include_graph,
                include_cross_vault=request.include_cross_vault,
            )
            builder = (
                self._service_factory.open_context_pack_builder(include_graph=True)
                if request.include_graph
                else self._services.context_pack_builder
            )
            pack = builder.build(pack_request)
            rendered_json = self._services.context_pack_renderer.render_json(pack)
            self._context_pack_cache.put(pack, rendered_json=rendered_json)
            from vault_graph.mcp.mcp_tool_serialization import (
                context_pack_to_payload,
                explanation_records_for_context_pack,
                mcp_warning_from_context,
                resource_links_for_context_pack,
            )

            records = explanation_records_for_context_pack(pack)
            body = _tool_body(
                tool_name="build_context_pack",
                payload=context_pack_to_payload(pack),
                resource_links=(
                    McpResourceLink(
                        rel="context_pack",
                        uri=f"vault://context/packs/{encode_resource_segment(pack.pack_id)}",
                        title=pack.goal,
                    ),
                    *resource_links_for_context_pack(pack),
                ),
                warnings=tuple(mcp_warning_from_context(warning) for warning in pack.warnings),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def find_related(self, request: FindRelatedInput) -> McpToolBody:
        try:
            _validate_find_related_request(request)
            selected_scope = _scope_for_tool(
                request.scope,
                catalog=self._services.catalog,
                allow_graph_cross_vault=True,
            )
            _validate_graph_cross_vault_request(selected_scope, include_cross_vault=request.include_cross_vault)
            response = self._service_factory.open_graph_retrieval_service().related(
                target=request.target,
                requested_scope=selected_scope,
                depth=request.depth,
                relationship_types=request.kinds,
                include_cross_vault=request.include_cross_vault,
                limit=request.limit,
                output_format="json",
            )
            from vault_graph.mcp.mcp_tool_serialization import (
                explanation_records_for_related,
                mcp_warning_from_graph,
                related_response_to_payload,
                resource_links_for_related,
            )

            records = explanation_records_for_related(response)
            body = _tool_body(
                tool_name="find_related",
                payload=related_response_to_payload(response),
                resource_links=resource_links_for_related(response),
                warnings=tuple(mcp_warning_from_graph(warning) for warning in response.warnings),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def get_decision_trace(self, request: DecisionTraceInput) -> McpToolBody:
        try:
            _validate_decision_trace_request(request)
            selected_scope = _scope_for_tool(
                request.scope,
                catalog=self._services.catalog,
                allow_graph_cross_vault=True,
            )
            _validate_graph_cross_vault_request(selected_scope, include_cross_vault=request.include_cross_vault)
            response = self._service_factory.open_graph_retrieval_service().decision_trace(
                topic=request.decision_or_topic,
                requested_scope=selected_scope,
                include_cross_vault=request.include_cross_vault,
                limit=request.limit,
                output_format="json",
            )
            from vault_graph.mcp.mcp_tool_serialization import (
                decision_trace_response_to_payload,
                explanation_records_for_decision_trace,
                mcp_warning_from_graph,
                resource_links_for_decision_trace,
            )

            records = explanation_records_for_decision_trace(response)
            body = _tool_body(
                tool_name="get_decision_trace",
                payload=decision_trace_response_to_payload(response),
                resource_links=resource_links_for_decision_trace(response),
                warnings=tuple(mcp_warning_from_graph(warning) for warning in response.warnings),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def check_index_status(self, request: CheckIndexStatusInput) -> McpToolBody:
        try:
            selected_scope = _scope_for_tool(request.scope, catalog=self._services.catalog)
            report = self._service_factory.open_status_service().status(scope=selected_scope)
            from vault_graph.mcp.mcp_tool_serialization import status_report_to_payload

            return _tool_body(
                tool_name="check_index_status",
                payload=status_report_to_payload(report, selected_scope=selected_scope),
                resource_links=(),
                warnings=(),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def explain_result(self, request: ExplainResultInput) -> McpToolBody:
        try:
            _validate_explain_result_request(request)
            record = self._explain_result_service.explain(result_id=request.result_id)
            from vault_graph.mcp.mcp_tool_serialization import explanation_payload_to_resource_links
            from vault_graph.memory.result_explanation import explanation_record_to_dict

            payload = explanation_record_to_dict(record)
            return _tool_body(
                tool_name="explain_result",
                payload=payload,
                resource_links=explanation_payload_to_resource_links(payload),
                warnings=tuple(
                    McpErrorPayload(
                        code=warning.code,
                        message=warning.message,
                        severity=warning.severity,
                        affected_vault_ids=warning.affected_vault_ids,
                        recovery_hint=warning.recovery_hint,
                    )
                    for warning in record.warnings
                ),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc


def register_mcp_tools(
    server: McpToolServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
    result_explanation_cache: ResultExplanationCache,
) -> McpToolRegistry:
    registry = McpToolRegistry(
        services=services,
        service_factory=service_factory,
        context_pack_cache=context_pack_cache,
        result_explanation_cache=result_explanation_cache,
    )

    @server.tool("search_vault", structured_output=True)
    def search_vault(
        query: str,
        scope: dict[str, object] | None = None,
        limit: int = 10,
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> dict[str, object]:
        request = parse_search_vault_input(
            query=query,
            scope=scope,
            limit=limit,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
        )
        return registry.search_vault(request).to_json_dict()

    @server.tool("build_context_pack", structured_output=True)
    def build_context_pack(
        goal: str,
        scope: dict[str, object] | None = None,
        max_tokens: int | None = None,
        limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> dict[str, object]:
        request = parse_build_context_pack_input(
            goal=goal,
            scope=scope,
            max_tokens=max_tokens,
            limit=limit,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
        )
        return registry.build_context_pack(request).to_json_dict()

    @server.tool("find_related", structured_output=True)
    def find_related(
        target: str,
        scope: dict[str, object] | None = None,
        depth: int = DEFAULT_GRAPH_RELATED_DEPTH,
        kinds: list[str] | None = None,
        limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
        include_cross_vault: bool = False,
    ) -> dict[str, object]:
        request = parse_find_related_input(
            target=target,
            scope=scope,
            depth=depth,
            kinds=kinds,
            limit=limit,
            include_cross_vault=include_cross_vault,
        )
        return registry.find_related(request).to_json_dict()

    @server.tool("get_decision_trace", structured_output=True)
    def get_decision_trace(
        decision_or_topic: str,
        scope: dict[str, object] | None = None,
        limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
        include_cross_vault: bool = False,
    ) -> dict[str, object]:
        request = parse_decision_trace_input(
            decision_or_topic=decision_or_topic,
            scope=scope,
            limit=limit,
            include_cross_vault=include_cross_vault,
        )
        return registry.get_decision_trace(request).to_json_dict()

    @server.tool("check_index_status", structured_output=True)
    def check_index_status(scope: dict[str, object] | None = None) -> dict[str, object]:
        request = parse_check_index_status_input(scope=scope)
        return registry.check_index_status(request).to_json_dict()

    @server.tool("explain_result", structured_output=True)
    def explain_result(result_id: str) -> dict[str, object]:
        request = parse_explain_result_input(result_id=result_id)
        return registry.explain_result(request).to_json_dict()

    return registry


def mcp_scope_input_from_raw(
    scope: object | None,
    *,
    include_cross_vault: bool = False,
) -> McpScopeInput | None:
    if scope is None:
        return McpScopeInput(include_cross_vault=include_cross_vault) if include_cross_vault else None
    if not isinstance(scope, dict):
        raise _invalid_arguments("scope must be an object")
    allowed = {"vault_ids", "all_vaults", "content_scopes", "include_cross_vault"}
    extra = set(scope) - allowed
    if extra:
        raise _invalid_arguments(f"unsupported scope keys: {', '.join(sorted(str(key) for key in extra))}")
    scope_cross_vault = _optional_bool(
        scope.get("include_cross_vault"),
        "include_cross_vault",
        default=include_cross_vault,
    )
    if scope_cross_vault != include_cross_vault:
        raise _invalid_arguments("scope.include_cross_vault must match include_cross_vault")
    vault_ids = _optional_string_tuple(scope.get("vault_ids"), "vault_ids")
    all_vaults = _optional_bool(scope.get("all_vaults"), "all_vaults", default=False)
    if all_vaults and vault_ids:
        raise _invalid_arguments("Use either all_vaults or vault_ids, not both.")
    return McpScopeInput(
        vault_ids=vault_ids,
        all_vaults=all_vaults,
        content_scopes=_optional_string_tuple(scope.get("content_scopes"), "content_scopes"),
        include_cross_vault=include_cross_vault,
    )


def parse_search_vault_input(
    *,
    query: str,
    scope: dict[str, object] | None = None,
    limit: int = 10,
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> SearchVaultInput:
    request = SearchVaultInput(
        query=_required_string(query, "query"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        limit=_limit(limit),
        include_graph=_required_bool(include_graph, "include_graph"),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
    )
    _validate_search_vault_request(request)
    return request


def parse_build_context_pack_input(
    *,
    goal: str,
    scope: dict[str, object] | None = None,
    max_tokens: int | None = None,
    limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    include_graph: bool = False,
    include_cross_vault: bool = False,
) -> BuildContextPackInput:
    request = BuildContextPackInput(
        goal=_required_string(goal, "goal"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        max_tokens=_optional_positive_int(max_tokens, "max_tokens"),
        limit=_limit(limit),
        include_graph=_required_bool(include_graph, "include_graph"),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
    )
    _validate_build_context_pack_request(request)
    return request


def parse_find_related_input(
    *,
    target: str,
    scope: dict[str, object] | None = None,
    depth: int = DEFAULT_GRAPH_RELATED_DEPTH,
    kinds: list[str] | None = None,
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    include_cross_vault: bool = False,
) -> FindRelatedInput:
    request = FindRelatedInput(
        target=_required_string(target, "target"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        depth=_graph_depth(depth),
        kinds=_string_tuple(kinds or (), "kinds"),
        limit=_limit(limit),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
    )
    _validate_find_related_request(request)
    return request


def parse_decision_trace_input(
    *,
    decision_or_topic: str,
    scope: dict[str, object] | None = None,
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    include_cross_vault: bool = False,
) -> DecisionTraceInput:
    request = DecisionTraceInput(
        decision_or_topic=_required_string(decision_or_topic, "decision_or_topic"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        limit=_limit(limit),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
    )
    _validate_decision_trace_request(request)
    return request


def parse_check_index_status_input(*, scope: dict[str, object] | None = None) -> CheckIndexStatusInput:
    return CheckIndexStatusInput(scope=mcp_scope_input_from_raw(scope))


def parse_explain_result_input(*, result_id: str) -> ExplainResultInput:
    request = ExplainResultInput(result_id=_required_string(result_id, "result_id"))
    _validate_explain_result_request(request)
    return request


def _validate_search_vault_request(request: SearchVaultInput) -> None:
    _required_string(request.query, "query")
    _limit(request.limit)
    _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)


def _validate_build_context_pack_request(request: BuildContextPackInput) -> None:
    _required_string(request.goal, "goal")
    _limit(request.limit)
    _optional_positive_int(request.max_tokens, "max_tokens")
    _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)


def _validate_find_related_request(request: FindRelatedInput) -> None:
    _required_string(request.target, "target")
    _graph_depth(request.depth)
    _limit(request.limit)
    _string_tuple(request.kinds, "kinds")


def _validate_decision_trace_request(request: DecisionTraceInput) -> None:
    _required_string(request.decision_or_topic, "decision_or_topic")
    _limit(request.limit)


def _validate_explain_result_request(request: ExplainResultInput) -> None:
    _required_string(request.result_id, "result_id")


def _scope_for_tool(
    scope: McpScopeInput | None,
    *,
    catalog: VaultCatalog,
    allow_graph_cross_vault: bool = False,
) -> QueryScope:
    return scope_from_mcp_input(scope, catalog=catalog, allow_graph_cross_vault=allow_graph_cross_vault)


def _reject_cross_vault_without_graph(include_cross_vault: bool, *, include_graph: bool) -> None:
    if include_cross_vault and not include_graph:
        raise _invalid_arguments("include_cross_vault requires include_graph")


def _validate_graph_cross_vault_request(selected_scope: QueryScope, *, include_cross_vault: bool) -> None:
    if include_cross_vault and len(selected_scope.vault_ids) < 2:
        raise _invalid_arguments("include_cross_vault requires at least two selected vault_ids")


def _tool_body(
    *,
    tool_name: McpToolName,
    payload: dict[str, object],
    resource_links: tuple[McpResourceLink, ...],
    warnings: tuple[McpErrorPayload, ...],
) -> McpToolBody:
    from vault_graph.mcp.mcp_tool_serialization import tool_text_mirror

    return McpToolBody(
        tool_name=tool_name,
        payload=payload,
        resource_links=resource_links,
        warnings=warnings,
        text=tool_text_mirror(payload),
    )


def _map_tool_exception(exc: Exception, *, service_factory: McpServiceFactory) -> McpProtocolError:
    if isinstance(exc, McpProtocolError):
        return exc
    state_path = getattr(service_factory, "_state_path", None)
    return map_exception_to_mcp_error(exc, user_state_path=state_path)


def _invalid_arguments(message: str) -> McpProtocolError:
    return McpProtocolError(
        kind="invalid_parameter",
        payload=McpErrorPayload(
            code="invalid_tool_arguments",
            message=message,
            severity="error",
            affected_vault_ids=(),
            recovery_hint="Check the tool argument schema and retry with bounded scope.",
        ),
    )


def _required_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise _invalid_arguments(f"{field_name} must be a string")
    stripped = value.strip()
    if not stripped:
        raise _invalid_arguments(f"{field_name} is required")
    return stripped


def _limit(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("limit must be an integer")
    if value < 1 or value > MAX_MCP_TOOL_LIMIT:
        raise _invalid_arguments(f"limit must be between 1 and {MAX_MCP_TOOL_LIMIT}")
    return value


def _graph_depth(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("depth must be an integer")
    if value < 1 or value > MAX_GRAPH_PROJECTION_DEPTH:
        raise _invalid_arguments(f"depth must be between 1 and {MAX_GRAPH_PROJECTION_DEPTH}")
    return value


def _optional_positive_int(value: object | None, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments(f"{field_name} must be an integer")
    if value <= 0:
        raise _invalid_arguments(f"{field_name} must be positive")
    return value


def _required_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise _invalid_arguments(f"{field_name} must be a boolean")
    return value


def _optional_bool(value: object, field_name: str, *, default: bool) -> bool:
    if value is None:
        return default
    return _required_bool(value, field_name)


def _optional_string_tuple(value: object, field_name: str) -> tuple[str, ...] | None:
    if value is None:
        return None
    return _string_tuple(value, field_name)


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise _invalid_arguments(f"{field_name} must be a list of strings")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise _invalid_arguments(f"{field_name} must contain only non-empty strings")
        strings.append(item.strip())
    return tuple(strings)
