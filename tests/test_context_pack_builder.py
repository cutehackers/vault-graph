from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from vault_graph.context import (
    ContextEvidenceRef,
    ContextPackBudget,
    ContextPackRequest,
    DefaultContextPackRenderer,
)
from vault_graph.context.context_pack_builder import (
    ContextRetrievalService,
    ResolvedContextEvidence,
    SearchContextPackBuilder,
)
from vault_graph.errors import ContextPackError
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.retrieval_result import RetrievalResult, RetrievalSignal, RetrievalWarning
from vault_graph.retrieval.search_response import SearchResponse, SearchStoreRevision, SearchWarning
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


class RecordingRetrievalService:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def search(self, **kwargs: object) -> SearchResponse:
        self.calls.append(kwargs)
        return self.response


class StaticResolver:
    def __init__(self, evidence: dict[ContextEvidenceRef, ResolvedContextEvidence] | None = None) -> None:
        self.evidence = evidence or {}
        self.calls: list[ContextEvidenceRef] = []

    def resolve(self, ref: ContextEvidenceRef) -> ResolvedContextEvidence | None:
        self.calls.append(ref)
        return self.evidence.get(ref)


def fixed_clock() -> datetime:
    return datetime(2026, 6, 12, tzinfo=UTC)


def make_catalog(tmp_path: Path) -> VaultCatalog:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    return VaultCatalog.from_entries(
        entries=(
            VaultCatalogEntry.from_root(vault_id="main", root_path=first, display_name="Main Vault"),
            VaultCatalogEntry.from_root(vault_id="second", root_path=second, display_name="Second Vault"),
        ),
        active_vault_id="main",
    )


def make_evidence(
    *,
    vault_id: str = "main",
    document_id: str = "doc-1",
    chunk_id: str = "chunk-1",
    path: str = "wiki/page.md",
    metadata_revision: str = "metadata-1",
    vault_revision: str | None = "git-1",
) -> EvidenceReference:
    return EvidenceReference(
        vault_id=vault_id,
        document_id=document_id,
        chunk_id=chunk_id,
        path=path,
        section="Section",
        anchor="section",
        content_hash=f"hash-{vault_id}-{chunk_id}",
        raw_sha256=f"raw-{vault_id}-{chunk_id}",
        metadata_index_revision=metadata_revision,
        vault_revision=vault_revision,
    )


def make_resolved(
    ref: ContextEvidenceRef,
    *,
    path: str = "wiki/page.md",
    text: str = "one two three",
    token_count: int = 3,
    vault_revision: str | None = "git-1",
) -> ResolvedContextEvidence:
    return ResolvedContextEvidence(
        ref=ref,
        path=path,
        section="Section",
        anchor="section",
        content_hash=f"hash-{ref.vault_id}-{ref.chunk_id}",
        raw_sha256=f"raw-{ref.vault_id}-{ref.chunk_id}",
        metadata_index_revision="metadata-1",
        vault_revision=vault_revision,
        text=text,
        token_count=token_count,
    )


def make_result(
    *,
    rank: int = 1,
    vault_id: str = "main",
    document_id: str = "doc-1",
    chunk_id: str = "chunk-1",
    kind: str = "evidence_chunk",
    path: str = "wiki/page.md",
    warnings: tuple[RetrievalWarning, ...] = (),
    signals: tuple[RetrievalSignal, ...] | None = None,
) -> RetrievalResult:
    evidence = make_evidence(vault_id=vault_id, document_id=document_id, chunk_id=chunk_id, path=path)
    return RetrievalResult(
        result_id=f"{vault_id}:{chunk_id}:rank-{rank}",
        vault_id=vault_id,
        kind=kind,
        title=f"{path}#section",
        summary=f"Summary {rank}",
        rank=rank,
        evidence=(evidence,),
        signals=signals
        or (
            RetrievalSignal(
                kind="keyword",
                source_id=f"keyword:{vault_id}:{chunk_id}",
                rank=rank,
                score=1.0,
                backend="sqlite-fts5",
                index_revision="keyword-1",
                explanation="keyword matched",
            ),
        ),
        relationship_status="not_applicable",
        warnings=warnings,
        store_revisions=(),
    )


def make_multi_evidence_result() -> RetrievalResult:
    first = make_evidence(document_id="doc-1", chunk_id="chunk-1")
    second = make_evidence(document_id="doc-2", chunk_id="chunk-2", path="wiki/second.md")
    result = make_result()
    return replace(result, evidence=(first, second))


