"""Application service that composes bounded code and Vault evidence."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote

from vault_graph.code_index.code_models import (
    CodeSearchResponse,
    CodeSymbolRequest,
    CodeSymbolResponse,
    CodeSymbolSearchRequest,
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
)


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


class ProjectContextPackBuilder(Protocol):
    def build(self, request: ContextPackRequest) -> ContextPack: ...


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
            fresh = bool(getattr(report, "metadata_ok", False) and getattr(report, "metadata_schema_compatible", False))
            statuses.append(
                ProjectAuthorityFreshness(
                    "vault",
                    vault_id,
                    "fresh" if fresh else "unavailable",
                    revision=getattr(report, "graph_last_success_revision", None),
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
        code_evidence: tuple[ProjectEvidence, ...],
        vault_evidence: tuple[ProjectEvidence, ...],
    ) -> tuple[ProjectEvidenceRelation, ...]: ...


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
            code_evidence, code_freshness, code_warnings = self._code_evidence(request, repository.repository_id)
            warnings.extend(code_warnings)
        vault_evidence, vault_warnings = self._vault_evidence(request, vault_scope, vault_freshness)
        warnings.extend(vault_warnings)
        code_evidence, vault_evidence, budget = _apply_budget(
            code_evidence=code_evidence,
            vault_evidence=vault_evidence,
            max_tokens=request.max_tokens,
            limit=request.limit,
        )
        relations = self._relations(
            request=request,
            binding=binding,
            code_evidence=code_evidence,
            vault_evidence=vault_evidence,
            warnings=warnings,
        )
        authority_freshness = (
            ProjectAuthorityFreshness("code", repository.repository_id, code_freshness),
            *tuple(sorted(vault_freshness, key=lambda item: item.authority_id)),
        )
        return ProjectContext(
            task=request.task,
            repository_id=repository.repository_id,
            binding=binding,
            freshness=combine_freshness(tuple(item.state for item in authority_freshness)),
            code_evidence=code_evidence,
            vault_evidence=vault_evidence,
            relations=relations,
            authority_freshness=authority_freshness,
            warnings=tuple(sorted(warnings, key=lambda item: (item.code, item.authority_id or ""))),
            budget=budget,
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
        self, request: ProjectContextRequest, repository_id: str
    ) -> tuple[tuple[ProjectEvidence, ...], ProjectFreshness, tuple[ProjectContextWarning, ...]]:
        assert self._code_query_service is not None
        try:
            response = self._code_query_service.search_symbols(
                CodeSymbolSearchRequest(
                    query_text=request.task,
                    repository_ids=(repository_id,),
                    limit=request.limit,
                    output_format="json",
                )
            )
        except (OSError, VaultGraphError, ValueError):
            return (
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
        for hit in sorted(
            response.results,
            key=lambda item: (item.repository_id, item.relative_path, item.start_line, item.symbol_id),
        ):
            source_uri, live_warnings = self._live_source_uri(hit.symbol_id, hit.repository_id, hit.relative_path)
            warnings += tuple(
                ProjectContextWarning(
                    code=warning,
                    message="Current source differs from, or is unavailable for, the selected code projection.",
                    freshness=response.freshness,
                    authority_id=hit.repository_id,
                )
                for warning in live_warnings
            )
            evidence.append(
                ProjectEvidence(
                    evidence_id=f"code:{hit.symbol_id}",
                    authority="code",
                    title=hit.qualified_name,
                    summary=hit.signature or hit.kind,
                    relationship_status="stated",
                    revision=hit.source_revision,
                    freshness=response.freshness,
                    source_uri=source_uri,
                    repository_id=hit.repository_id,
                    relative_path=hit.relative_path,
                    start_line=hit.start_line,
                    end_line=hit.end_line,
                    reasons=("code_symbol_match",),
                )
            )
        return tuple(evidence), response.freshness, warnings

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


def _apply_budget(
    *,
    code_evidence: tuple[ProjectEvidence, ...],
    vault_evidence: tuple[ProjectEvidence, ...],
    max_tokens: int,
    limit: int,
) -> tuple[tuple[ProjectEvidence, ...], tuple[ProjectEvidence, ...], ProjectContextBudget]:
    kept_code: list[ProjectEvidence] = []
    kept_vault: list[ProjectEvidence] = []
    used = 0
    omitted = 0
    for evidence in (*code_evidence, *vault_evidence):
        cost = _token_cost(evidence)
        if len(kept_code) + len(kept_vault) >= limit or used + cost > max_tokens:
            omitted += 1
            continue
        (kept_code if evidence.authority == "code" else kept_vault).append(evidence)
        used += cost
    return (
        tuple(kept_code),
        tuple(kept_vault),
        ProjectContextBudget(max_tokens=max_tokens, used_tokens=used, omitted_evidence=omitted),
    )


def _token_cost(evidence: ProjectEvidence) -> int:
    return max(1, len(f"{evidence.title} {evidence.summary}".split()))


def _vault_uri(vault_id: str, path: str) -> str | None:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        return None
    return f"vault://{quote(vault_id, safe='')}/{quote(candidate.as_posix(), safe='/')}"


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
]
