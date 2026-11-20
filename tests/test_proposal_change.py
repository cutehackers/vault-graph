"""What a memory proposal would change, per draft shape (spec 2026-11-20-vg-review-accept D4, A2).

The drafts come from the same builders the memory tools use, so the shapes match what reaches the
Vault review queue.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from vault_graph.operation.memory import proposal_change
from vault_graph.operation.memory.memory_drafts import (
    build_remember_draft,
    build_restore_draft,
    build_retire_draft,
    build_supersede_claim_draft,
    build_update_draft,
)
from vault_graph.operation.memory.memory_ports import PageText
from vault_graph.operation.memory.memory_requests import (
    RememberRequest,
    RestoreRequest,
    RetireRequest,
    SupersedeClaimRequest,
    UpdateRequest,
)
from vault_graph.operation.memory.proposal_change import (
    FrontmatterChange,
    build_proposal_change,
    render_proposal_change,
)

TODAY = date(2026, 11, 20)
QUOTE = 'session 7f3a#12 user: "배포는 금요일에 하지 않는다"'
PAGE_PATH = "wiki/decisions/배포-요일.md"

CURRENT_PAGE = (
    "---\n"
    "title: 배포 요일\n"
    "type: decision\n"
    "status: active\n"
    "created: 2026-11-01\n"
    "updated: 2026-11-01\n"
    "owner: agent\n"
    "summary: 배포 요일\n"
    "source_count: 1\n"
    "tags: []\n"
    "---\n"
    "# 배포 요일\n"
    "\n"
    "배포는 목요일까지 한다.\n"
    "\n"
    "## Evidence\n"
    "\n"
    "Status: stated\n"
    "\n"
    "- Evidence: 옛 근거\n"
)


def remember_draft() -> dict[str, object]:
    request = RememberRequest(
        kind="decision",
        title="배포 요일",
        body="배포는 금요일에 하지 않는다.",
        basis="inferred",
        evidence=(QUOTE, "second line"),
    )
    return build_remember_draft(request, today=TODAY)


def update_draft() -> dict[str, object]:
    request = UpdateRequest(
        path=PAGE_PATH,
        body="배포는 금요일에 하지 않는다.",
        basis="inferred",
        evidence=(QUOTE,),
        summary="금요일 배포 금지",
    )
    return build_update_draft(request, PageText(text=CURRENT_PAGE, sha256="0" * 64), today=TODAY)


def test_new_page_shows_the_whole_page_and_its_evidence_lines() -> None:
    draft = remember_draft()

    change = build_proposal_change(draft, None)

    assert change.kind == "new-page"
    assert change.path == "wiki/decisions/배포-요일.md"
    assert change.new_page is not None
    assert change.new_page.startswith("---\ntitle: 배포 요일\n")
    assert "status: active\n" in change.new_page
    assert "  provenance: section\n" in change.new_page
    assert change.new_page.endswith(str(draft["body"]))
    assert change.body_diff == ()
    assert change.frontmatter == ()
    assert change.evidence == (QUOTE, "second line")
    rendered = "\n".join(render_proposal_change(change))
    assert "배포는 금요일에 하지 않는다." in rendered
    assert QUOTE in rendered
    assert "\\u" not in rendered


def test_upsert_on_an_existing_page_shows_the_body_diff_and_the_changed_frontmatter_keys() -> None:
    change = build_proposal_change(update_draft(), CURRENT_PAGE)

    assert change.kind == "page-update"
    assert change.new_page is None
    assert "-배포는 목요일까지 한다." in change.body_diff
    assert "+배포는 금요일에 하지 않는다." in change.body_diff
    assert " # 배포 요일" in change.body_diff
    assert not any(line.startswith(("---", "+++")) for line in change.body_diff)
    assert change.frontmatter == (
        FrontmatterChange("updated", "changed", before="2026-11-01", after="2026-11-20"),
        FrontmatterChange("summary", "changed", before="배포 요일", after="금요일 배포 금지"),
    )
    assert change.evidence == (QUOTE,)
    rendered = render_proposal_change(change)
    assert "summary: 배포 요일 -> 금요일 배포 금지" in rendered
    assert not any(line.startswith("title:") for line in rendered)


def test_upsert_reports_added_and_removed_frontmatter_keys() -> None:
    draft = update_draft()
    frontmatter = dict(draft["frontmatter"])  # type: ignore[call-overload]
    del frontmatter["owner"]
    frontmatter["aliases"] = ["금요일 배포"]
    draft["frontmatter"] = frontmatter

    change = build_proposal_change(draft, CURRENT_PAGE)

    assert FrontmatterChange("aliases", "added", before=None, after=["금요일 배포"]) in change.frontmatter
    assert FrontmatterChange("owner", "removed", before="agent", after=None) in change.frontmatter
    rendered = render_proposal_change(change)
    assert 'aliases: (none) -> ["금요일 배포"]' in rendered
    assert "owner: agent -> (removed)" in rendered


def test_upsert_with_the_same_body_has_an_empty_diff() -> None:
    draft = update_draft()
    draft["body"] = CURRENT_PAGE.split("---\n", 2)[2]

    change = build_proposal_change(draft, CURRENT_PAGE)

    assert change.body_diff == ()
    assert "(body unchanged)" in render_proposal_change(change)


def test_retire_draft_shows_the_frontmatter_keys_as_written_and_no_result_page() -> None:
    draft = build_retire_draft(RetireRequest(path=PAGE_PATH, reason="더 이상 맞지 않음", basis="inferred"), today=TODAY)

    change = build_proposal_change(draft, CURRENT_PAGE)

    assert change.kind == "patch"
    assert change.new_page is None
    assert change.body_diff == ()
    assert change.frontmatter == (
        FrontmatterChange("status", "set", before=None, after="retired"),
        FrontmatterChange("retired_reason", "set", before=None, after="더 이상 맞지 않음"),
        FrontmatterChange("retired_at", "set", before=None, after="2026-11-20"),
    )
    assert change.edits == ()
    rendered = render_proposal_change(change)
    assert "status: retired" in rendered
    assert "retired_reason: 더 이상 맞지 않음" in rendered
    assert not any("배포는 목요일까지 한다." in line for line in rendered)


def test_patch_page_is_the_same_with_or_without_the_current_page() -> None:
    retired = CURRENT_PAGE.replace("status: active", "status: retired")
    draft = build_restore_draft(
        RestoreRequest(path=PAGE_PATH, reason="다시 유효", basis="inferred"),
        PageText(text=retired, sha256="0" * 64),
        today=TODAY,
    )

    assert build_proposal_change(draft, retired) == build_proposal_change(draft, None)


def test_supersede_claim_shows_the_old_claim_the_new_claim_and_the_evidence() -> None:
    request = SupersedeClaimRequest(
        path=PAGE_PATH,
        claim="배포는 목요일까지 한다.",
        new_claim="배포는 수요일까지 한다.",
        basis="inferred",
        evidence=QUOTE,
    )

    change = build_proposal_change(build_supersede_claim_draft(request), CURRENT_PAGE)

    assert change.kind == "patch"
    assert change.frontmatter == ()
    assert len(change.edits) == 1
    edit = change.edits[0]
    assert edit.op == "supersede-claim"
    assert dict(edit.fields) == {
        "claim": "배포는 목요일까지 한다.",
        "by": "배포는 수요일까지 한다.",
        "status": "inferred",
        "evidence": QUOTE,
    }
    assert change.evidence == (QUOTE,)
    rendered = render_proposal_change(change)
    assert "  old claim: 배포는 목요일까지 한다." in rendered
    assert "  new claim: 배포는 수요일까지 한다." in rendered
    assert f"- {QUOTE}" in rendered


def test_an_unknown_edit_is_shown_with_its_own_fields() -> None:
    draft: dict[str, object] = {
        "version": 1,
        "operation": "patch-page",
        "path": PAGE_PATH,
        "edits": [{"op": "append-section", "heading": "메모", "lines": ["한 줄", "두 줄"]}],
    }

    change = build_proposal_change(draft, None)

    assert change.edits[0].op == "append-section"
    assert change.edits[0].fields == (("heading", "메모"), ("lines", '["한 줄", "두 줄"]'))
    assert change.evidence == ()


@pytest.mark.parametrize(
    "draft",
    [
        {"operation": "delete-page", "path": PAGE_PATH},
        {"operation": "upsert-page", "path": PAGE_PATH, "frontmatter": {}},
        {"operation": "upsert-page", "path": PAGE_PATH, "frontmatter": [], "body": "x"},
        {"operation": "upsert-page", "frontmatter": {}, "body": "x"},
        {"operation": "patch-page", "path": PAGE_PATH, "frontmatter": "status: retired"},
        {"operation": "patch-page", "path": PAGE_PATH, "edits": [{"claim": "no op"}]},
        {"operation": "patch-page", "path": PAGE_PATH, "edits": {"op": "supersede-claim"}},
    ],
    ids=["operation", "no-body", "frontmatter-shape", "no-path", "patch-frontmatter", "edit-without-op", "edits-shape"],
)
def test_a_draft_outside_the_known_shapes_is_refused_with_a_reason(draft: dict[str, object]) -> None:
    with pytest.raises(ValueError, match=r"\S"):
        build_proposal_change(draft, None)


def test_the_module_reads_no_file_and_starts_no_process() -> None:
    source = Path(proposal_change.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}

    assert imported.isdisjoint({"pathlib", "os", "io", "subprocess", "shutil", "tempfile"})
    assert "open" not in called
    assert attributes.isdisjoint({"read_text", "write_text", "read_bytes", "write_bytes", "open"})