def make_search_response(
    *,
    results: tuple[RetrievalResult, ...] | None = None,
    warnings: tuple[SearchWarning, ...] = (),
    requested_scope: QueryScope | None = None,
    actual_scopes: tuple[QueryScope, ...] | None = None,
    store_revisions: tuple[SearchStoreRevision, ...] | None = None,
) -> SearchResponse:
    result_tuple = results if results is not None else (make_result(),)
    scope_tuple = actual_scopes if actual_scopes is not None else (QueryScope(vault_ids=("main",)),)
    response_requested_scope = requested_scope if requested_scope is not None else QueryScope(vault_ids=("main",))
    return SearchResponse(
        query_text="Build context",
        requested_scope=response_requested_scope,
        actual_scopes=scope_tuple,
        limit=10,
        result_count=len(result_tuple),
        candidate_count=len(result_tuple),
        dropped_candidate_count=0,
        results=result_tuple,
        warnings=warnings,
        degraded=bool(warnings),
        store_revisions=store_revisions
        if store_revisions is not None
        else (
            SearchStoreRevision(kind="metadata", revision="metadata-1", vault_id="main", scope_key="main:wiki:local"),
            SearchStoreRevision(kind="keyword", revision="keyword-1", vault_id="main", scope_key="main:wiki:local"),
        ),
        generated_at="2026-06-12T00:00:00+00:00",
    )


def make_builder(
    *,
    tmp_path: Path,
    response: SearchResponse,
    resolver: StaticResolver,
    clock: Callable[[], datetime] = fixed_clock,
) -> SearchContextPackBuilder:
    return SearchContextPackBuilder(
        catalog=make_catalog(tmp_path),
        retrieval_service=cast(ContextRetrievalService, RecordingRetrievalService(response)),
        evidence_resolver=resolver,
        clock=clock,
    )


def test_builder_passes_retrieval_limit_and_graph_flags(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    retrieval = RecordingRetrievalService(make_search_response())
    builder = SearchContextPackBuilder(
        catalog=make_catalog(tmp_path),
        retrieval_service=cast(ContextRetrievalService, retrieval),
        evidence_resolver=StaticResolver({ref: make_resolved(ref)}),
        clock=fixed_clock,
    )

    builder.build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            retrieval_limit=7,
            include_graph=False,
        )
    )

    assert retrieval.calls[0]["limit"] == 7
    assert retrieval.calls[0]["include_graph"] is False
    assert retrieval.calls[0]["include_cross_vault"] is False


def test_builder_preserves_graph_mode_warnings(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        warnings=(
            SearchWarning(
                code="graph_stale",
                message="Graph stale",
                severity="warning",
                affected_vault_ids=("main",),
            ),
        )
    )
    pack = make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver({ref: make_resolved(ref)})).build(
        ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)), include_graph=True)
    )

    assert [(warning.code, warning.source_code) for warning in pack.warnings] == [("graph_stale", "graph_stale")]


def test_result_level_warnings_become_item_warnings_and_markdown_visible(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        results=(make_result(warnings=(RetrievalWarning("stale_vector", "Stale vector", "warning"),)),)
    )
    pack = make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver({ref: make_resolved(ref)})).build(
        ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
    )

    assert pack.relevant_pages[0].warnings[0].code == "stale_projection"
    assert pack.relevant_pages[0].warnings[0].source_code == "stale_vector"
    assert "Stale vector" in DefaultContextPackRenderer().render_markdown(pack)


def test_truncated_excerpt_updates_budget_and_warnings(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(),
        resolver=StaticResolver({ref: make_resolved(ref, text="one two three four", token_count=4)}),
    ).build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            budget=ContextPackBudget(max_excerpt_tokens=3),
        )
    )

    assert pack.budget.used_tokens == 3
    assert pack.evidence[0].truncated is True
    assert pack.evidence[0].warnings[0].code == "excerpt_truncated"
    assert "excerpt_truncated" in [warning.code for warning in pack.warnings]


def test_budget_omission_is_aggregated_for_evidence_item_limit(tmp_path: Path) -> None:
    first = ContextEvidenceRef("main", "doc-1", "chunk-1")
    second = ContextEvidenceRef("main", "doc-2", "chunk-2")
    response = make_search_response(
        results=(
            make_result(rank=1, document_id="doc-1", chunk_id="chunk-1"),
            make_result(rank=2, document_id="doc-2", chunk_id="chunk-2"),
        )
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver({first: make_resolved(first), second: make_resolved(second)}),
    ).build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            budget=ContextPackBudget(max_evidence_items=1),
        )
    )

    assert pack.budget.omitted_items == 1
    assert [warning.code for warning in pack.warnings].count("budget_omitted") == 1


