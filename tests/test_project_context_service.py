from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from vault_graph.code_index.code_models import (
    CodeImpactRequest,
    CodeSearchResponse,
    CodeSymbolHit,
    CodeSymbolResponse,
    CodeTraversalResponse,
    CodeTraversalResult,
)
from vault_graph.context import ContextPack
from vault_graph.project_context import (
    ProjectAuthorityFreshness,
    ProjectBinding,
    ProjectContextRequest,
    ProjectFreshness,
)
from vault_graph.project_context.project_context_service import ProjectContextService, VaultGraphRelationLookup


@dataclass(frozen=True)
class _Repository:
    repository_id: str
    root_path: Path


class _Repositories:
    def __init__(self, root: Path) -> None:
        self.entry = _Repository("demo", root.resolve())

    def entries(self) -> tuple[_Repository, ...]:
        return (self.entry,)

    def resolve(self, repository_id: str) -> _Repository:
        if repository_id != "demo":
            raise ValueError(f"unknown repository_id: {repository_id}")
        return self.entry


class _Bindings:
    def entries(self) -> tuple[ProjectBinding, ...]:
        return (ProjectBinding("demo", ("vault",), ("wiki",)),)

    def resolve(self, repository_id: str) -> ProjectBinding:
        if repository_id != "demo":
            raise ValueError(f"missing project binding for repository_id: {repository_id}")
        return self.entries()[0]


class _Code:
    def search_symbols(self, request: object) -> CodeSearchResponse:
        return CodeSearchResponse(
            query_text="task",
            results=(
                CodeSymbolHit(
                    symbol_id="symbol-1",
                    repository_id="demo",
                    file_id="file-1",
                    relative_path="src/demo.py",
                    kind="function",
                    language_kind="function_definition",
                    name="run",
                    qualified_name="run",
                    signature="def run()",
                    start_line=3,
                    end_line=5,
                ),
            ),
            freshness="fresh",
        )

    def get_symbol(self, request: object) -> CodeSymbolResponse:
        return CodeSymbolResponse(
            symbol=None,
            freshness="fresh",
            source_uri="vg-source://demo/src/demo.py#L3-L5",
            source_relative_path="src/demo.py",
            source_lines=("must not appear in project context",),
        )

    def get_impact(self, request: CodeImpactRequest) -> CodeTraversalResponse:
        return CodeTraversalResponse(
            CodeTraversalResult(
                root_symbol_id="symbol-1",
                direction="inbound",
                hits=(
                    CodeSymbolHit(
                        symbol_id="caller-1",
                        repository_id="demo",
                        file_id="file-2",
                        relative_path="src/caller.py",
                        kind="function",
                        language_kind="function_definition",
                        name="caller",
                        qualified_name="caller",
                        signature="def caller()",
                        start_line=7,
                        end_line=9,
                    ),
                    CodeSymbolHit(
                        symbol_id="test-1",
                        repository_id="demo",
                        file_id="file-3",
                        relative_path="tests/test_demo.py",
                        kind="test",
                        language_kind="function_definition",
                        name="test_run",
                        qualified_name="test_run",
                        signature="def test_run()",
                        start_line=3,
                        end_line=6,
                    ),
                ),
                freshness="fresh",
            )
        )


@dataclass(frozen=True)
class _Ref:
    vault_id: str
    document_id: str
    chunk_id: str


@dataclass(frozen=True)
class _VaultEvidence:
    ref: _Ref
    path: str
    section: str | None
    anchor: str | None
    content_hash: str
    metadata_index_revision: str
    vault_revision: str | None
    retrieval_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _Pack:
    evidence: tuple[_VaultEvidence, ...]
    warnings: tuple[object, ...] = ()


class _ContextPacks:
    def build(self, request: object) -> ContextPack:
        return cast(
            ContextPack,
            _Pack(
                evidence=(
                    _VaultEvidence(
                        ref=_Ref("vault", "decision-1", "chunk-1"),
                        path="wiki/decision.md",
                        section="Decision",
                        anchor="decision",
                        content_hash="content-hash",
                        metadata_index_revision="metadata-1",
                        vault_revision="git-1",
                        retrieval_reasons=("keyword matched",),
                    ),
                )
            ),
        )


class _VaultStatus:
    def status(self, vault_ids: tuple[str, ...]) -> tuple[ProjectAuthorityFreshness, ...]:
        return tuple(ProjectAuthorityFreshness("vault", vault_id, "fresh", revision="git-1") for vault_id in vault_ids)


