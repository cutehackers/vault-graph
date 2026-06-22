from __future__ import annotations

import json
from typing import cast

from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.mcp.mcp_memory_serialization import (
    health_explorer_report_to_payload,
    memory_warning_to_mcp_error,
    open_questions_projection_to_payload,
    project_memory_projection_to_payload,
    recent_changes_projection_to_payload,
    resource_links_for_memory_projection,
    resource_links_for_recent_changes,
    timeline_warnings,
)
from vault_graph.mcp.mcp_tool_serialization import tool_text_mirror
from vault_graph.memory.health_explorer import (
    BackendReadinessRecord,
    HealthExplorerReport,
    McpRuntimeCacheRecord,
    ScaleUpAdapterReadiness,
)
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
from vault_graph.memory.timeline_memory import RecentChangesProjection, TimelineEvidenceRef, TimelineItem, TimelineVault


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


def test_recent_changes_payload_preserves_origins_evidence_revisions_and_warnings() -> None:
    payload = recent_changes_projection_to_payload(make_recent_changes_projection())
    vaults = cast(list[dict[str, object]], payload["vaults"])
    vault = vaults[0]
    items = cast(list[dict[str, object]], vault["items"])
    item = items[0]
    evidence = cast(list[dict[str, object]], item["evidence"])
    revisions = cast(list[dict[str, object]], item["store_revisions"])
    item_warnings = cast(list[dict[str, object]], item["warnings"])
    payload_warnings = cast(list[dict[str, object]], payload["warnings"])

    assert item["origin"] == "document_snapshot_change"
    assert evidence[0]["source_kind"] == "document"
    assert revisions[0]["kind"] == "metadata"
    assert item_warnings[0]["code"] == "candidate_decision"
    assert payload_warnings[0]["code"] == "candidate_decision"


def test_recent_changes_links_only_document_backed_items() -> None:
    links = resource_links_for_recent_changes(make_recent_changes_projection())

    assert [link.uri for link in links] == ["vault://main/documents/wiki%2Fpage.md"]
    assert links[0].rel == "document"


def test_timeline_warnings_collect_projection_vault_and_item_warnings() -> None:
    assert len(timeline_warnings(make_recent_changes_projection())) == 3


def test_health_explorer_payload_preserves_backend_runtime_and_scale_up_records() -> None:
    report = HealthExplorerReport(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        backends=(
            BackendReadinessRecord(
                backend_kind="metadata",
                backend_name="sqlite",
                vault_id="main",
                scope_key="main:wiki",
                status="ready",
                schema_compatible=True,
                freshness="fresh",
                revision="metadata-1",
                last_success_at=None,
                last_error_at=None,
                message="metadata ready",
                recovery_hint=None,
            ),
        ),
        runtime_caches=(
            McpRuntimeCacheRecord(
                cache_name="context_pack",
                current_entries=1,
                max_entries=32,
                status="ready",
                message="cache ready",
            ),
        ),
        scale_up_adapters=(
            ScaleUpAdapterReadiness(
                adapter_kind="metadata",
                target_backend="postgres",
                configured=False,
                contract_ready=True,
                migration_required=True,
                depends_on_backend_kind="metadata",
                message="metadata contract ready; no record-level migration audit was performed",
            ),
        ),
        warnings=(),
        generated_at="2026-06-18T00:00:00+00:00",
    )

    payload = health_explorer_report_to_payload(report)
    backends = cast(list[dict[str, object]], payload["backends"])
    runtime_caches = cast(list[dict[str, object]], payload["runtime_caches"])
    scale_up_adapters = cast(list[dict[str, object]], payload["scale_up_adapters"])

    assert backends[0]["backend_kind"] == "metadata"
    assert runtime_caches[0]["cache_name"] == "context_pack"
    assert scale_up_adapters[0]["target_backend"] == "postgres"


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


def make_recent_changes_projection() -> RecentChangesProjection:
    warning = make_warning()
    item = TimelineItem(
        item_id="timeline:document_snapshot_change:0123456789abcdef01234567",
        origin="document_snapshot_change",
        title="Indexed document: wiki/page.md",
        summary="Indexed document state changed.",
        vault_id="main",
        occurred_at="2026-06-18T00:00:00+00:00",
        sort_key="2026-06-18T00:00:00+00:00",
        evidence=(
            TimelineEvidenceRef(
                source_kind="document",
                vault_id="main",
                document_id="doc-1",
                path="wiki/page.md",
                content_hash="hash",
            ),
        ),
        store_revisions=(
            MemoryBackendRevision(kind="metadata", revision="metadata-1", vault_id="main", scope_key="main:wiki"),
        ),
        warnings=(warning,),
    )
    return RecentChangesProjection(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        actual_scopes=(QueryScope(vault_ids=("main",), content_scopes=("wiki",)),),
        since=None,
        limit=20,
        vaults=(
            TimelineVault(
                vault_id="main",
                display_name="Main",
                items=(item,),
                warnings=(warning,),
                store_revisions=(),
                freshness="fresh",
            ),
        ),
        warnings=(warning,),
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