def test_budget_packing_prioritizes_decisions_before_pages(tmp_path: Path) -> None:
    page_ref = ContextEvidenceRef("main", "doc-page", "chunk-page")
    decision_ref = ContextEvidenceRef("main", "doc-decision", "chunk-decision")
    response = make_search_response(
        results=(
            make_result(rank=1, document_id="doc-page", chunk_id="chunk-page", kind="evidence_chunk"),
            make_result(rank=2, document_id="doc-decision", chunk_id="chunk-decision", kind="decision"),
        )
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver(
            {
                page_ref: make_resolved(page_ref),
                decision_ref: make_resolved(decision_ref, path="wiki/decision.md"),
            }
        ),
    ).build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            budget=ContextPackBudget(max_evidence_items=1),
        )
    )

    assert pack.decisions[0].evidence_refs == (decision_ref,)
    assert pack.relevant_pages == ()
    assert pack.budget.omitted_items == 1


def test_omitted_multi_evidence_item_does_not_leave_orphan_evidence(tmp_path: Path) -> None:
    first = ContextEvidenceRef("main", "doc-1", "chunk-1")
    second = ContextEvidenceRef("main", "doc-2", "chunk-2")
    response = make_search_response(results=(make_multi_evidence_result(),))
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver({first: make_resolved(first), second: make_resolved(second)}),
    ).build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            budget=ContextPackBudget(max_evidence_items=1),
        )
    )

    assert pack.relevant_pages == ()
    assert pack.evidence == ()
    assert pack.budget.used_tokens == 0
    assert pack.budget.omitted_items == 1


def test_same_chunk_id_from_two_vaults_remains_distinct(tmp_path: Path) -> None:
    first = ContextEvidenceRef("main", "doc-1", "shared")
    second = ContextEvidenceRef("second", "doc-1", "shared")
    response = make_search_response(
        results=(
            make_result(rank=1, vault_id="main", document_id="doc-1", chunk_id="shared"),
            make_result(rank=2, vault_id="second", document_id="doc-1", chunk_id="shared"),
        ),
        requested_scope=QueryScope(vault_ids=("main", "second")),
        actual_scopes=(QueryScope(vault_ids=("main",)), QueryScope(vault_ids=("second",))),
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver({first: make_resolved(first), second: make_resolved(second)}),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main", "second"))))

    assert [(evidence.ref.vault_id, evidence.ref.chunk_id) for evidence in pack.evidence] == [
        ("main", "shared"),
        ("second", "shared"),
    ]


def test_duplicate_evidence_refs_are_resolved_once_and_render_once(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        results=(
            make_result(rank=1, document_id="doc-1", chunk_id="chunk-1"),
            make_result(rank=2, document_id="doc-1", chunk_id="chunk-1"),
        )
    )
    resolver = StaticResolver({ref: make_resolved(ref)})
    pack = make_builder(tmp_path=tmp_path, response=response, resolver=resolver).build(
        ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
    )

    assert resolver.calls == [ref]
    assert len(pack.evidence) == 1


def test_invalid_evidence_paths_are_dropped_with_warning(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(),
        resolver=StaticResolver({ref: make_resolved(ref, path="/Users/me/vault/wiki/page.md")}),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert pack.relevant_pages == ()
    assert pack.evidence == ()
    assert "invalid_evidence_path" in [warning.code for warning in pack.warnings]


@pytest.mark.parametrize("path", ["private.md", "scratch/drafts/report.md", "docs/spec.md"])
def test_evidence_paths_must_stay_inside_actual_content_scope(tmp_path: Path, path: str) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver({ref: make_resolved(ref, path=path)}),
    ).build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        )
    )

    assert pack.relevant_pages == ()
    assert pack.evidence == ()
    assert "invalid_evidence_path" in [warning.code for warning in pack.warnings]


def test_default_pack_does_not_mark_graph_backends_used(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    builder = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(),
        resolver=StaticResolver({ref: make_resolved(ref)}),
    )
    pack = builder.build(
        ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
    )

    assert pack.backend.graph_store.used is False
    assert pack.backend.graph_projection.used is False
    assert {revision.kind for revision in pack.store_revisions} == {"metadata", "keyword"}
    assert pack.relevant_pages[0].evidence_refs == (ref,)


