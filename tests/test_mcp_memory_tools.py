from __future__ import annotations

import json
from typing import cast

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_memory_serialization import (
    memory_warning_to_mcp_error,
    open_questions_projection_to_payload,
    project_memory_projection_to_payload,
    resource_links_for_memory_projection,
)
from vault_graph.mcp.mcp_tool_serialization import tool_text_mirror
from vault_graph.memory.memory_models import (
    MemoryBackendRevision,
    MemoryEvidenceRef,
    MemoryItem,
    MemoryWarning,
    OpenQuestionsProjection,
    OpenQuestionsVault,
    ProjectMemoryProjection,
    ProjectMemoryVault,
)


def test_project_memory_projection_payload_preserves_claim_status_signals_evidence_and_warnings() -> None:
    warning = make_warning()
    projection = make_project_projection(warnings=(warning,), item_warnings=(warning,))

    payload = project_memory_projection_to_payload(projection)
    vaults = cast(list[dict[str, object]], payload["vaults"])
    vault = vaults[0]
    decisions = cast(list[dict[str, object]], vault["decisions"])
    item = decisions[0]
    evidence = cast(list[dict[str, object]], item["evidence"])
    item_warnings = cast(list[dict[str, object]], item["warnings"])
    payload_warnings = cast(list[dict[str, object]], payload["warnings"])

    assert item["claim_status"] == "stated"
    assert item["matched_signals"] == ["path:wiki/decisions"]
    assert evidence[0]["chunk_id"] == "chunk-1"
    assert item_warnings[0]["code"] == "candidate_decision"
    assert payload_warnings[0]["code"] == "candidate_decision"


def test_open_questions_projection_payload_preserves_vault_groups() -> None:
    projection = make_open_questions_projection()

    payload = open_questions_projection_to_payload(projection)
    requested_scope = cast(dict[str, object], payload["requested_scope"])
    vaults = cast(list[dict[str, object]], payload["vaults"])

    assert requested_scope["vault_ids"] == ["main", "work"]
    assert [vault["vault_id"] for vault in vaults] == ["main", "work"]


def test_memory_resource_links_include_document_page_decision_and_issue_links() -> None:
    decision = make_item(document_resource_kinds=("document", "page", "decision"))
    question = make_item(
        kind="open_question",
        document_resource_kinds=("document", "page", "issue"),
        document_id="issue-doc",
        chunk_id="issue-chunk",
        path="wiki/issues/open.md",
    )
    projection = make_project_projection(decisions=(decision,), open_questions=(question,))

    links = resource_links_for_memory_projection(projection)
    uris = {link.uri for link in links}

    assert "vault://main/documents/wiki%2Fdecisions%2Fuse-mcp.md" in uris
    assert "vault://main/pages/wiki%2Fdecisions%2Fuse-mcp.md" in uris
    assert "vault://main/decisions/doc-1" in uris
    assert "vault://main/issues/issue-doc" in uris


def test_memory_resource_links_use_document_resource_kinds_for_frontmatter_decisions_and_issues() -> None:
    source_decision = make_item(
        document_resource_kinds=("document", "source", "decision"),
        path="docs/decision.md",
    )
    projection = make_project_projection(decisions=(source_decision,))

    uris = {link.uri for link in resource_links_for_memory_projection(projection)}

    assert "vault://main/sources/doc-1" in uris
    assert "vault://main/decisions/doc-1" in uris


def test_memory_resource_links_do_not_link_heading_only_candidates_as_decisions_or_issues() -> None:
    candidate = make_item(claim_status="heading_candidate", document_resource_kinds=("document", "page"))
    projection = make_project_projection(decisions=(candidate,))

    uris = {link.uri for link in resource_links_for_memory_projection(projection)}

    assert "vault://main/documents/wiki%2Fdecisions%2Fuse-mcp.md" in uris
    assert not any("/decisions/" in uri for uri in uris)


