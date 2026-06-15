from __future__ import annotations

from dataclasses import replace

from tests.test_context_pack_contract import make_pack
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPackWarning,
    DefaultContextPackRenderer,
)


def test_markdown_renderer_uses_phase_4b_section_order() -> None:
    markdown = DefaultContextPackRenderer().render_markdown(make_pack())

    expected_order = [
        "# Context Pack",
        "## Goal",
        "## Scope",
        "## Warnings",
        "## Decisions",
        "## Constraints",
        "## Open Questions",
        "## Current State",
        "## Relevant Pages",
        "## Relevant Sources",
        "## Evidence",
        "## Revisions",
        "## Budget",
        "## Backend",
    ]
    positions = [markdown.index(heading) for heading in expected_order]
    assert positions == sorted(positions)


def test_markdown_warnings_show_scope_and_recovery_hint() -> None:
    pack = replace(
        make_pack(),
        warnings=(
            ContextPackWarning(
                code="metadata_unavailable",
                severity="warning",
                message="Metadata missing",
                affected_vault_ids=("main",),
                source_code="metadata_unavailable",
                source_kind="builder",
                recovery_hint="Run `vg index`.",
            ),
        ),
    )

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "[warning] `metadata_unavailable` [main]: Metadata missing" in markdown
    assert "Recovery: Run \\`vg index\\`." in markdown


def test_markdown_evidence_lines_include_vault_anchor_and_truncated_marker() -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    evidence = ContextEvidence(
        ref=ref,
        path="wiki/page.md",
        section="Section",
        anchor="section",
        content_hash="hash",
        raw_sha256="raw",
        metadata_index_revision="metadata-1",
        vault_revision="git-1",
        excerpt="one two three",
        excerpt_token_count=3,
        truncated=True,
        retrieval_reasons=("keyword matched",),
        warnings=(
            ContextPackWarning(
                code="excerpt_truncated",
                severity="warning",
                message="Evidence excerpt truncated.",
                affected_vault_ids=("main",),
                evidence_refs=(ref,),
                source_code="excerpt_truncated",
                source_kind="budget",
            ),
        ),
    )
    pack = replace(make_pack(), evidence=(evidence,))

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "[main] wiki/page.md#section [truncated]" in markdown
    assert "excerpt_truncated" in markdown


def test_markdown_renderer_escapes_vault_derived_item_and_evidence_text() -> None:
    pack = replace(
        make_pack(),
        warnings=(
            ContextPackWarning(
                code="search_degraded",
                severity="warning",
                message="# injected\n```",
                affected_vault_ids=("main",),
                source_code="search_degraded",
                source_kind="retrieval",
            ),
        ),
    )

    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "\n# injected" not in markdown
    assert "\\# injected" in markdown
    assert markdown.count("```") % 2 == 0