def test_non_graph_pack_omits_graph_and_projection_revisions(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        store_revisions=(
            SearchStoreRevision(kind="metadata", revision="metadata-1", vault_id="main", scope_key="main:wiki:local"),
            SearchStoreRevision(kind="keyword", revision="keyword-1", vault_id="main", scope_key="main:wiki:local"),
            SearchStoreRevision(kind="graph", revision="graph-1", vault_id="main", scope_key="main:wiki:local"),
            SearchStoreRevision(kind="projection", revision="projection-1", vault_id=None, scope_key="main:wiki:local"),
        )
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=response,
        resolver=StaticResolver({ref: make_resolved(ref)}),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert {revision.kind for revision in pack.store_revisions} == {"metadata", "keyword"}


def test_zero_results_pack_is_valid_and_preserves_search_warnings(tmp_path: Path) -> None:
    response = make_search_response(
        results=(),
        warnings=(
            SearchWarning(
                code="vector_unavailable",
                message="Vector unavailable",
                severity="warning",
                affected_vault_ids=("main",),
            ),
        ),
    )
    pack = make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver()).build(
        ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
    )

    assert pack.relevant_pages == ()
    assert pack.evidence == ()
    assert pack.warnings[0].code == "search_degraded"


def test_builder_rejects_response_that_widens_requested_scope(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(actual_scopes=(QueryScope(vault_ids=("main",)), QueryScope(vault_ids=("second",))))

    with pytest.raises(ContextPackError, match="outside requested scope"):
        make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver({ref: make_resolved(ref)})).build(
            ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
        )


def test_builder_rejects_response_that_widens_requested_content_scope(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki", "docs")),),
    )

    with pytest.raises(ContextPackError, match="outside requested scope"):
        make_builder(
            tmp_path=tmp_path,
            response=response,
            resolver=StaticResolver({ref: make_resolved(ref, path="docs/spec.md")}),
        ).build(
            ContextPackRequest(
                goal="Build context",
                requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
            )
        )


def test_builder_rejects_response_that_adds_cross_vault_scope(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    response = make_search_response(
        requested_scope=QueryScope(vault_ids=("main",)),
        actual_scopes=(QueryScope(vault_ids=("main",), include_cross_vault=True),),
    )

    with pytest.raises(ContextPackError, match="outside requested scope"):
        make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver({ref: make_resolved(ref)})).build(
            ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
        )


def test_builder_rejects_result_evidence_outside_actual_scope(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("second", "doc-1", "chunk-1")
    response = make_search_response(
        results=(make_result(vault_id="second"),),
        actual_scopes=(QueryScope(vault_ids=("main",)),),
    )

    with pytest.raises(ContextPackError, match="outside actual scope"):
        make_builder(tmp_path=tmp_path, response=response, resolver=StaticResolver({ref: make_resolved(ref)})).build(
            ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",)))
        )


def test_builder_classifies_decisions_constraints_questions_current_state_and_sources(tmp_path: Path) -> None:
    decision_ref = ContextEvidenceRef("main", "doc-decision", "chunk-decision")
    constraint_ref = ContextEvidenceRef("main", "doc-constraint", "chunk-constraint")
    question_ref = ContextEvidenceRef("main", "doc-question", "chunk-question")
    state_ref = ContextEvidenceRef("main", "doc-state", "chunk-state")
    source_ref = ContextEvidenceRef("main", "doc-source", "chunk-source")
    results = (
        make_result(rank=1, document_id="doc-decision", chunk_id="chunk-decision", path="wiki/decisions/choice.md"),
        make_result(rank=2, document_id="doc-constraint", chunk_id="chunk-constraint", path="docs/policy.md"),
        make_result(rank=3, document_id="doc-question", chunk_id="chunk-question", path="wiki/follow-up.md"),
        make_result(
            rank=4,
            document_id="doc-state",
            chunk_id="chunk-state",
            kind="evidence_chunk",
            path="wiki/status.md",
        ),
        make_result(rank=5, document_id="doc-source", chunk_id="chunk-source", path="raw/source.md"),
    )
    resolver = StaticResolver(
        {
            decision_ref: make_resolved(decision_ref, path="wiki/decisions/choice.md"),
            constraint_ref: make_resolved(constraint_ref, path="docs/policy.md"),
            question_ref: make_resolved(question_ref, path="wiki/follow-up.md"),
            state_ref: make_resolved(state_ref, path="wiki/status.md"),
            source_ref: make_resolved(source_ref, path="raw/source.md"),
        }
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=results),
        resolver=resolver,
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [item.item_type for item in pack.decisions] == ["decision"]
    assert [item.item_type for item in pack.constraints] == ["constraint"]
    assert [item.item_type for item in pack.open_questions] == ["open_question"]
    assert [item.item_type for item in pack.current_state] == ["current_state"]
    assert [item.item_type for item in pack.relevant_sources] == ["source"]


def test_builder_tie_breaks_by_signal_count_then_path(tmp_path: Path) -> None:
    first_ref = ContextEvidenceRef("main", "doc-first", "chunk-first")
    second_ref = ContextEvidenceRef("main", "doc-second", "chunk-second")
    first = make_result(
        rank=1,
        document_id="doc-first",
        chunk_id="chunk-first",
        path="wiki/a.md",
        signals=(
            RetrievalSignal(
                kind="keyword",
                source_id="keyword:first",
                rank=1,
                score=1.0,
                backend="sqlite-fts5",
                index_revision="keyword-1",
                explanation="keyword matched",
            ),
        ),
    )
    second = make_result(
        rank=1,
        document_id="doc-second",
        chunk_id="chunk-second",
        path="wiki/b.md",
        signals=(
            RetrievalSignal(
                kind="keyword",
                source_id="keyword:second",
                rank=1,
                score=1.0,
                backend="sqlite-fts5",
                index_revision="keyword-1",
                explanation="keyword matched",
            ),
            RetrievalSignal(
                kind="vector",
                source_id="vector:second",
                rank=2,
                score=0.9,
                backend="chroma",
                index_revision="vector-1",
                explanation="vector matched",
            ),
        ),
    )
    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=(first, second)),
        resolver=StaticResolver(
            {
                first_ref: make_resolved(first_ref, path="wiki/a.md"),
                second_ref: make_resolved(second_ref, path="wiki/b.md"),
            }
        ),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [item.evidence_refs[0].chunk_id for item in pack.relevant_pages] == ["chunk-second", "chunk-first"]


