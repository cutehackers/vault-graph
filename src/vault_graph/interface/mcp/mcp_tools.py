from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from vault_graph.context.memory.memory_candidates import CANDIDATE_KINDS, CandidateKind
from vault_graph.context.memory.memory_models import MemoryWarning, OpenQuestionsProjection, ProjectMemoryProjection
from vault_graph.context.pack.context_pack import (
    DEFAULT_CONTEXT_MAX_TOKENS,
    DEFAULT_CONTEXT_RETRIEVAL_LIMIT,
    ContextPackBudget,
    ContextPackRequest,
)
from vault_graph.errors import CatalogError, MemoryProjectionError
from vault_graph.interface.composition.query_scope_resolution import (
    PROJECT_SCOPE_WARNING_CODE,
    ProjectQuerySelection,
    empty_project_search_json,
    metadata_index_check,
    project_query_selection,
    project_scope_warning_json,
)
from vault_graph.interface.composition.vault_labels import label_payload
from vault_graph.interface.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.interface.mcp.mcp_errors import McpErrorPayload, McpProtocolError
from vault_graph.interface.mcp.mcp_memory_tools import ImportAutoMemoryInput as ImportAutoMemoryInput
from vault_graph.interface.mcp.mcp_memory_tools import McpMemoryTools as McpMemoryTools
from vault_graph.interface.mcp.mcp_memory_tools import MemoryBasis as MemoryBasis
from vault_graph.interface.mcp.mcp_memory_tools import MemoryKind as MemoryKind
from vault_graph.interface.mcp.mcp_memory_tools import PageKind as PageKind
from vault_graph.interface.mcp.mcp_memory_tools import RememberInput as RememberInput
from vault_graph.interface.mcp.mcp_memory_tools import RestoreMemoryInput as RestoreMemoryInput
from vault_graph.interface.mcp.mcp_memory_tools import RetireMemoryInput as RetireMemoryInput
from vault_graph.interface.mcp.mcp_memory_tools import SupersedeClaimInput as SupersedeClaimInput
from vault_graph.interface.mcp.mcp_memory_tools import UpdateMemoryInput as UpdateMemoryInput
from vault_graph.interface.mcp.mcp_memory_tools import background_index_message as background_index_message
from vault_graph.interface.mcp.mcp_memory_tools import parse_remember_input as parse_remember_input
from vault_graph.interface.mcp.mcp_memory_tools import parse_retire_memory_input as parse_retire_memory_input
from vault_graph.interface.mcp.mcp_memory_tools import parse_update_memory_input as parse_update_memory_input
from vault_graph.interface.mcp.mcp_memory_tools import register_memory_tools
from vault_graph.interface.mcp.mcp_resource_models import McpResourceLink as McpResourceLink
from vault_graph.interface.mcp.mcp_scope import McpScopeInput, scope_from_mcp_input
from vault_graph.interface.mcp.mcp_service_factory import CurrentMcpServices, McpServiceFactory, McpServices
from vault_graph.interface.mcp.mcp_tool_body import McpToolBody as McpToolBody
from vault_graph.interface.mcp.mcp_tool_body import McpToolName as McpToolName
from vault_graph.interface.mcp.mcp_tool_body import McpToolServer as McpToolServer
from vault_graph.interface.mcp.mcp_tool_body import invalid_arguments as _invalid_arguments
from vault_graph.interface.mcp.mcp_tool_body import map_tool_exception as _map_tool_exception
from vault_graph.interface.mcp.mcp_tool_body import tool_body as _tool_body
from vault_graph.interface.mcp.mcp_uri import encode_resource_segment
from vault_graph.interface.mcp.result_explanation_cache import ResultExplanationCache
from vault_graph.operation.integration.vault_map import vault_map_path
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog
from vault_graph.project.context import (
    DEFAULT_PROJECT_CONTEXT_DEPTH,
    DEFAULT_PROJECT_CONTEXT_LIMIT,
    DEFAULT_PROJECT_CONTEXT_TOKENS,
    MAX_PROJECT_CONTEXT_DEPTH,
    MAX_PROJECT_CONTEXT_LIMIT,
    MAX_PROJECT_CONTEXT_TOKENS,
    MIN_PROJECT_CONTEXT_TOKENS,
    ProjectContextRequest,
)
from vault_graph.retrieval.explanation.result_explanation import ExplainResultService
from vault_graph.retrieval.graph.projection.graph_projection import (
    DEFAULT_GRAPH_RELATED_DEPTH,
    DEFAULT_GRAPH_RESULT_LIMIT,
    MAX_GRAPH_PROJECTION_DEPTH,
)
from vault_graph.retrieval.search.search_response import SearchMode

if TYPE_CHECKING:
    from vault_graph.context.memory.project_memory import L3Entry, ProjectL3List

MAX_MCP_TOOL_LIMIT = 50
MAX_MCP_PROJECT_TASK_CHARS = 4096
DEFAULT_MEMORY_CANDIDATE_LIMIT = 20  # spec 2026-11-05 §4.4.4
SKIPPED_OUTCOME = "skipped"
MEMORY_CANDIDATES_WARNING_CODE = "memory_candidates"


# Allowed values of the write tool inputs. They show as `enum` in the MCP schema and must equal
# BASES, REMEMBER_KINDS and MEMORY_KINDS in operation/memory/memory_requests.py.
@dataclass(frozen=True)
class AskVaultInput:
    question: str
    scope: McpScopeInput | None = None
    mode: str = "evidence-first"
    limit: int = 10
    max_evidence_tokens: int = 8000
    include_graph: bool = False
    include_cross_vault: bool = False
    cwd: str | None = None


@dataclass(frozen=True)
class SearchVaultInput:
    query: str
    scope: McpScopeInput | None = None
    limit: int = 10
    include_graph: bool = False
    include_cross_vault: bool = False
    mode: SearchMode = "knowledge"
    cwd: str | None = None
    include_retired: bool = False


@dataclass(frozen=True)
class BuildContextPackInput:
    goal: str
    scope: McpScopeInput | None = None
    max_tokens: int | None = None
    limit: int = DEFAULT_CONTEXT_RETRIEVAL_LIMIT
    include_graph: bool = False
    include_cross_vault: bool = False
    cwd: str | None = None


@dataclass(frozen=True)
class FindRelatedInput:
    target: str
    scope: McpScopeInput | None = None
    depth: int = DEFAULT_GRAPH_RELATED_DEPTH
    kinds: tuple[str, ...] = ()
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False
    cwd: str | None = None


@dataclass(frozen=True)
class DecisionTraceInput:
    decision_or_topic: str
    scope: McpScopeInput | None = None
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT
    include_cross_vault: bool = False
    cwd: str | None = None


@dataclass(frozen=True)
class CheckIndexStatusInput:
    scope: McpScopeInput | None = None


