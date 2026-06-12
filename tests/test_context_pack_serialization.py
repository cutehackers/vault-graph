from __future__ import annotations

import json
import math
from dataclasses import replace

import pytest

from tests.test_context_pack_contract import make_pack, make_pack_with_warning
from vault_graph.context import (
    ContextEvidence,
    ContextEvidenceRef,
    ContextPackItem,
    ContextPackRenderer,
    ContextPackSignal,
    DefaultContextPackRenderer,
    render_context_pack_json,
    with_computed_pack_id,
)
from vault_graph.errors import ContextPackError


def test_context_pack_json_keeps_null_optional_fields_and_sorted_keys() -> None:
    pack = make_pack_with_warning()
    rendered = render_context_pack_json(pack)
    payload = json.loads(rendered)

    assert rendered.endswith("\n")
    assert payload["backend"]["graph_store"]["name"] is None
    assert payload["warnings"][0]["scope_key"] is None
    assert list(payload.keys()) == sorted(payload.keys())


def test_pack_id_excludes_generated_at() -> None:
    first = with_computed_pack_id(make_pack(generated_at="2026-06-12T00:00:00+00:00"))
    second = with_computed_pack_id(make_pack(generated_at="2026-06-12T01:00:00+00:00"))

    assert first.pack_id == second.pack_id
    assert len(first.pack_id) == 64


def test_json_renderer_uses_canonical_json() -> None:
    pack = make_pack_with_warning()
    renderer: ContextPackRenderer = DefaultContextPackRenderer()

    assert renderer.render_json(pack) == render_context_pack_json(pack)


def test_markdown_renderer_cannot_hide_top_level_warnings() -> None:
    pack = make_pack_with_warning(code="graph_unavailable", message="Graph missing")
    renderer: ContextPackRenderer = DefaultContextPackRenderer()
    markdown = renderer.render_markdown(pack)

    assert "## Warnings" in markdown
    assert "graph_unavailable" in markdown
    assert "Graph missing" in markdown


def test_markdown_renderer_preserves_metadata_budget_and_revisions() -> None:
    markdown = DefaultContextPackRenderer().render_markdown(make_pack())

    assert "## Budget" in markdown
    assert "- max_tokens: `8000`" in markdown
    assert "- omitted_items: `0`" in markdown
    assert "## Backend" in markdown
    assert "- metadata_store: `sqlite`, used=`True`" in markdown
    assert "## Vault Revisions" in markdown
    assert "- `main`: `git-sha` (`git`)" in markdown
    assert "## Store Revisions" in markdown
    assert "- `metadata`: `metadata-1`, vault=`main`, scope=`main:wiki,docs:local`" in markdown


def test_markdown_renderer_escapes_vault_derived_headings() -> None:
    pack = make_pack_with_warning(message="# injected\n```")
    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "\n# injected" not in markdown
    assert "\\# injected" in markdown


def test_markdown_renderer_uses_collision_safe_fence_for_excerpts() -> None:
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
        excerpt="before\n```\n# injected",
        excerpt_token_count=3,
        truncated=False,
        retrieval_reasons=("keyword matched",),
        warnings=(),
    )
    pack = replace(make_pack(), evidence=(evidence,))
    markdown = DefaultContextPackRenderer().render_markdown(pack)

    assert "\n  ````text\n" in markdown
    assert markdown.count("\n  ````") == 2


def test_context_pack_json_rejects_non_finite_float_scores() -> None:
    ref = ContextEvidenceRef("main", "doc-1", "chunk-1")
    item = ContextPackItem(
        item_id="item-1",
        item_type="page",
        title="Page",
        summary="Summary",
        evidence_refs=(ref,),
        retrieval_signals=(ContextPackSignal(kind="vector", rank=1, score=math.nan, explanation="vector matched"),),
        relationship_status=None,
        rank=1,
        warnings=(),
    )
    pack = replace(make_pack(), relevant_pages=(item,))

    with pytest.raises(ContextPackError, match="non-finite float"):
        render_context_pack_json(pack)


def test_cli_does_not_format_context_pack_sections_in_phase_4a() -> None:
    cli_source = "src/vault_graph/cli/main.py"
    with open(cli_source, encoding="utf-8") as file:
        source = file.read()

    assert "ContextPackRenderer" not in source
    assert "render_context_pack" not in source