def test_memory_resource_links_do_not_create_memory_uris() -> None:
    projection = make_project_projection()

    assert not any("/memory/" in link.uri for link in resource_links_for_memory_projection(projection))


def test_memory_warning_maps_to_mcp_error_payload() -> None:
    warning = make_warning()

    payload = memory_warning_to_mcp_error(warning)

    assert payload.code == warning.code
    assert payload.severity == warning.severity
    assert payload.affected_vault_ids == warning.affected_vault_ids


def test_memory_text_mirror_contains_no_fields_outside_structured_payload() -> None:
    payload = project_memory_projection_to_payload(make_project_projection())

    mirrored = json.loads(tool_text_mirror(payload))

    assert mirrored == payload


def make_project_projection(
    *,
    decisions: tuple[MemoryItem, ...] | None = None,
    open_questions: tuple[MemoryItem, ...] = (),
    warnings: tuple[MemoryWarning, ...] = (),
    item_warnings: tuple[MemoryWarning, ...] = (),
) -> ProjectMemoryProjection:
    item = make_item(warnings=item_warnings)
    vault = ProjectMemoryVault(
        vault_id="main",
        display_name="Main",
        current_state=(),
        decisions=decisions if decisions is not None else (item,),
        open_questions=open_questions,
        constraints=(),
        next_priorities=(),
        stale_areas=(),
        warnings=warnings,
        store_revisions=(
            MemoryBackendRevision(kind="metadata", revision="rev-1", vault_id="main", scope_key="main:wiki"),
        ),
        freshness="fresh",
    )
    return ProjectMemoryProjection(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        vaults=(vault,),
        warnings=warnings,
        generated_at="2026-06-18T00:00:00+00:00",
    )


def make_open_questions_projection() -> OpenQuestionsProjection:
    return OpenQuestionsProjection(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",)),
        actual_scopes=(
            QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
            QueryScope(vault_ids=("work",), content_scopes=("wiki",)),
        ),
        vaults=(
            OpenQuestionsVault(
                vault_id="main",
                display_name="Main",
                questions=(make_item(kind="open_question"),),
                warnings=(),
                store_revisions=(),
                freshness="fresh",
            ),
            OpenQuestionsVault(
                vault_id="work",
                display_name="Work",
                questions=(
                    make_item(
                        kind="open_question",
                        vault_id="work",
                        document_id="work-doc",
                        chunk_id="work-chunk",
                    ),
                ),
                warnings=(),
                store_revisions=(),
                freshness="fresh",
            ),
        ),
        warnings=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )


def make_item(
    *,
    kind: str = "decision",
    claim_status: str = "stated",
    document_resource_kinds: tuple[str, ...] = ("document", "page", "decision"),
    vault_id: str = "main",
    document_id: str = "doc-1",
    chunk_id: str = "chunk-1",
    path: str = "wiki/decisions/use-mcp.md",
    warnings: tuple[MemoryWarning, ...] = (),
) -> MemoryItem:
    return MemoryItem(
        item_id=f"memory:{kind}:0123456789abcdef01234567",
        kind=kind,  # type: ignore[arg-type]
        claim_status=claim_status,  # type: ignore[arg-type]
        matched_signals=("path:wiki/decisions",),
        document_resource_kinds=document_resource_kinds,  # type: ignore[arg-type]
        title="Use MCP",
        summary="Decision summary",
        vault_id=vault_id,
        path=path,
        status="accepted",
        rank=1,
        evidence=(
            MemoryEvidenceRef(
                vault_id=vault_id,
                document_id=document_id,
                chunk_id=chunk_id,
                path=path,
                section="Decision",
                anchor="decision",
                content_hash="content-hash",
                raw_sha256="raw-sha",
                metadata_index_revision="metadata-1",
                vault_revision="vault-1",
            ),
        ),
        warnings=warnings,
    )


def make_warning() -> MemoryWarning:
    return MemoryWarning(
        code="candidate_decision",
        message="Candidate decision",
        severity="warning",
        affected_vault_ids=("main",),
        recovery_hint="Check the cited document.",
    )