@dataclass(frozen=True)
class ExplainResultInput:
    result_id: str


@dataclass(frozen=True)
class SummarizeProjectMemoryInput:
    scope: McpScopeInput | None = None
    limit: int = 10
    cwd: str | None = None


@dataclass(frozen=True)
class GetOpenQuestionsInput:
    scope: McpScopeInput | None = None
    limit: int = 20
    cwd: str | None = None


@dataclass(frozen=True)
class GetRecentChangesInput:
    since: str | None = None
    scope: McpScopeInput | None = None
    limit: int = 20
    cwd: str | None = None


@dataclass(frozen=True)
class ExploreProjectInput:
    task: str
    project_path: str | None = None
    repository_id: str | None = None
    max_tokens: int = DEFAULT_PROJECT_CONTEXT_TOKENS
    depth: int = DEFAULT_PROJECT_CONTEXT_DEPTH
    limit: int = DEFAULT_PROJECT_CONTEXT_LIMIT

    def to_project_context_request(self) -> ProjectContextRequest:
        return ProjectContextRequest(
            task=self.task,
            project_path=self.project_path,
            repository_id=self.repository_id,
            max_tokens=self.max_tokens,
            depth=self.depth,
            limit=self.limit,
        )


@dataclass(frozen=True)
class ListMemoryCandidatesInput:
    cwd: str | None = None
    kinds: tuple[CandidateKind, ...] | None = None
    limit: int = DEFAULT_MEMORY_CANDIDATE_LIMIT


@dataclass(frozen=True)
class MarkCandidatesReviewedInput:
    keys: tuple[str, ...]
    cwd: str | None = None


