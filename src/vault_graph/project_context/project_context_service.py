"""Application service that composes bounded code and Vault evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

from vault_graph.code_index.code_models import (
    CodeImpactRequest,
    CodeSearchResponse,
    CodeSymbolHit,
    CodeSymbolRequest,
    CodeSymbolResponse,
    CodeSymbolSearchRequest,
    CodeTraversalResponse,
)
from vault_graph.context.context_pack import ContextPack, ContextPackBudget, ContextPackRequest
from vault_graph.errors import VaultGraphError
from vault_graph.ingestion.vault_catalog import DEFAULT_CONTENT_SCOPES, QueryScope, VaultCatalog
from vault_graph.project_context.project_binding import ProjectBinding
from vault_graph.project_context.project_binding_catalog import ProjectBindingCatalog
from vault_graph.project_context.project_context_models import (
    ProjectAuthorityFreshness,
    ProjectContext,
    ProjectContextBudget,
    ProjectContextRequest,
    ProjectContextWarning,
    ProjectEvidence,
    ProjectEvidenceRelation,
    ProjectFreshness,
    combine_freshness,
    estimate_project_context_tokens,
)
from vault_graph.retrieval.graph_retrieval import GraphOutputFormat
from vault_graph.retrieval.search_response import SearchOutputFormat


class RepositoryEntry(Protocol):
    @property
    def repository_id(self) -> str: ...

    @property
    def root_path(self) -> Path: ...


class ProjectRepositoryCatalog(Protocol):
    def entries(self) -> tuple[RepositoryEntry, ...]: ...

    def resolve(self, repository_id: str) -> RepositoryEntry: ...


class ProjectCodeQueryService(Protocol):
    def search_symbols(self, request: CodeSymbolSearchRequest) -> CodeSearchResponse: ...

    def get_symbol(self, request: CodeSymbolRequest) -> CodeSymbolResponse: ...

    def get_impact(self, request: CodeImpactRequest) -> CodeTraversalResponse: ...


class ProjectContextPackBuilder(Protocol):
    def build(self, request: ContextPackRequest) -> ContextPack: ...


class ProjectVaultRetrievalService(Protocol):
    def search(
        self,
        *,
        query_text: str,
        requested_scope: QueryScope,
        limit: int = 10,
        output_format: SearchOutputFormat = "json",
        include_graph: bool = False,
        include_cross_vault: bool = False,
    ) -> object: ...


class ProjectVaultGraphService(Protocol):
    def related(
        self,
        *,
        target: str,
        requested_scope: QueryScope,
        depth: int = 1,
        direction: str = "both",
        relationship_types: tuple[str, ...] = (),
        include_cross_vault: bool = False,
        limit: int = 10,
        output_format: GraphOutputFormat = "json",
    ) -> object: ...


class ProjectVaultStatusService(Protocol):
    def status(self, vault_ids: tuple[str, ...]) -> tuple[ProjectAuthorityFreshness, ...]: ...


class VaultIndexStatusReader(Protocol):
    def status(self, *, scope: QueryScope | None = None) -> object: ...


class IndexStatusVaultFreshness:
    """Stable adapter from the read-only Vault status boundary to project freshness."""

    def __init__(self, *, catalog: VaultCatalog, status_reader: VaultIndexStatusReader) -> None:
        self._catalog = catalog
        self._status_reader = status_reader

    def status(self, vault_ids: tuple[str, ...]) -> tuple[ProjectAuthorityFreshness, ...]:
        statuses: list[ProjectAuthorityFreshness] = []
        for vault_id in vault_ids:
            entry = self._catalog.resolve(vault_id)
            try:
                report = self._status_reader.status(
                    scope=QueryScope(vault_ids=(vault_id,), content_scopes=entry.content_scopes)
                )
            except (OSError, VaultGraphError, ValueError):
                statuses.append(ProjectAuthorityFreshness("vault", vault_id, "unavailable"))
                continue
            state, warnings = _vault_freshness_from_status(report)
            statuses.append(
                ProjectAuthorityFreshness(
                    "vault",
                    vault_id,
                    state,
                    revision=getattr(report, "graph_last_success_revision", None),
                    warnings=warnings,
                )
            )
        return tuple(statuses)


class ProjectGraphRelationLookup(Protocol):
    def find_relations(
        self,
        *,
        task: str,
        repository_id: str,
        vault_ids: tuple[str, ...],
        content_scopes: tuple[str, ...],
        code_evidence: tuple[ProjectEvidence, ...],
        vault_evidence: tuple[ProjectEvidence, ...],
    ) -> tuple[ProjectEvidenceRelation, ...]: ...


class VaultGraphRelationLookup:
    """Use read-only Vault retrieval/graph adapters without merging authorities."""

    def __init__(
        self,
        *,
        retrieval_service: ProjectVaultRetrievalService,
        graph_service: ProjectVaultGraphService,
    ) -> None:
        self._retrieval_service = retrieval_service
        self._graph_service = graph_service

    def find_relations(
        self,
        *,
        task: str,
        repository_id: str,
        vault_ids: tuple[str, ...],
        content_scopes: tuple[str, ...],
        code_evidence: tuple[ProjectEvidence, ...],
        vault_evidence: tuple[ProjectEvidence, ...],
    ) -> tuple[ProjectEvidenceRelation, ...]:
        if not code_evidence or not vault_evidence:
            return ()
        scope = QueryScope(vault_ids=vault_ids, content_scopes=content_scopes)
        try:
            retrieval = self._retrieval_service.search(
                query_text=task, requested_scope=scope, limit=1, output_format="json"
            )
            graph = self._graph_service.related(
                target=task, requested_scope=scope, depth=1, limit=1, output_format="json"
            )
        except (OSError, VaultGraphError, ValueError):
            return (
                ProjectEvidenceRelation(
                    code_evidence_id=code_evidence[0].evidence_id,
                    vault_evidence_id=vault_evidence[0].evidence_id,
                    status="unresolved",
                    reason="Vault graph lookup is unavailable; no stable cross-authority identifier was resolved.",
                ),
            )
        resolved_vault_ids = _vault_evidence_ids_from_response(retrieval) | _vault_evidence_ids_from_response(graph)
        relations: list[ProjectEvidenceRelation] = []
        for code in code_evidence:
            stable_ids = {
                reason.removeprefix("vault-evidence:")
                for reason in code.reasons
                if reason.startswith("vault-evidence:")
            }
            for vault in vault_evidence:
                if vault.evidence_id in stable_ids and vault.evidence_id in resolved_vault_ids:
                    relations.append(
                        ProjectEvidenceRelation(
                            code_evidence_id=code.evidence_id,
                            vault_evidence_id=vault.evidence_id,
                            status="stated",
                            reason="Explicit stable evidence identifier configured on code evidence.",
                        )
                    )
        if relations:
            return tuple(sorted(relations, key=lambda item: (item.code_evidence_id, item.vault_evidence_id)))
        reason = (
            "An explicit mapping did not appear in selected Vault retrieval or graph evidence."
            if any(reason.startswith("vault-evidence:") for reason in code_evidence[0].reasons)
            else "No stable code-to-Vault identifier or explicit mapping is configured."
        )
        return (
            ProjectEvidenceRelation(
                code_evidence_id=code_evidence[0].evidence_id,
                vault_evidence_id=vault_evidence[0].evidence_id,
                status="unresolved",
                reason=reason,
            ),
        )


class ProjectContextService:
    """Return working context without giving either authority durable priority."""

    def __init__(
        self,
        *,
        repository_catalog: ProjectRepositoryCatalog,
        binding_catalog: ProjectBindingCatalog,
        context_pack_builder: ProjectContextPackBuilder,
        vault_status_service: ProjectVaultStatusService,
        code_query_service: ProjectCodeQueryService | None = None,
        graph_relation_lookup: ProjectGraphRelationLookup | None = None,
    ) -> None:
        self._repository_catalog = repository_catalog
        self._binding_catalog = binding_catalog
        self._code_query_service = code_query_service
        self._context_pack_builder = context_pack_builder
        self._vault_status_service = vault_status_service
        self._graph_relation_lookup = graph_relation_lookup

    def build(self, request: ProjectContextRequest) -> ProjectContext:
        """Compose deterministic, bounded evidence for one explicit project scope."""

        repository = self._resolve_repository(request)
        binding = self._binding_catalog.resolve(repository.repository_id)
        vault_scope = QueryScope(
            vault_ids=binding.vault_ids,
            content_scopes=binding.content_scopes or DEFAULT_CONTENT_SCOPES,
        )
        vault_freshness = self._vault_status_service.status(binding.vault_ids)
        self._validate_vault_statuses(binding=binding, statuses=vault_freshness)
        warnings: list[ProjectContextWarning] = []
        code_evidence: tuple[ProjectEvidence, ...] = ()
        impact_evidence: tuple[ProjectEvidence, ...] = ()
        test_evidence: tuple[ProjectEvidence, ...] = ()
        code_freshness: ProjectFreshness = "unavailable"
        if self._code_query_service is None:
            warnings.append(
                ProjectContextWarning(
                    code="code_index_unavailable",
                    message="Code projection is unavailable; Vault evidence is returned without code evidence.",
                    freshness="unavailable",
                    authority_id=repository.repository_id,
                    recovery_hint="Run `vg code index --repository-id <repository-id>`.",
                )
            )
        else:
            (
                code_evidence,
                impact_evidence,
                test_evidence,
                code_freshness,
                code_warnings,
            ) = self._code_evidence(request, repository.repository_id, binding)
            warnings.extend(code_warnings)
        vault_evidence, vault_warnings = self._vault_evidence(request, vault_scope, vault_freshness)
        warnings.extend(vault_warnings)
        authority_freshness = (
            ProjectAuthorityFreshness("code", repository.repository_id, code_freshness),
            *tuple(sorted(vault_freshness, key=lambda item: item.authority_id)),
        )
        relations = self._relations(
            request=request,
            binding=binding,
            code_evidence=code_evidence,
            vault_evidence=vault_evidence,
            warnings=warnings,
        )
        return _fit_context_budget(
            task=_display_task(request.task, request.max_tokens),
            repository_id=repository.repository_id,
            binding=binding,
            freshness=combine_freshness(tuple(item.state for item in authority_freshness)),
            code_evidence=code_evidence,
            impact_evidence=impact_evidence,
            test_evidence=test_evidence,
            vault_evidence=vault_evidence,
            relations=relations,
            authority_freshness=authority_freshness,
            warnings=tuple(sorted(warnings, key=lambda item: (item.code, item.authority_id or ""))),
            max_tokens=request.max_tokens,
        )

    def _resolve_repository(self, request: ProjectContextRequest) -> RepositoryEntry:
        repository_from_id = (
            self._repository_catalog.resolve(request.repository_id) if request.repository_id is not None else None
        )
        repository_from_path = (
            self._repository_for_path(request.project_path) if request.project_path is not None else None
        )
        if repository_from_id is not None and repository_from_path is not None:
            if repository_from_id.repository_id != repository_from_path.repository_id:
                raise ValueError("conflicting_project_scope; use one registered repository scope")
            return repository_from_id
        if repository_from_id is not None:
            return repository_from_id
        if repository_from_path is not None:
            return repository_from_path
        candidates = tuple(
            entry
            for entry in self._repository_catalog.entries()
            if _has_binding(self._binding_catalog, entry.repository_id)
        )
        if len(candidates) == 1:
            return candidates[0]
        accepted = ", ".join(sorted(item.repository_id for item in candidates)) or "none"
        raise ValueError(f"scope_required; select a bound repository_id ({accepted})")

    def _repository_for_path(self, project_path: str) -> RepositoryEntry:
        try:
            candidate = Path(project_path).expanduser().resolve(strict=True)
        except OSError as exc:
            raise ValueError("unregistered_project_path; provide a registered repository_id") from exc
        matches = tuple(
            entry for entry in self._repository_catalog.entries() if _contains_path(entry.root_path, candidate)
        )
        if len(matches) != 1:
            raise ValueError("unregistered_project_path; provide a registered repository_id")
        return matches[0]

    def _code_evidence(
        self, request: ProjectContextRequest, repository_id: str, binding: ProjectBinding
    ) -> tuple[
        tuple[ProjectEvidence, ...],
        tuple[ProjectEvidence, ...],
        tuple[ProjectEvidence, ...],
        ProjectFreshness,
        tuple[ProjectContextWarning, ...],
    ]:
        assert self._code_query_service is not None
        max_symbol_work = _bounded_symbol_work(request)
        try:
            response = self._code_query_service.search_symbols(
                CodeSymbolSearchRequest(
                    query_text=request.task,
                    repository_ids=(repository_id,),
                    limit=max_symbol_work,
                    output_format="json",
                )
            )
        except (OSError, VaultGraphError, ValueError):
            return (
                (),
                (),
                (),
                "unavailable",
                (
                    ProjectContextWarning(
                        code="code_index_unavailable",
                        message=(
                            "Code projection could not be queried; Vault evidence is returned without code evidence."
                        ),
                        freshness="unavailable",
                        authority_id=repository_id,
                        recovery_hint="Run `vg code index --repository-id <repository-id>`.",
                    ),
                ),
            )
        warnings = tuple(
            ProjectContextWarning(
                code="code_projection_warning",
                message=warning,
                freshness=response.freshness,
                authority_id=repository_id,
            )
            for warning in sorted(set(response.warnings))
        )
        evidence: list[ProjectEvidence] = []
        impacts: list[ProjectEvidence] = []
        tests: list[ProjectEvidence] = []
        freshnesses: list[ProjectFreshness] = [response.freshness]
        for hit in sorted(
            response.results,
            key=lambda item: (item.repository_id, item.relative_path, item.start_line, item.symbol_id),
        )[:max_symbol_work]:
            source_uri, live_warnings = self._live_source_uri(hit.symbol_id, hit.repository_id, hit.relative_path)
            source_freshness = _freshness_for_live_source(response.freshness, live_warnings)
            freshnesses.append(source_freshness)
            warnings += tuple(
                ProjectContextWarning(
                    code=warning,
                    message="Current source differs from, or is unavailable for, the selected code projection.",
                    freshness=source_freshness,
                    authority_id=hit.repository_id,
                )
                for warning in live_warnings
            )
            mapping = dict(binding.evidence_mappings).get(f"code:{hit.symbol_id}")
            reasons = ("code_symbol_match", f"vault-evidence:{mapping}") if mapping else ("code_symbol_match",)
            evidence.append(
                ProjectEvidence(
                    evidence_id=f"code:{hit.symbol_id}",
                    authority="code",
                    title=hit.qualified_name,
                    summary=hit.signature or hit.kind,
                    relationship_status="stated",
                    revision=hit.source_revision,
                    freshness=source_freshness,
                    source_uri=source_uri,
                    repository_id=hit.repository_id,
                    relative_path=hit.relative_path,
                    start_line=hit.start_line,
                    end_line=hit.end_line,
                    reasons=reasons,
                )
            )
            impact, related_tests, impact_freshness, impact_warnings = self._impact_evidence(
                symbol_id=hit.symbol_id,
                repository_id=hit.repository_id,
                depth=request.depth,
                limit=max_symbol_work,
            )
            impacts.extend(impact)
            tests.extend(related_tests)
            freshnesses.append(impact_freshness)
            warnings += impact_warnings
        return (
            tuple(evidence),
            tuple(_unique_evidence(impacts)),
            tuple(_unique_evidence(tests)),
            combine_freshness(tuple(freshnesses)),
            warnings,
        )

    def _impact_evidence(
        self,
        *,
        symbol_id: str,
        repository_id: str,
        depth: int,
        limit: int,
    ) -> tuple[
        tuple[ProjectEvidence, ...], tuple[ProjectEvidence, ...], ProjectFreshness, tuple[ProjectContextWarning, ...]
    ]:
        assert self._code_query_service is not None
        try:
            response = self._code_query_service.get_impact(
                CodeImpactRequest(
                    symbol_id=symbol_id,
                    repository_id=repository_id,
                    depth=depth,
                    limit=limit,
                    output_format="json",
                )
            )
        except (OSError, VaultGraphError, ValueError):
            return (
                (),
                (),
                "partial",
                (
                    ProjectContextWarning(
                        code="code_impact_unavailable",
                        message="Code impact traversal is unavailable for a selected symbol.",
                        freshness="partial",
                        authority_id=repository_id,
                    ),
                ),
            )
        traversal = response.result
        warnings = tuple(
            ProjectContextWarning(
                code="code_impact_warning",
                message=warning,
                freshness=traversal.freshness,
                authority_id=repository_id,
            )
            for warning in sorted(set(traversal.warnings))
        )
        impacts: list[ProjectEvidence] = []
        tests: list[ProjectEvidence] = []
        freshnesses: list[ProjectFreshness] = [traversal.freshness]
        for hit in sorted(
            traversal.hits,
            key=lambda item: (item.repository_id, item.relative_path, item.start_line, item.symbol_id),
        )[:limit]:
            source_uri, source_warnings = self._live_source_uri(hit.symbol_id, hit.repository_id, hit.relative_path)
            item_freshness = _freshness_for_live_source(traversal.freshness, source_warnings)
            freshnesses.append(item_freshness)
            warnings += tuple(
                ProjectContextWarning(
                    code=warning,
                    message="Current source differs from, or is unavailable for, the selected code projection.",
                    freshness=item_freshness,
                    authority_id=hit.repository_id,
                )
                for warning in source_warnings
            )
            item = _code_evidence_from_hit(
                hit=hit,
                source_uri=source_uri,
                freshness=item_freshness,
                reason="code_impact" if hit.kind != "test" else "related_test",
            )
            (tests if hit.kind == "test" else impacts).append(item)
        return tuple(impacts), tuple(tests), combine_freshness(tuple(freshnesses)), warnings

    def _live_source_uri(
        self, symbol_id: str, repository_id: str, relative_path: str
    ) -> tuple[str | None, tuple[str, ...]]:
        assert self._code_query_service is not None
        try:
            response = self._code_query_service.get_symbol(
                CodeSymbolRequest(
                    symbol_id=symbol_id,
                    repository_id=repository_id,
                    relative_path=relative_path,
                    include_source=True,
                    max_lines=1,
                    output_format="json",
                )
            )
        except (OSError, VaultGraphError, ValueError):
            return None, ("source_unavailable",)
        return response.source_uri, tuple(sorted(set(response.warnings)))

    def _vault_evidence(
        self,
        request: ProjectContextRequest,
        scope: QueryScope,
        authority_freshness: tuple[ProjectAuthorityFreshness, ...],
    ) -> tuple[tuple[ProjectEvidence, ...], tuple[ProjectContextWarning, ...]]:
        try:
            pack = self._context_pack_builder.build(
                ContextPackRequest(
                    goal=request.task,
                    requested_scope=scope,
                    budget=ContextPackBudget(max_tokens=request.max_tokens),
                    retrieval_limit=request.limit,
                )
            )
        except (OSError, VaultGraphError, ValueError):
            return (), (
                ProjectContextWarning(
                    code="vault_context_unavailable",
                    message="Vault context could not be assembled for the selected authority scope.",
                    freshness="unavailable",
                    recovery_hint="Run `vg index` for the selected Vault.",
                ),
            )
        evidence: list[ProjectEvidence] = []
        freshness_by_vault = {
            item.authority_id: item.state for item in authority_freshness if item.authority == "vault"
        }
        for item in sorted(
            pack.evidence,
            key=lambda item: (item.ref.vault_id, item.ref.document_id, item.ref.chunk_id),
        ):
            uri = _vault_uri(item.ref.vault_id, item.path)
            evidence.append(
                ProjectEvidence(
                    evidence_id=f"vault:{item.ref.vault_id}:{item.ref.document_id}:{item.ref.chunk_id}",
                    authority="vault",
                    title=item.section or item.path,
                    summary=item.anchor or item.path,
                    relationship_status="not_applicable",
                    revision=item.vault_revision or item.metadata_index_revision,
                    freshness=freshness_by_vault.get(item.ref.vault_id, "unknown"),
                    source_uri=uri,
                    vault_id=item.ref.vault_id,
                    relative_path=item.path,
                    reasons=tuple(item.retrieval_reasons),
                )
            )
        warnings = tuple(
            ProjectContextWarning(
                code=getattr(item, "code", "vault_context_warning"),
                message=getattr(item, "message", "Vault context emitted a warning."),
                freshness="unknown",
            )
            for item in pack.warnings
        )
        return tuple(evidence), warnings

    def _relations(
        self,
        *,
        request: ProjectContextRequest,
        binding: ProjectBinding,
        code_evidence: tuple[ProjectEvidence, ...],
        vault_evidence: tuple[ProjectEvidence, ...],
        warnings: list[ProjectContextWarning],
    ) -> tuple[ProjectEvidenceRelation, ...]:
        if self._graph_relation_lookup is None:
            return ()
        known_code = {item.evidence_id for item in code_evidence}
        known_vault = {item.evidence_id for item in vault_evidence}
        relations = self._graph_relation_lookup.find_relations(
            task=request.task,
            repository_id=binding.repository_id,
            vault_ids=binding.vault_ids,
            content_scopes=binding.content_scopes or DEFAULT_CONTENT_SCOPES,
            code_evidence=code_evidence,
            vault_evidence=vault_evidence,
        )
        allowed = tuple(
            relation
            for relation in relations
            if relation.code_evidence_id in known_code and relation.vault_evidence_id in known_vault
        )
        if len(allowed) != len(relations):
            warnings.append(
                ProjectContextWarning(
                    code="unresolved_cross_authority_relation",
                    message="A cross-authority relation did not resolve to selected evidence.",
                    freshness="unknown",
                )
            )
        return tuple(sorted(allowed, key=lambda item: (item.code_evidence_id, item.vault_evidence_id, item.status)))

    @staticmethod
    def _validate_vault_statuses(
        *,
        binding: ProjectBinding,
        statuses: tuple[ProjectAuthorityFreshness, ...],
    ) -> None:
        actual = tuple(sorted(item.authority_id for item in statuses if item.authority == "vault"))
        if actual != tuple(sorted(binding.vault_ids)):
            raise ValueError("vault status must include every selected Vault authority")


def _has_binding(catalog: ProjectBindingCatalog, repository_id: str) -> bool:
    try:
        catalog.resolve(repository_id)
    except ValueError:
        return False
    return True


def _fit_context_budget(
    *,
    task: str,
    repository_id: str,
    binding: ProjectBinding,
    freshness: ProjectFreshness,
    code_evidence: tuple[ProjectEvidence, ...],
    impact_evidence: tuple[ProjectEvidence, ...],
    test_evidence: tuple[ProjectEvidence, ...],
    vault_evidence: tuple[ProjectEvidence, ...],
    relations: tuple[ProjectEvidenceRelation, ...],
    authority_freshness: tuple[ProjectAuthorityFreshness, ...],
    warnings: tuple[ProjectContextWarning, ...],
    max_tokens: int,
) -> ProjectContext:
    kept_code: list[ProjectEvidence] = []
    kept_impact: list[ProjectEvidence] = []
    kept_tests: list[ProjectEvidence] = []
    kept_vault: list[ProjectEvidence] = []
    kept_relations: list[ProjectEvidenceRelation] = []
    kept_warnings: list[ProjectContextWarning] = []
    omitted = 0

    def context() -> ProjectContext:
        return ProjectContext(
            task=task,
            repository_id=repository_id,
            binding=binding,
            freshness=freshness,
            code_evidence=tuple(kept_code),
            impact_evidence=tuple(kept_impact),
            test_evidence=tuple(kept_tests),
            vault_evidence=tuple(kept_vault),
            relations=tuple(kept_relations),
            authority_freshness=authority_freshness,
            warnings=tuple(kept_warnings),
            budget=ProjectContextBudget(max_tokens=max_tokens, used_tokens=max_tokens, omitted_evidence=omitted),
        )

    for collection, candidates in (
        (kept_code, code_evidence),
        (kept_impact, impact_evidence),
        (kept_tests, test_evidence),
        (kept_vault, vault_evidence),
    ):
        for candidate in candidates:
            collection.append(candidate)
            if estimate_project_context_tokens(context()) > max_tokens:
                collection.pop()
                omitted += 1
    selected_ids = {item.evidence_id for item in (*kept_code, *kept_impact, *kept_tests, *kept_vault)}
    for relation in relations:
        if relation.code_evidence_id not in selected_ids or relation.vault_evidence_id not in selected_ids:
            omitted += 1
            continue
        kept_relations.append(relation)
        if estimate_project_context_tokens(context()) > max_tokens:
            kept_relations.pop()
            omitted += 1
    for warning in warnings:
        kept_warnings.append(warning)
        if estimate_project_context_tokens(context()) > max_tokens:
            kept_warnings.pop()
            omitted += 1
    provisional = context()
    actual_tokens = estimate_project_context_tokens(provisional)
    return replace(
        provisional,
        budget=ProjectContextBudget(max_tokens=max_tokens, used_tokens=actual_tokens, omitted_evidence=omitted),
    )


def _display_task(task: str, max_tokens: int) -> str:
    return task[: max(64, max_tokens * 2)]


def _code_evidence_from_hit(
    *, hit: CodeSymbolHit, source_uri: str | None, freshness: ProjectFreshness, reason: str
) -> ProjectEvidence:
    return ProjectEvidence(
        evidence_id=f"code:{hit.symbol_id}",
        authority="code",
        title=hit.qualified_name,
        summary=hit.signature or hit.kind,
        relationship_status="stated",
        revision=hit.source_revision,
        freshness=freshness,
        source_uri=source_uri,
        repository_id=hit.repository_id,
        relative_path=hit.relative_path,
        start_line=hit.start_line,
        end_line=hit.end_line,
        reasons=(reason,),
    )


def _unique_evidence(evidence: list[ProjectEvidence]) -> tuple[ProjectEvidence, ...]:
    return tuple({item.evidence_id: item for item in evidence}.values())


def _freshness_for_live_source(base: ProjectFreshness, warnings: tuple[str, ...]) -> ProjectFreshness:
    if any(warning.startswith("source_unavailable") for warning in warnings):
        return "unavailable"
    if any(warning.startswith("source_changed_since_index") for warning in warnings):
        return combine_freshness((base, "stale"))
    return base


def _bounded_symbol_work(request: ProjectContextRequest) -> int:
    """Bound source/impact reads before live work based on the requested output budget."""

    return min(request.limit, max(1, request.max_tokens // 64), 20)


def _vault_freshness_from_status(report: object) -> tuple[ProjectFreshness, tuple[str, ...]]:
    """Map metadata, vector, and graph status without concealing a degraded authority."""

    if not bool(getattr(report, "metadata_ok", False)) or not bool(
        getattr(report, "metadata_schema_compatible", False)
    ):
        return "unavailable", ("metadata_unavailable",)
    states: list[ProjectFreshness] = ["fresh"]
    warnings: list[str] = []
    if not bool(getattr(report, "vector_schema_compatible", False)):
        states.append("unavailable")
        warnings.append("vector_schema_incompatible")
    elif not bool(getattr(report, "vector_ok", False)):
        states.append("partial")
        warnings.append("vector_unavailable")
    elif int(getattr(report, "vector_stale_count", 0)) > 0:
        states.append("stale")
        warnings.append("vector_stale")
    elif getattr(report, "vector_last_error", None):
        states.append("partial")
        warnings.append("vector_last_error")
    graph = getattr(report, "graph_readiness", None)
    graph_state = str(getattr(graph, "freshness", "unknown"))
    graph_map: dict[str, ProjectFreshness] = {
        "fresh": "fresh",
        "stale": "stale",
        "syncing": "syncing",
        "partial": "partial",
        "unknown": "unknown",
        "unavailable": "unavailable",
        "incompatible": "unavailable",
        "missing": "unknown",
        "empty": "unknown",
    }
    states.append(graph_map.get(graph_state, "unknown"))
    if graph_map.get(graph_state, "unknown") != "fresh":
        warnings.append(f"graph_{graph_state}")
    if getattr(report, "graph_last_error", None):
        states.append("partial")
        warnings.append("graph_last_error")
    return combine_freshness(tuple(states)), tuple(warnings)


def _vault_uri(vault_id: str, path: str) -> str | None:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    return f"vault://{quote(vault_id, safe='')}/{quote(candidate.as_posix(), safe='/')}"


def _vault_evidence_ids_from_response(response: object) -> set[str]:
    """Read only stable Vault evidence identities from retrieval/graph response DTOs."""

    ids: set[str] = set()
    for item in (*tuple(getattr(response, "results", ())), *tuple(getattr(response, "items", ()))):
        for evidence in tuple(getattr(item, "evidence", ())):
            vault_id = getattr(evidence, "vault_id", None)
            document_id = getattr(evidence, "document_id", None)
            chunk_id = getattr(evidence, "chunk_id", None)
            if all(isinstance(value, str) and value for value in (vault_id, document_id, chunk_id)):
                ids.add(f"vault:{vault_id}:{document_id}:{chunk_id}")
    return ids


def _contains_path(root_path: Path, candidate: Path) -> bool:
    root = root_path.expanduser().resolve()
    return candidate == root or root in candidate.parents


__all__ = [
    "ProjectCodeQueryService",
    "ProjectContextPackBuilder",
    "ProjectContextService",
    "ProjectGraphRelationLookup",
    "ProjectRepositoryCatalog",
    "ProjectVaultStatusService",
    "IndexStatusVaultFreshness",
    "ProjectVaultRetrievalService",
    "ProjectVaultGraphService",
    "VaultGraphRelationLookup",
]