def _service(
    tmp_path: Path, *, code: _Code | None = None, vault_state: ProjectFreshness = "fresh"
) -> ProjectContextService:
    repository = tmp_path / "repository"
    repository.mkdir()

    class Status(_VaultStatus):
        def status(self, vault_ids: tuple[str, ...]) -> tuple[ProjectAuthorityFreshness, ...]:
            return tuple(
                ProjectAuthorityFreshness("vault", vault_id, vault_state, revision="git-1") for vault_id in vault_ids
            )

    return ProjectContextService(
        repository_catalog=_Repositories(repository),
        binding_catalog=_Bindings(),
        code_query_service=code,
        context_pack_builder=_ContextPacks(),
        vault_status_service=Status(),
    )


def test_project_context_selects_sole_bound_repository_and_returns_compact_evidence(tmp_path: Path) -> None:
    context = _service(tmp_path, code=_Code()).build(ProjectContextRequest(task="Find the implementation"))

    assert context.repository_id == "demo"
    assert context.freshness == "fresh"
    assert context.code_evidence[0].source_uri == "vg-source://demo/src/demo.py#L3-L5"
    assert context.vault_evidence[0].source_uri == "vault://vault/wiki/decision.md"
    assert context.vault_evidence[0].freshness == "fresh"
    assert "must not appear" not in repr(context)


def test_project_context_includes_bounded_impact_and_related_test_evidence(tmp_path: Path) -> None:
    context = _service(tmp_path, code=_Code()).build(ProjectContextRequest(task="Find the implementation", depth=2))

    assert [item.evidence_id for item in context.impact_evidence] == ["code:caller-1"]
    assert [item.evidence_id for item in context.test_evidence] == ["code:test-1"]


def test_vault_graph_relation_adapter_marks_unmapped_authorities_as_unresolved(tmp_path: Path) -> None:
    calls: list[str] = []

    class Retrieval:
        def search(self, **_: object) -> object:
            calls.append("retrieval")
            return object()

    class Graph:
        def related(self, **_: object) -> object:
            calls.append("graph")
            return object()

    context = _service(tmp_path, code=_Code()).build(ProjectContextRequest(task="Find the implementation"))
    lookup = VaultGraphRelationLookup(retrieval_service=Retrieval(), graph_service=Graph())
    relations = lookup.find_relations(
        task=context.task,
        repository_id=context.repository_id,
        vault_ids=("vault",),
        code_evidence=context.code_evidence,
        vault_evidence=context.vault_evidence,
    )

    assert calls == ["retrieval", "graph"]
    assert relations[0].status == "unresolved"


def test_project_context_never_reports_fresh_when_a_selected_vault_is_stale(tmp_path: Path) -> None:
    context = _service(tmp_path, code=_Code(), vault_state="stale").build(
        ProjectContextRequest(task="Find the implementation")
    )

    assert context.freshness == "stale"


@pytest.mark.parametrize("vault_state", ["stale", "partial", "syncing", "unknown", "unavailable"])
def test_project_context_is_never_fresh_when_any_selected_authority_is_not_fresh(
    tmp_path: Path, vault_state: ProjectFreshness
) -> None:
    context = _service(tmp_path, code=_Code(), vault_state=vault_state).build(
        ProjectContextRequest(task="Find the implementation")
    )

    assert context.freshness == vault_state


def test_live_source_drift_downgrades_an_otherwise_fresh_code_authority(tmp_path: Path) -> None:
    class DriftedCode(_Code):
        def get_symbol(self, request: object) -> CodeSymbolResponse:
            return CodeSymbolResponse(symbol=None, freshness="fresh", warnings=("source_changed_since_index",))

    context = _service(tmp_path, code=DriftedCode()).build(ProjectContextRequest(task="Find the implementation"))

    assert context.authority_freshness[0].state == "stale"
    assert context.freshness == "stale"


def test_project_context_falls_back_to_vault_evidence_when_code_index_is_missing(tmp_path: Path) -> None:
    context = _service(tmp_path).build(ProjectContextRequest(task="Find the implementation"))

    assert context.code_evidence == ()
    assert context.vault_evidence
    assert {warning.code for warning in context.warnings} == {"code_index_unavailable"}


def test_project_context_applies_a_deterministic_output_budget(tmp_path: Path) -> None:
    context = _service(tmp_path, code=_Code()).build(
        ProjectContextRequest(task="Find the implementation", max_tokens=512)
    )

    assert context.budget.used_tokens <= 512
    assert context.budget.omitted_evidence == 0