class McpToolRegistry:
    tool_names: tuple[McpToolName, ...]

    def __init__(
        self,
        *,
        services: McpServices,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
        result_explanation_cache: ResultExplanationCache,
        services_holder: CurrentMcpServices | None = None,
    ) -> None:
        self.services_holder = services_holder or CurrentMcpServices(services=services, service_factory=service_factory)
        self._service_factory = service_factory
        self._context_pack_cache = context_pack_cache
        self._result_explanation_cache = result_explanation_cache
        self._explain_result_service = ExplainResultService(cache=result_explanation_cache)
        self._memory_tools = McpMemoryTools(
            service_factory=service_factory, on_index_finished=self._refresh_services_after_index
        )
        self.tool_names = (
            "ask_vault",
            "search_vault",
            "build_context_pack",
            "find_related",
            "get_decision_trace",
            "check_index_status",
            "explain_result",
            "summarize_project_memory",
            "get_open_questions",
            "get_recent_changes",
            "explore_project",
            "list_memory_candidates",
            "mark_candidates_reviewed",
            "remember",
            "update_memory",
            "retire_memory",
            "import_auto_memory",
            "supersede_claim",
            "restore_memory",
        )

    def ask_vault(self, request: AskVaultInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_ask_vault_request(request)
            selected_scope, selection = self._query_scope(
                services, request.scope, request.cwd, allow_graph_cross_vault=request.include_graph
            )
            selected_scope = _require_project_scope(selected_scope, selection)
            _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
            from vault_graph.context.answer.answer_plan import AnswerRequest
            from vault_graph.context.answer.answer_response import AnswerMode
            from vault_graph.interface.mcp.mcp_answer_serialization import (
                answer_response_to_payload,
                explanation_records_for_answer,
                mcp_warning_from_answer,
                resource_links_for_answer,
            )

            answer_service = self._service_factory.open_answer_service(include_graph=request.include_graph)
            response = answer_service.ask(
                AnswerRequest(
                    question=request.question,
                    requested_scope=selected_scope,
                    mode=cast(AnswerMode, request.mode),
                    retrieval_limit=request.limit,
                    max_evidence_tokens=request.max_evidence_tokens,
                    include_graph=request.include_graph,
                    include_cross_vault=request.include_cross_vault,
                )
            )
            records = explanation_records_for_answer(response)
            body = _tool_body(
                tool_name="ask_vault",
                payload=_labeled(answer_response_to_payload(response), selection),
                resource_links=resource_links_for_answer(response),
                warnings=(
                    *_scope_warnings(selection),
                    *(mcp_warning_from_answer(warning) for warning in response.warnings),
                ),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def search_vault(self, request: SearchVaultInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_search_vault_request(request)
            selected_scope, selection = self._query_scope(
                services, request.scope, request.cwd, allow_graph_cross_vault=request.include_graph
            )
            _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
            from vault_graph.interface.mcp.mcp_tool_serialization import (
                explanation_records_for_search,
                mcp_warning_from_search,
                resource_links_for_search,
                search_response_to_payload,
            )

            if selected_scope is None:
                return _tool_body(
                    tool_name="search_vault",
                    payload=empty_project_search_json(
                        query_text=request.query, limit=request.limit, warnings=selection.warnings
                    ),
                    resource_links=(),
                    warnings=_scope_warnings(selection),
                )
            retrieval_service = (
                self._service_factory.open_retrieval_service(include_graph=True)
                if request.include_graph
                else services.retrieval_service
            )
            response = retrieval_service.search(
                query_text=request.query,
                requested_scope=selected_scope,
                limit=request.limit,
                output_format="json",
                include_graph=request.include_graph,
                include_cross_vault=request.include_cross_vault,
                mode=request.mode,
                include_retired=request.include_retired,
            )
            records = explanation_records_for_search(response)
            payload = search_response_to_payload(response, labels=selection.labels)
            if selection.warnings:
                payload["warnings"] = [
                    *(project_scope_warning_json(message) for message in selection.warnings),
                    *cast(list[dict[str, object]], payload["warnings"]),
                ]
            body = _tool_body(
                tool_name="search_vault",
                payload=payload,
                resource_links=resource_links_for_search(response),
                warnings=(
                    *_scope_warnings(selection),
                    *(mcp_warning_from_search(warning) for warning in response.warnings),
                ),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def build_context_pack(self, request: BuildContextPackInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_build_context_pack_request(request)
            selected_scope, selection = self._query_scope(
                services, request.scope, request.cwd, allow_graph_cross_vault=request.include_graph
            )
            selected_scope = _require_project_scope(selected_scope, selection)
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
                else services.context_pack_builder
            )
            pack = builder.build(pack_request)
            rendered_json = services.context_pack_renderer.render_json(pack)
            self._context_pack_cache.put(pack, rendered_json=rendered_json)
            from vault_graph.interface.mcp.mcp_tool_serialization import (
                context_pack_to_payload,
                explanation_records_for_context_pack,
                mcp_warning_from_context,
                resource_links_for_context_pack,
            )

            records = explanation_records_for_context_pack(pack)
            body = _tool_body(
                tool_name="build_context_pack",
                payload=_labeled(context_pack_to_payload(pack), selection),
                resource_links=(
                    McpResourceLink(
                        rel="context_pack",
                        uri=f"vault://context/packs/{encode_resource_segment(pack.pack_id)}",
                        title=pack.goal,
                    ),
                    *resource_links_for_context_pack(pack),
                ),
                warnings=(
                    *_scope_warnings(selection),
                    *(mcp_warning_from_context(warning) for warning in pack.warnings),
                ),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def _query_scope(
        self,
        services: McpServices,
        scope_input: McpScopeInput | None,
        cwd: str | None,
        *,
        allow_graph_cross_vault: bool,
    ) -> tuple[QueryScope | None, ProjectQuerySelection]:
        """Pick the scope of a query tool (spec V2) and the labels for its results.

        A request that names ``vault_ids`` or ``all_vaults`` keeps its scope. Otherwise the
        registered Vaults of the ``cwd`` project are used, ``cwd`` defaulting to the server working
        directory. Outside a project the active Vault is used. None means the project has no
        searchable Vault.
        """
        explicit = scope_input is not None and bool(scope_input.vault_ids or scope_input.all_vaults)
        selection = project_query_selection(
            None if explicit else Path(cwd) if cwd is not None else Path.cwd(),
            catalog=services.catalog,
            vault_map_file=vault_map_path(),
            is_indexed=metadata_index_check(services.metadata_store),
        )
        if selection.vault_ids == ():
            return None, selection
        if selection.vault_ids is not None:
            scope_input = McpScopeInput(
                vault_ids=selection.vault_ids,
                content_scopes=scope_input.content_scopes if scope_input is not None else None,
                include_cross_vault=scope_input.include_cross_vault if scope_input is not None else False,
            )
        scope = _scope_for_tool(scope_input, catalog=services.catalog, allow_graph_cross_vault=allow_graph_cross_vault)
        return scope, selection

    def _project_scope(
        self,
        services: McpServices,
        scope_input: McpScopeInput | None,
        cwd: str | None,
        *,
        allow_graph_cross_vault: bool = False,
    ) -> tuple[QueryScope, ProjectQuerySelection]:
        """``_query_scope`` for tools that need at least one Vault: a project with none is an error."""
        selected_scope, selection = self._query_scope(
            services, scope_input, cwd, allow_graph_cross_vault=allow_graph_cross_vault
        )
        return _require_project_scope(selected_scope, selection), selection

    def find_related(self, request: FindRelatedInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_find_related_request(request)
            selected_scope, selection = self._project_scope(
                services, request.scope, request.cwd, allow_graph_cross_vault=True
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
            from vault_graph.interface.mcp.mcp_tool_serialization import (
                explanation_records_for_related,
                mcp_warning_from_graph,
                related_response_to_payload,
                resource_links_for_related,
            )

            records = explanation_records_for_related(response)
            body = _tool_body(
                tool_name="find_related",
                payload=_labeled(related_response_to_payload(response), selection),
                resource_links=resource_links_for_related(response),
                warnings=(
                    *_scope_warnings(selection),
                    *(mcp_warning_from_graph(warning) for warning in response.warnings),
                ),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def get_decision_trace(self, request: DecisionTraceInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_decision_trace_request(request)
            selected_scope, selection = self._project_scope(
                services, request.scope, request.cwd, allow_graph_cross_vault=True
            )
            _validate_graph_cross_vault_request(selected_scope, include_cross_vault=request.include_cross_vault)
            response = self._service_factory.open_graph_retrieval_service().decision_trace(
                topic=request.decision_or_topic,
                requested_scope=selected_scope,
                include_cross_vault=request.include_cross_vault,
                limit=request.limit,
                output_format="json",
            )
            from vault_graph.interface.mcp.mcp_tool_serialization import (
                decision_trace_response_to_payload,
                explanation_records_for_decision_trace,
                mcp_warning_from_graph,
                resource_links_for_decision_trace,
            )

            records = explanation_records_for_decision_trace(response)
            body = _tool_body(
                tool_name="get_decision_trace",
                payload=_labeled(decision_trace_response_to_payload(response), selection),
                resource_links=resource_links_for_decision_trace(response),
                warnings=(
                    *_scope_warnings(selection),
                    *(mcp_warning_from_graph(warning) for warning in response.warnings),
                ),
            )
            self._result_explanation_cache.put_many(records)
            return body
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def check_index_status(self, request: CheckIndexStatusInput) -> McpToolBody:
        try:
            services = self._current_services()
            selected_scope = _scope_for_tool(request.scope, catalog=services.catalog)
            report = self._service_factory.open_status_service().status(scope=selected_scope)
            from vault_graph.interface.mcp.mcp_memory_serialization import (
                health_explorer_report_to_payload,
                memory_warning_to_mcp_error,
                runtime_cache_records_for_mcp,
            )
            from vault_graph.interface.mcp.mcp_tool_serialization import status_report_to_payload

            runtime_caches = runtime_cache_records_for_mcp(
                context_pack_cache=self._context_pack_cache,
                result_explanation_cache=self._result_explanation_cache,
            )
            health_report = self._service_factory.open_health_explorer_service().inspect(
                requested_scope=selected_scope,
                runtime_caches=runtime_caches,
                status_report=report,
            )

            return _tool_body(
                tool_name="check_index_status",
                payload=status_report_to_payload(
                    report,
                    selected_scope=selected_scope,
                    health_explorer=health_explorer_report_to_payload(health_report),
                ),
                resource_links=(),
                warnings=tuple(memory_warning_to_mcp_error(warning) for warning in health_report.warnings),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def explain_result(self, request: ExplainResultInput) -> McpToolBody:
        try:
            self._current_services()
            _validate_explain_result_request(request)
            record = self._explain_result_service.explain(result_id=request.result_id)
            from vault_graph.interface.mcp.mcp_tool_serialization import explanation_payload_to_resource_links
            from vault_graph.retrieval.explanation.result_explanation import explanation_record_to_dict

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

    def summarize_project_memory(self, request: SummarizeProjectMemoryInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_summarize_project_memory_request(request)
            selected_scope, selection = self._project_scope(services, request.scope, request.cwd)
            from vault_graph.interface.composition.read_only_service_factory import project_memory_scope

            memory_scope = project_memory_scope(
                Path(request.cwd) if request.cwd is not None else Path.cwd(),
                vault_map_file=vault_map_path(),
                catalog=services.catalog,
            )
            from vault_graph.interface.composition.read_only_service_factory import metadata_body_reader

            project_memory = self._service_factory.open_project_memory_service()
            project_id = memory_scope.project_id if memory_scope is not None else None
            projection = project_memory.summarize(
                requested_scope=selected_scope,
                limit=request.limit,
                project_id=project_id,
                vault_scopes=memory_scope.vault_scopes if memory_scope is not None else None,
            )
            # The same L3 list as session start recall block L3 (spec 2026-11-05 §4.4.7, A-27).
            l3_list = project_memory.l3_list(
                requested_scope=selected_scope,
                project_id=project_id,
                vault_scopes=memory_scope.vault_scopes if memory_scope is not None else {},
                body_reader=metadata_body_reader(services.metadata_store),
                limit=request.limit,
            )
            from vault_graph.interface.mcp.mcp_memory_serialization import (
                memory_warning_to_mcp_error,
                project_memory_projection_to_payload,
                resource_links_for_memory_projection,
            )

            warnings = (
                *_scope_warnings(selection),
                *(memory_warning_to_mcp_error(warning) for warning in _project_memory_warnings(projection)),
            )
            return _tool_body(
                tool_name="summarize_project_memory",
                payload=_labeled(
                    {**project_memory_projection_to_payload(projection), "l3_list": _l3_list_payload(l3_list)},
                    selection,
                ),
                resource_links=resource_links_for_memory_projection(projection),
                warnings=warnings,
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def get_open_questions(self, request: GetOpenQuestionsInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_get_open_questions_request(request)
            selected_scope, selection = self._project_scope(services, request.scope, request.cwd)
            projection = self._service_factory.open_issue_memory_service().open_questions(
                requested_scope=selected_scope,
                limit=request.limit,
            )
            from vault_graph.interface.mcp.mcp_memory_serialization import (
                memory_warning_to_mcp_error,
                open_questions_projection_to_payload,
                resource_links_for_memory_projection,
            )

            warnings = (
                *_scope_warnings(selection),
                *(memory_warning_to_mcp_error(warning) for warning in _open_questions_warnings(projection)),
            )
            return _tool_body(
                tool_name="get_open_questions",
                payload=_labeled(open_questions_projection_to_payload(projection), selection),
                resource_links=resource_links_for_memory_projection(projection),
                warnings=warnings,
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def get_recent_changes(self, request: GetRecentChangesInput) -> McpToolBody:
        try:
            services = self._current_services()
            _validate_get_recent_changes_request(request)
            selected_scope, selection = self._project_scope(services, request.scope, request.cwd)
            try:
                projection = self._service_factory.open_timeline_memory_service().recent_changes(
                    requested_scope=selected_scope,
                    since=request.since,
                    limit=request.limit,
                )
            except MemoryProjectionError as exc:
                raise _memory_projection_error_to_mcp_error(exc, affected_vault_ids=selected_scope.vault_ids) from exc
            from vault_graph.interface.mcp.mcp_memory_serialization import (
                memory_warning_to_mcp_error,
                recent_changes_projection_to_payload,
                resource_links_for_recent_changes,
                timeline_warnings,
            )

            return _tool_body(
                tool_name="get_recent_changes",
                payload=_labeled(recent_changes_projection_to_payload(projection), selection),
                resource_links=resource_links_for_recent_changes(projection),
                warnings=(
                    *_scope_warnings(selection),
                    *(memory_warning_to_mcp_error(warning) for warning in timeline_warnings(projection)),
                ),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def explore_project(self, request: ExploreProjectInput) -> McpToolBody:
        """Expose only the project-context application boundary to MCP."""

        try:
            self._current_services()
            _validate_explore_project_request(request)
            context = self._service_factory.open_project_context_service().build(request.to_project_context_request())
            from vault_graph.interface.mcp.mcp_tool_serialization import (
                mcp_warnings_for_project_context,
                project_context_text_mirror,
                project_context_to_payload,
                resource_links_for_project_context,
            )

            payload = project_context_to_payload(context)
            return _bounded_project_context_body(
                payload=payload,
                resource_links=resource_links_for_project_context(context),
                warnings=mcp_warnings_for_project_context(context),
                text=project_context_text_mirror(context),
                max_tokens=request.max_tokens,
            )
        except ValueError as exc:
            if _is_project_scope_error(exc):
                raise _project_scope_error(exc) from exc
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def list_memory_candidates(self, request: ListMemoryCandidatesInput) -> McpToolBody:
        """Return the cleanup bundle of the ``cwd`` project and start a new cleanup (spec 2026-11-05 §4.4.4).

        A cleanup runs from one call to the next in this server process, so every call resets the
        inferred proposal count, also when the bundle is empty.
        """

        try:
            self._service_factory.start_curation()
            cwd = Path(request.cwd) if request.cwd is not None else Path.cwd()
            package = self._service_factory.memory_candidate_package(cwd, kinds=request.kinds, limit=request.limit)
            from vault_graph.interface.mcp.mcp_tool_serialization import memory_candidate_package_to_payload

            return _tool_body(
                tool_name="list_memory_candidates",
                payload=memory_candidate_package_to_payload(package),
                resource_links=(),
                warnings=tuple(
                    McpErrorPayload(
                        code=MEMORY_CANDIDATES_WARNING_CODE, message=message, severity="warning", affected_vault_ids=()
                    )
                    for message in package.warnings
                ),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def mark_candidates_reviewed(self, request: MarkCandidatesReviewedInput) -> McpToolBody:
        """Record skipped candidates in the Graph Home ``memory/reviewed.jsonl``. Writes nothing to a Vault."""

        try:
            self._service_factory.open_reviewed_log().append(request.keys, outcome=SKIPPED_OUTCOME)
            return _tool_body(
                tool_name="mark_candidates_reviewed",
                payload={"recorded": list(request.keys), "outcome": SKIPPED_OUTCOME},
                resource_links=(),
                warnings=(),
            )
        except Exception as exc:
            raise _map_tool_exception(exc, service_factory=self._service_factory) from exc

    def remember(self, request: RememberInput) -> McpToolBody:
        return self._memory_tools.remember(request)

    def update_memory(self, request: UpdateMemoryInput) -> McpToolBody:
        return self._memory_tools.update_memory(request)

    def retire_memory(self, request: RetireMemoryInput) -> McpToolBody:
        return self._memory_tools.retire_memory(request)

    def import_auto_memory(self, request: ImportAutoMemoryInput) -> McpToolBody:
        return self._memory_tools.import_auto_memory(request)

    def supersede_claim(self, request: SupersedeClaimInput) -> McpToolBody:
        return self._memory_tools.supersede_claim(request)

    def restore_memory(self, request: RestoreMemoryInput) -> McpToolBody:
        return self._memory_tools.restore_memory(request)

    def _current_services(self) -> McpServices:
        """Return read services on the active index generation, reopening them when it changed (finding 발견2)."""
        return self.services_holder.get()

    def _refresh_services_after_index(self, succeeded: bool) -> None:
        """Reopen the shared read services so search reads the index generation just published."""
        if succeeded:
            self.services_holder.reopen()


def register_mcp_tools(
    server: McpToolServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
    result_explanation_cache: ResultExplanationCache,
    services_holder: CurrentMcpServices | None = None,
) -> McpToolRegistry:
    registry = McpToolRegistry(
        services=services,
        service_factory=service_factory,
        context_pack_cache=context_pack_cache,
        result_explanation_cache=result_explanation_cache,
        services_holder=services_holder,
    )

    @server.tool("ask_vault", structured_output=True)
    def ask_vault(
        question: str,
        scope: dict[str, object] | None = None,
        mode: str = "evidence-first",
        limit: int = 10,
        max_evidence_tokens: int = 8000,
        include_graph: bool = False,
        include_cross_vault: bool = False,
        cwd: str | None = None,
    ) -> dict[str, object]:
        request = parse_ask_vault_input(
            question=question,
            scope=scope,
            mode=mode,
            limit=limit,
            max_evidence_tokens=max_evidence_tokens,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
            cwd=cwd,
        )
        return registry.ask_vault(request).to_json_dict()

    @server.tool("search_vault", structured_output=True)
    def search_vault(
        query: str,
        scope: dict[str, object] | None = None,
        limit: int = 10,
        include_graph: bool = False,
        include_cross_vault: bool = False,
        mode: str = "knowledge",
        cwd: str | None = None,
        include_retired: bool = False,
    ) -> dict[str, object]:
        request = parse_search_vault_input(
            query=query,
            scope=scope,
            limit=limit,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
            mode=mode,
            cwd=cwd,
            include_retired=include_retired,
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
        cwd: str | None = None,
    ) -> dict[str, object]:
        request = parse_build_context_pack_input(
            goal=goal,
            scope=scope,
            max_tokens=max_tokens,
            limit=limit,
            include_graph=include_graph,
            include_cross_vault=include_cross_vault,
            cwd=cwd,
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
        cwd: str | None = None,
    ) -> dict[str, object]:
        """Find graph entities related to ``target``, with evidence.

        ``cwd`` is the project folder. Without ``scope``, the tool reads every registered Vault linked to that
        project in vault-map.json. Without ``cwd``, the server working folder is used. Outside a project the
        active Vault is used. ``scope`` with ``vault_ids`` or ``all_vaults`` overrides the project choice.
        """
        request = parse_find_related_input(
            target=target,
            scope=scope,
            depth=depth,
            kinds=kinds,
            limit=limit,
            include_cross_vault=include_cross_vault,
            cwd=cwd,
        )
        return registry.find_related(request).to_json_dict()

    @server.tool("get_decision_trace", structured_output=True)
    def get_decision_trace(
        decision_or_topic: str,
        scope: dict[str, object] | None = None,
        limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
        include_cross_vault: bool = False,
        cwd: str | None = None,
    ) -> dict[str, object]:
        """Trace a decision or topic through the graph: what led to it and what it replaced.

        ``cwd`` is the project folder. Without ``scope``, the tool reads every registered Vault linked to that
        project in vault-map.json. Without ``cwd``, the server working folder is used. Outside a project the
        active Vault is used. ``scope`` with ``vault_ids`` or ``all_vaults`` overrides the project choice.
        """
        request = parse_decision_trace_input(
            decision_or_topic=decision_or_topic,
            scope=scope,
            limit=limit,
            include_cross_vault=include_cross_vault,
            cwd=cwd,
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

    @server.tool("summarize_project_memory", structured_output=True)
    def summarize_project_memory(
        scope: dict[str, object] | None = None,
        limit: int = 10,
        cwd: str | None = None,
    ) -> dict[str, object]:
        """Summarize current state, decisions, open questions, constraints and next priorities.

        ``cwd`` is the project folder. Without ``scope``, the tool reads every registered Vault linked to that
        project in vault-map.json. Without ``cwd``, the server working folder is used. Outside a project the
        active Vault is used. ``scope`` with ``vault_ids`` or ``all_vaults`` overrides the project choice.
        """
        request = parse_summarize_project_memory_input(scope=scope, limit=limit, cwd=cwd)
        return registry.summarize_project_memory(request).to_json_dict()

    @server.tool("get_open_questions", structured_output=True)
    def get_open_questions(
        scope: dict[str, object] | None = None,
        limit: int = 20,
        cwd: str | None = None,
    ) -> dict[str, object]:
        """List open questions recorded in Vault pages.

        ``cwd`` is the project folder. Without ``scope``, the tool reads every registered Vault linked to that
        project in vault-map.json. Without ``cwd``, the server working folder is used. Outside a project the
        active Vault is used. ``scope`` with ``vault_ids`` or ``all_vaults`` overrides the project choice.
        """
        request = parse_get_open_questions_input(scope=scope, limit=limit, cwd=cwd)
        return registry.get_open_questions(request).to_json_dict()

    @server.tool("get_recent_changes", structured_output=True)
    def get_recent_changes(
        since: str | None = None,
        scope: dict[str, object] | None = None,
        limit: int = 20,
        cwd: str | None = None,
    ) -> dict[str, object]:
        """List Vault pages changed since ``since`` (ISO date or datetime).

        ``cwd`` is the project folder. Without ``scope``, the tool reads every registered Vault linked to that
        project in vault-map.json. Without ``cwd``, the server working folder is used. Outside a project the
        active Vault is used. ``scope`` with ``vault_ids`` or ``all_vaults`` overrides the project choice.
        """
        request = parse_get_recent_changes_input(since=since, scope=scope, limit=limit, cwd=cwd)
        return registry.get_recent_changes(request).to_json_dict()

    @server.tool("explore_project", structured_output=True)
    def explore_project(
        task: str,
        project_path: str | None = None,
        repository_id: str | None = None,
        max_tokens: int | None = None,
        depth: int = DEFAULT_PROJECT_CONTEXT_DEPTH,
        limit: int = DEFAULT_PROJECT_CONTEXT_LIMIT,
    ) -> dict[str, object]:
        request = parse_explore_project_input(
            task=task,
            project_path=project_path,
            repository_id=repository_id,
            max_tokens=max_tokens,
            depth=depth,
            limit=limit,
        )
        return registry.explore_project(request).to_json_dict()

    @server.tool("list_memory_candidates", structured_output=True)
    def list_memory_candidates(
        cwd: str | None = None,
        kinds: list[CandidateKind] | None = None,
        limit: int = DEFAULT_MEMORY_CANDIDATE_LIMIT,
    ) -> dict[str, object]:
        """List memory cleanup candidates of a project and start a new cleanup. Reads only; writes nothing.

        Kinds: ``l1_note`` (a Claude Code auto-memory note no linked Vault keeps yet; ``location`` is the note
        path), ``session_exchange`` (an indexed session exchange no wiki page cites yet; ``location`` is
        ``<path> L<a>-L<b>``, cite it as is), ``merge`` (two very similar current pages) and ``retire`` (a page
        whose cited code is gone or that recall injected for 90 days and nobody opened) and ``brief`` (five or
        more decision pages since the project brief; ``location`` is the brief path, ``comparison`` the new
        decision pages; write the brief last, with remember kind project when it does not exist yet, else
        update_memory). Each candidate has a
        ``key``; pass it as ``candidate_key`` to the write tool that handles it, or to mark_candidates_reviewed
        to skip it. ``comparison`` lists similar existing pages with ``status`` and ``superseded_by``; a
        retired page has ``label`` "폐기됨: <reason>": use restore_memory instead of writing it again.

        Each call starts a new cleanup: at most 10 ``basis: inferred`` proposals until the next call.
        ``cwd`` is the project folder; without it the server working folder is used. Outside a project the
        bundle is empty and ``reason`` says why. The prompt curate_memory gives the full order of steps.
        """
        request = parse_list_memory_candidates_input(cwd=cwd, kinds=kinds, limit=limit)
        return registry.list_memory_candidates(request).to_json_dict()

    @server.tool("mark_candidates_reviewed", structured_output=True)
    def mark_candidates_reviewed(keys: list[str], cwd: str | None = None) -> dict[str, object]:
        """Record cleanup candidates you decided to skip, so list_memory_candidates does not offer them again.

        ``keys`` are candidate ``key`` values from list_memory_candidates. The record goes to the vault-graph
        Graph Home (``memory/reviewed.jsonl``) with outcome ``skipped``; nothing is written to a Vault.
        Candidates handled by a write tool with ``candidate_key`` are recorded by that tool. ``cwd`` is
        accepted like in list_memory_candidates; the record is one Graph Home file for every project.
        """
        request = parse_mark_candidates_reviewed_input(keys=keys, cwd=cwd)
        return registry.mark_candidates_reviewed(request).to_json_dict()

    register_memory_tools(server, registry)
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


def parse_list_memory_candidates_input(
    *,
    cwd: str | None = None,
    kinds: Sequence[str] | None = None,
    limit: int = DEFAULT_MEMORY_CANDIDATE_LIMIT,
) -> ListMemoryCandidatesInput:
    kind_values = _optional_string_tuple(kinds, "kinds")
    if kind_values is not None:
        unknown = sorted(set(kind_values) - set(CANDIDATE_KINDS))
        if unknown:
            raise _invalid_arguments(f"kinds must be among {', '.join(CANDIDATE_KINDS)}; got {', '.join(unknown)}")
    return ListMemoryCandidatesInput(
        cwd=_optional_cwd(cwd),
        kinds=cast(tuple[CandidateKind, ...], kind_values) if kind_values is not None else None,
        limit=_limit(limit),
    )


def parse_mark_candidates_reviewed_input(*, keys: list[str], cwd: str | None = None) -> MarkCandidatesReviewedInput:
    values = _string_tuple(keys, "keys")
    if not values:
        raise _invalid_arguments("keys must list at least one candidate key")
    if any("\n" in value or "\r" in value for value in values):
        raise _invalid_arguments("keys must contain only single-line strings")
    return MarkCandidatesReviewedInput(keys=values, cwd=_optional_cwd(cwd))


def parse_ask_vault_input(
    *,
    question: str,
    scope: dict[str, object] | None = None,
    mode: str = "evidence-first",
    limit: int = 10,
    max_evidence_tokens: int = 8000,
    include_graph: bool = False,
    include_cross_vault: bool = False,
    cwd: str | None = None,
) -> AskVaultInput:
    request = AskVaultInput(
        question=_required_string(question, "question"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        mode=_required_string(mode, "mode"),
        limit=_limit(limit),
        max_evidence_tokens=_evidence_token_budget(max_evidence_tokens),
        include_graph=_required_bool(include_graph, "include_graph"),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
        cwd=_optional_cwd(cwd),
    )
    _validate_ask_vault_request(request)
    return request


def parse_search_vault_input(
    *,
    query: str,
    scope: dict[str, object] | None = None,
    limit: int = 10,
    include_graph: bool = False,
    include_cross_vault: bool = False,
    mode: str = "knowledge",
    cwd: str | None = None,
    include_retired: bool = False,
) -> SearchVaultInput:
    request = SearchVaultInput(
        query=_required_string(query, "query"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        limit=_limit(limit),
        include_graph=_required_bool(include_graph, "include_graph"),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
        mode=cast(SearchMode, mode),
        cwd=_optional_cwd(cwd),
        include_retired=_required_bool(include_retired, "include_retired"),
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
    cwd: str | None = None,
) -> BuildContextPackInput:
    request = BuildContextPackInput(
        goal=_required_string(goal, "goal"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        max_tokens=_optional_positive_int(max_tokens, "max_tokens"),
        limit=_limit(limit),
        include_graph=_required_bool(include_graph, "include_graph"),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
        cwd=_optional_cwd(cwd),
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
    cwd: str | None = None,
) -> FindRelatedInput:
    request = FindRelatedInput(
        target=_required_string(target, "target"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        depth=_graph_depth(depth),
        kinds=_string_tuple(kinds or (), "kinds"),
        limit=_limit(limit),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
        cwd=_optional_cwd(cwd),
    )
    _validate_find_related_request(request)
    return request


def parse_decision_trace_input(
    *,
    decision_or_topic: str,
    scope: dict[str, object] | None = None,
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    include_cross_vault: bool = False,
    cwd: str | None = None,
) -> DecisionTraceInput:
    request = DecisionTraceInput(
        decision_or_topic=_required_string(decision_or_topic, "decision_or_topic"),
        scope=mcp_scope_input_from_raw(scope, include_cross_vault=include_cross_vault),
        limit=_limit(limit),
        include_cross_vault=_required_bool(include_cross_vault, "include_cross_vault"),
        cwd=_optional_cwd(cwd),
    )
    _validate_decision_trace_request(request)
    return request


def parse_check_index_status_input(*, scope: dict[str, object] | None = None) -> CheckIndexStatusInput:
    return CheckIndexStatusInput(scope=mcp_scope_input_from_raw(scope))


def parse_explain_result_input(*, result_id: str) -> ExplainResultInput:
    request = ExplainResultInput(result_id=_required_string(result_id, "result_id"))
    _validate_explain_result_request(request)
    return request


def parse_summarize_project_memory_input(
    *,
    scope: dict[str, object] | None = None,
    limit: int = 10,
    cwd: str | None = None,
) -> SummarizeProjectMemoryInput:
    request = SummarizeProjectMemoryInput(
        scope=mcp_scope_input_from_raw(scope), limit=_limit(limit), cwd=_optional_cwd(cwd)
    )
    _validate_summarize_project_memory_request(request)
    return request


def parse_get_open_questions_input(
    *,
    scope: dict[str, object] | None = None,
    limit: int = 20,
    cwd: str | None = None,
) -> GetOpenQuestionsInput:
    request = GetOpenQuestionsInput(scope=mcp_scope_input_from_raw(scope), limit=_limit(limit), cwd=_optional_cwd(cwd))
    _validate_get_open_questions_request(request)
    return request


def parse_get_recent_changes_input(
    *,
    since: str | None = None,
    scope: dict[str, object] | None = None,
    limit: int = 20,
    cwd: str | None = None,
) -> GetRecentChangesInput:
    from vault_graph.context.memory.timeline_memory import parse_timeline_since

    try:
        parsed_since = parse_timeline_since(since)
    except MemoryProjectionError as exc:
        raise _invalid_arguments(str(exc)) from exc
    request = GetRecentChangesInput(
        since=parsed_since,
        scope=mcp_scope_input_from_raw(scope),
        limit=_limit(limit),
        cwd=_optional_cwd(cwd),
    )
    _validate_get_recent_changes_request(request)
    return request


def parse_explore_project_input(
    *,
    task: str,
    project_path: str | None = None,
    repository_id: str | None = None,
    max_tokens: int | None = None,
    depth: int = DEFAULT_PROJECT_CONTEXT_DEPTH,
    limit: int = DEFAULT_PROJECT_CONTEXT_LIMIT,
) -> ExploreProjectInput:
    if project_path is not None and repository_id is not None:
        raise _invalid_arguments("Use either project_path or repository_id, not both.")
    request = ExploreProjectInput(
        task=_project_task(task),
        project_path=_optional_project_scope(project_path, "project_path"),
        repository_id=_optional_project_scope(repository_id, "repository_id"),
        max_tokens=_project_token_budget(max_tokens),
        depth=_project_depth(depth),
        limit=_project_limit(limit),
    )
    _validate_explore_project_request(request)
    return request


def _validate_search_vault_request(request: SearchVaultInput) -> None:
    _required_string(request.query, "query")
    _limit(request.limit)
    _reject_cross_vault_without_graph(request.include_cross_vault, include_graph=request.include_graph)
    if request.mode not in ("knowledge", "evidence", "operating", "audit", "all"):
        raise _invalid_arguments("unsupported search mode")


def _validate_ask_vault_request(request: AskVaultInput) -> None:
    _required_string(request.question, "question")
    if request.mode != "evidence-first":
        raise _invalid_arguments("unsupported answer mode")
    _limit(request.limit)
    _evidence_token_budget(request.max_evidence_tokens)
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


def _validate_summarize_project_memory_request(request: SummarizeProjectMemoryInput) -> None:
    _limit(request.limit)


def _validate_get_open_questions_request(request: GetOpenQuestionsInput) -> None:
    _limit(request.limit)


def _validate_get_recent_changes_request(request: GetRecentChangesInput) -> None:
    _limit(request.limit)
    if request.scope is not None and request.scope.include_cross_vault:
        raise _invalid_arguments("get_recent_changes does not support include_cross_vault")


def _validate_explore_project_request(request: ExploreProjectInput) -> None:
    _project_task(request.task)
    _optional_project_scope(request.project_path, "project_path")
    _optional_project_scope(request.repository_id, "repository_id")
    if request.project_path is not None and request.repository_id is not None:
        raise _invalid_arguments("Use either project_path or repository_id, not both.")
    _project_token_budget(request.max_tokens)
    _project_depth(request.depth)
    _project_limit(request.limit)


def _scope_for_tool(
    scope: McpScopeInput | None,
    *,
    catalog: VaultCatalog,
    allow_graph_cross_vault: bool = False,
) -> QueryScope:
    return scope_from_mcp_input(scope, catalog=catalog, allow_graph_cross_vault=allow_graph_cross_vault)


def _optional_cwd(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _invalid_arguments("cwd must be a non-empty string")
    return value


def _scope_warnings(selection: ProjectQuerySelection) -> tuple[McpErrorPayload, ...]:
    return tuple(
        McpErrorPayload(code=PROJECT_SCOPE_WARNING_CODE, message=message, severity="warning", affected_vault_ids=())
        for message in selection.warnings
    )


def _l3_list_payload(l3_list: ProjectL3List) -> dict[str, object]:
    """Open work, current decisions, corrections and rules of the project; ``superseded`` claim rows are left out."""

    def entries(items: tuple[L3Entry, ...]) -> list[dict[str, object]]:
        return [
            {
                "vault_id": entry.vault_id,
                "path": entry.path,
                "title": entry.title,
                "day": entry.day,
                "status": entry.status,
                "claims": [
                    {"claim": row.claim, "status": row.status, "evidence": row.evidence} for row in entry.claims
                ],
            }
            for entry in items
        ]

    return {
        "open_work": entries(l3_list.open_work),
        "decisions": entries(l3_list.decisions),
        "corrections_and_rules": entries(l3_list.corrections_and_rules),
        "warnings": list(l3_list.warnings),
    }


def _labeled(payload: dict[str, object], selection: ProjectQuerySelection) -> dict[str, object]:
    """Name the source Vault of every result in a read tool payload (§0 rule 4, F12)."""
    return cast(dict[str, object], label_payload(payload, selection.labels))


def _require_project_scope(scope: QueryScope | None, selection: ProjectQuerySelection) -> QueryScope:
    """Answers and context packs need at least one Vault. A project with none is an error, not a fallback."""
    if scope is None:
        raise CatalogError(" ".join(selection.warnings) or "The project has no searchable Vault. Run `vg setup`.")
    return scope


def _reject_cross_vault_without_graph(include_cross_vault: bool, *, include_graph: bool) -> None:
    if include_cross_vault and not include_graph:
        raise _invalid_arguments("include_cross_vault requires include_graph")


def _validate_graph_cross_vault_request(selected_scope: QueryScope, *, include_cross_vault: bool) -> None:
    if include_cross_vault and len(selected_scope.vault_ids) < 2:
        raise _invalid_arguments("include_cross_vault requires at least two selected vault_ids")


def _project_memory_warnings(projection: ProjectMemoryProjection) -> tuple[MemoryWarning, ...]:
    return tuple(
        (
            *projection.warnings,
            *(warning for vault in projection.vaults for warning in vault.warnings),
            *(warning for vault in projection.vaults for item in vault.current_state for warning in item.warnings),
            *(warning for vault in projection.vaults for item in vault.decisions for warning in item.warnings),
            *(warning for vault in projection.vaults for item in vault.open_questions for warning in item.warnings),
            *(warning for vault in projection.vaults for item in vault.constraints for warning in item.warnings),
            *(warning for vault in projection.vaults for item in vault.next_priorities for warning in item.warnings),
            *(warning for vault in projection.vaults for item in vault.stale_areas for warning in item.warnings),
        )
    )


def _open_questions_warnings(projection: OpenQuestionsProjection) -> tuple[MemoryWarning, ...]:
    return tuple(
        (
            *projection.warnings,
            *(warning for vault in projection.vaults for warning in vault.warnings),
            *(warning for vault in projection.vaults for item in vault.questions for warning in item.warnings),
        )
    )


def _memory_projection_error_to_mcp_error(
    exc: MemoryProjectionError,
    *,
    affected_vault_ids: tuple[str, ...],
) -> McpProtocolError:
    code = str(exc).split(":", 1)[0].strip() if ":" in str(exc) else "memory_projection_unavailable"
    kind: Literal["invalid_parameter", "execution"] = (
        "invalid_parameter" if code == "invalid_timeline_since" else "execution"
    )
    recovery_hint = "Run vg index, then vg status for the selected Vault." if code == "metadata_unavailable" else None
    return McpProtocolError(
        kind=kind,
        payload=McpErrorPayload(
            code=code,
            message=str(exc),
            severity="error",
            affected_vault_ids=affected_vault_ids,
            recovery_hint=recovery_hint,
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


def _evidence_token_budget(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("max_evidence_tokens must be an integer")
    if value < 1000 or value > 24000:
        raise _invalid_arguments("max_evidence_tokens must be between 1000 and 24000")
    return value


def _graph_depth(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("depth must be an integer")
    if value < 1 or value > MAX_GRAPH_PROJECTION_DEPTH:
        raise _invalid_arguments(f"depth must be between 1 and {MAX_GRAPH_PROJECTION_DEPTH}")
    return value


def _project_task(value: object) -> str:
    task = _required_string(value, "task")
    if len(task) > MAX_MCP_PROJECT_TASK_CHARS:
        raise _invalid_arguments(f"task must be at most {MAX_MCP_PROJECT_TASK_CHARS} characters")
    return task


def _optional_project_scope(value: object | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, field_name)


def _project_token_budget(value: object | None) -> int:
    if value is None:
        return DEFAULT_PROJECT_CONTEXT_TOKENS
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("max_tokens must be an integer")
    if value < MIN_PROJECT_CONTEXT_TOKENS or value > MAX_PROJECT_CONTEXT_TOKENS:
        raise _invalid_arguments(
            f"max_tokens must be between {MIN_PROJECT_CONTEXT_TOKENS} and {MAX_PROJECT_CONTEXT_TOKENS}"
        )
    return value


def _project_depth(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("depth must be an integer")
    if value < 0 or value > MAX_PROJECT_CONTEXT_DEPTH:
        raise _invalid_arguments(f"depth must be between 0 and {MAX_PROJECT_CONTEXT_DEPTH}")
    return value


def _project_limit(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _invalid_arguments("limit must be an integer")
    if value < 1 or value > MAX_PROJECT_CONTEXT_LIMIT:
        raise _invalid_arguments(f"limit must be between 1 and {MAX_PROJECT_CONTEXT_LIMIT}")
    return value


def _project_scope_error(exc: ValueError) -> McpProtocolError:
    raw_message = str(exc)
    code, _, detail = raw_message.partition(";")
    if raw_message.startswith("missing project binding"):
        code = "scope_required"
        detail = "An explicit repository-to-Vault binding is required."
    recovery_hint = (
        "Register a repository and bind it to its Vault with `vg project bind`, then pass repository_id."
        if code == "scope_required"
        else "Pass a registered repository_id or a path inside one registered repository."
    )
    return McpProtocolError(
        kind="invalid_parameter",
        payload=McpErrorPayload(
            code=code,
            message=detail.strip() or "A registered, explicitly bound repository scope is required.",
            severity="error",
            affected_vault_ids=(),
            recovery_hint=recovery_hint,
        ),
    )


def _is_project_scope_error(exc: ValueError) -> bool:
    message = str(exc)
    return message.startswith(
        (
            "scope_required",
            "unregistered_project_path",
            "conflicting_project_scope",
            "missing project binding",
        )
    )


def _bounded_project_context_body(
    *,
    payload: dict[str, object],
    resource_links: tuple[McpResourceLink, ...],
    warnings: tuple[McpErrorPayload, ...],
    text: str,
    max_tokens: int,
) -> McpToolBody:
    """Fit the whole MCP envelope, not just the nested project-context DTO."""

    selected_links = list(resource_links)
    selected_warnings = list(warnings)
    selected_text = text
    body = _project_context_body(payload, selected_links, selected_warnings, selected_text)
    if _estimate_mcp_body_tokens(body) <= max_tokens:
        return body

    selected_text = "Project context: see structured payload."
    body = _project_context_body(payload, selected_links, selected_warnings, selected_text)
    while selected_links and _estimate_mcp_body_tokens(body) > max_tokens:
        selected_links.pop()
        body = _project_context_body(payload, selected_links, selected_warnings, selected_text)
    while selected_warnings and _estimate_mcp_body_tokens(body) > max_tokens:
        selected_warnings.pop()
        body = _project_context_body(payload, selected_links, selected_warnings, selected_text)
    while _estimate_mcp_body_tokens(body) > max_tokens and _trim_project_context_payload(payload):
        body = _project_context_body(payload, selected_links, selected_warnings, selected_text)
    if _estimate_mcp_body_tokens(body) > max_tokens:
        raise _invalid_arguments("project context cannot fit the requested max_tokens")
    return body


def _project_context_body(
    payload: dict[str, object],
    resource_links: list[McpResourceLink],
    warnings: list[McpErrorPayload],
    text: str,
) -> McpToolBody:
    return McpToolBody(
        tool_name="explore_project",
        payload=payload,
        resource_links=tuple(resource_links),
        warnings=tuple(warnings),
        text=text,
    )


def _estimate_mcp_body_tokens(body: McpToolBody) -> int:
    serialized = json.dumps(body.to_json_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return max(1, (len(serialized) + 3) // 4)


def _trim_project_context_payload(payload: dict[str, object]) -> bool:
    for field_name in ("warnings", "relations", "impact_evidence", "test_evidence"):
        if _drop_last_payload_item(payload, field_name, keep=0):
            return True
    for field_name in ("code_evidence", "vault_evidence"):
        if _drop_last_payload_item(payload, field_name, keep=1):
            return True
    binding = payload.get("binding")
    if isinstance(binding, dict) and _drop_last_mapping_item(binding, "evidence_mappings"):
        return True
    for field_name in ("code_evidence", "vault_evidence", "authority_freshness"):
        if _drop_last_payload_item(payload, field_name, keep=0):
            return True
    return False


def _drop_last_payload_item(payload: dict[str, object], field_name: str, *, keep: int) -> bool:
    values = payload.get(field_name)
    if not isinstance(values, tuple | list) or len(values) <= keep:
        return False
    payload[field_name] = values[:-1]
    return True


def _drop_last_mapping_item(mapping: dict[object, object], field_name: str) -> bool:
    values = mapping.get(field_name)
    if not isinstance(values, tuple | list) or not values:
        return False
    mapping[field_name] = values[:-1]
    return True


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