def test_builder_caps_large_retrieval_limit_by_evidence_budget(tmp_path: Path) -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    retrieval = RecordingRetrievalService(make_search_response())
    builder = SearchContextPackBuilder(
        catalog=make_catalog(tmp_path),
        retrieval_service=cast(ContextRetrievalService, retrieval),
        evidence_resolver=StaticResolver({ref: make_resolved(ref)}),
        clock=fixed_clock,
    )

    builder.build(
        ContextPackRequest(
            goal="Build context",
            requested_scope=QueryScope(vault_ids=("main",)),
            retrieval_limit=10_000,
            budget=ContextPackBudget(max_evidence_items=24),
        )
    )

    assert retrieval.calls[0]["limit"] == 96


def test_builder_keeps_durable_page_before_raw_source_and_lexical_tie_break(tmp_path: Path) -> None:
    page_ref = ContextEvidenceRef("main", "doc-page", "chunk-page")
    raw_ref = ContextEvidenceRef("main", "doc-raw", "chunk-raw")
    alpha_ref = ContextEvidenceRef("main", "doc-alpha", "chunk-alpha")
    beta_ref = ContextEvidenceRef("main", "doc-beta", "chunk-beta")
    page = make_result(rank=1, document_id="doc-page", chunk_id="chunk-page", path="wiki/page.md")
    raw = make_result(rank=1, document_id="doc-raw", chunk_id="chunk-raw", path="raw/source.md")
    alpha = make_result(rank=1, document_id="doc-alpha", chunk_id="chunk-alpha", path="wiki/a.md")
    beta = make_result(rank=1, document_id="doc-beta", chunk_id="chunk-beta", path="wiki/b.md")

    pack = make_builder(
        tmp_path=tmp_path,
        response=make_search_response(results=(raw, beta, page, alpha)),
        resolver=StaticResolver(
            {
                page_ref: make_resolved(page_ref, path="wiki/page.md"),
                raw_ref: make_resolved(raw_ref, path="raw/source.md"),
                alpha_ref: make_resolved(alpha_ref, path="wiki/a.md"),
                beta_ref: make_resolved(beta_ref, path="wiki/b.md"),
            }
        ),
    ).build(ContextPackRequest(goal="Build context", requested_scope=QueryScope(vault_ids=("main",))))

    assert [evidence.path for evidence in pack.evidence] == [
        "wiki/a.md",
        "wiki/b.md",
        "wiki/page.md",
        "raw/source.md",
    ]
