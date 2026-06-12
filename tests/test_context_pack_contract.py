from __future__ import annotations

import pytest

from vault_graph.context import (
    CONTEXT_PACK_SCHEMA_VERSION,
    ContextEvidenceRef,
    ContextPack,
    ContextPackActualScope,
    ContextPackBackend,
    ContextPackBackendUse,
    ContextPackBudget,
    ContextPackItem,
    ContextPackRequest,
    ContextPackRequestedScope,
    ContextPackScope,
    ContextPackStoreRevision,
    ContextPackVault,
    ContextPackVaultRevision,
    ContextPackWarning,
    context_scope_from_query_scopes,
    scope_key,
)
from vault_graph.errors import ContextPackError
from vault_graph.ingestion.vault_catalog import QueryScope


def make_pack(*, generated_at: str = "2026-06-12T00:00:00+00:00") -> ContextPack:
    return ContextPack(
        context_pack_schema_version=CONTEXT_PACK_SCHEMA_VERSION,
        pack_id="",
        goal="Implement GraphRAG MVP",
        scope=ContextPackScope(
            requested=ContextPackRequestedScope(
                vault_ids=("main",),
                content_scopes=("wiki", "docs"),
                include_cross_vault=False,
            ),
            actual_scopes=(
                ContextPackActualScope(
                    vault_ids=("main",),
                    content_scopes=("wiki", "docs"),
                    include_cross_vault=False,
                    scope_key="main:wiki,docs:local",
                ),
            ),
        ),
        vaults=(ContextPackVault(vault_id="main", display_name="Main Vault"),),
        vault_revisions=(ContextPackVaultRevision(vault_id="main", revision="git-sha", revision_kind="git"),),
        backend=ContextPackBackend(
            metadata_store=ContextPackBackendUse(name="sqlite", used=True),
            keyword_index=ContextPackBackendUse(name="sqlite-fts5", used=True),
            vector_store=ContextPackBackendUse(name="chroma", used=True),
            graph_store=ContextPackBackendUse(name=None, used=False),
            graph_projection=ContextPackBackendUse(name=None, used=False),
        ),
        store_revisions=(
            ContextPackStoreRevision(
                kind="metadata",
                revision="metadata-1",
                vault_id="main",
                scope_key="main:wiki,docs:local",
            ),
        ),
        retrieval_policy_version="retrieval-policy-v1",
        budget=ContextPackBudget(used_tokens=0, omitted_items=0),
        generated_at=generated_at,
        current_state=(),
        relevant_pages=(),
        relevant_sources=(),
        decisions=(),
        constraints=(),
        open_questions=(),
        warnings=(),
        evidence=(),
    )


def make_pack_with_warning(*, code: str = "graph_unavailable", message: str = "Graph missing") -> ContextPack:
    pack = make_pack()
    return ContextPack(
        **{
            **pack.__dict__,
            "warnings": (
                ContextPackWarning(
                    code=code,
                    severity="warning",
                    message=message,
                    affected_vault_ids=("main",),
                    source_code=code,
                    source_kind="graph",
                ),
            ),
        }
    )


def test_context_pack_includes_required_top_level_fields() -> None:
    pack = make_pack()

    assert pack.context_pack_schema_version == "context-pack-v1"
    assert pack.scope.requested.vault_ids == ("main",)
    assert pack.backend.graph_store.used is False
    assert pack.budget.max_tokens == 8000
    assert pack.warnings == ()
    assert pack.evidence == ()


def test_item_requires_evidence_refs() -> None:
    with pytest.raises(ContextPackError, match="evidence_refs are required"):
        ContextPackItem(
            item_id="item-1",
            item_type="page",
            title="Page",
            summary="Summary",
            evidence_refs=(),
            retrieval_signals=(),
            relationship_status=None,
            rank=1,
            warnings=(),
        )


def test_context_pack_request_rejects_cross_vault_without_graph() -> None:
    with pytest.raises(ContextPackError, match="include_cross_vault requires include_graph"):
        ContextPackRequest(
            goal="Build",
            requested_scope=QueryScope(vault_ids=("first", "second"), include_cross_vault=True),
            include_graph=False,
            include_cross_vault=True,
        )


def test_context_pack_request_rejects_mismatched_cross_vault_state() -> None:
    with pytest.raises(ContextPackError, match="include_cross_vault must match requested_scope"):
        ContextPackRequest(
            goal="Build",
            requested_scope=QueryScope(vault_ids=("first", "second"), include_cross_vault=True),
            include_graph=True,
            include_cross_vault=False,
        )


def test_context_pack_request_rejects_cross_vault_with_single_requested_vault() -> None:
    with pytest.raises(ContextPackError, match="requires multiple requested vault_ids"):
        ContextPackRequest(
            goal="Build",
            requested_scope=QueryScope(vault_ids=("main",), include_cross_vault=True),
            include_graph=True,
            include_cross_vault=True,
        )


def test_scope_key_distinguishes_local_and_cross_vault_scopes() -> None:
    assert scope_key(QueryScope(vault_ids=("main",), content_scopes=("wiki", "docs"))) == "main:wiki,docs:local"
    assert (
        scope_key(
            QueryScope(
                vault_ids=("first", "second"),
                content_scopes=("wiki",),
                include_cross_vault=True,
            )
        )
        == "first,second:wiki:cross-vault"
    )


def test_context_scope_from_query_scopes_preserves_requested_and_actual_state() -> None:
    context_scope = context_scope_from_query_scopes(
        requested_scope=QueryScope(vault_ids=("first", "second"), content_scopes=("wiki",)),
        actual_scopes=(
            QueryScope(vault_ids=("first",), content_scopes=("wiki",)),
            QueryScope(vault_ids=("second",), content_scopes=("wiki",)),
        ),
    )

    assert context_scope.requested.vault_ids == ("first", "second")
    assert [actual.scope_key for actual in context_scope.actual_scopes] == [
        "first:wiki:local",
        "second:wiki:local",
    ]


def test_warning_severity_is_validated() -> None:
    with pytest.raises(ContextPackError, match="unsupported warning severity"):
        ContextPackWarning(
            code="warning",
            severity="fatal",  # type: ignore[arg-type]
            message="bad severity",
            affected_vault_ids=("main",),
        )


def test_evidence_ref_is_hashable_and_vault_scoped() -> None:
    assert len({ContextEvidenceRef("first", "doc", "chunk"), ContextEvidenceRef("second", "doc", "chunk")}) == 2
