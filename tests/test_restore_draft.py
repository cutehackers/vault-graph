"""restore_memory: bring a retired page back with a frontmatter-only ``patch-page`` draft.

Source: spec 2026-11-05 §4.4.13-3, §6 ("restore_memory 대상이 폐기 상태가 아님"), A-39 (vg side), A-31.
``status: active``, ``restored_at`` and ``restored_reason`` change. ``retired_reason``, ``retired_at`` and
``superseded_by`` stay on the page as history, so the draft never names them.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from tests.test_memory_write_service import TODAY, RecordingWriter, add_page, make_service, make_vault
from tests.test_read_only_boundary import file_bytes
from vault_graph.operation.memory.memory_drafts import build_restore_draft
from vault_graph.operation.memory.memory_ports import PageText, WriteOutcome
from vault_graph.operation.memory.memory_requests import RestoreRequest, validate_restore

PATH = "wiki/decisions/use-sqlite.md"


def page(status: str, extra: str = "") -> str:
    return f"""---
title: Use SQLite
type: decision
status: {status}
created: 2026-10-01
updated: 2026-10-01
owner: agent
summary: Use SQLite
source_count: 1
tags: []
related: []
confidence: medium
{extra}---

# Use SQLite

Body.
"""


RETIRED_PAGE = page("retired", "retired_reason: We moved to Postgres.\nretired_at: 2026-10-20\n")


def page_text(text: str) -> PageText:
    return PageText(text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


def restore_request(**overrides: object) -> RestoreRequest:
    values: dict[str, object] = {
        "path": PATH,
        "reason": "Postgres was rolled back.",
        "basis": "stated",
        "vault": "main",
    }
    values.update(overrides)
    return RestoreRequest(**values)  # type: ignore[arg-type]


def test_draft_changes_only_status_and_restored_fields() -> None:
    draft = build_restore_draft(
        restore_request(reason="  Postgres was rolled back. "), page_text(RETIRED_PAGE), today=TODAY
    )

    assert draft["operation"] == "patch-page"
    assert draft["path"] == PATH
    assert draft["frontmatter"] == {
        "status": "active",
        "restored_at": "2026-11-02",
        "restored_reason": "Postgres was rolled back.",
    }
    assert "edits" not in draft
    assert "body" not in draft
    log = draft["log"]
    assert isinstance(log, dict)
    assert log["items"] == ["Restored [[decisions/use-sqlite]]: Postgres was rolled back."]


@pytest.mark.parametrize(
    "text",
    [
        page("deprecated", "superseded_by:\n  - decisions/use-postgres\n"),
        page("superseded", "superseded_by:\n  - decisions/use-postgres\n"),
    ],
)
def test_deprecated_and_superseded_pages_are_restorable(text: str) -> None:
    draft = build_restore_draft(restore_request(), page_text(text), today=TODAY)

    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert frontmatter["status"] == "active"
    assert "superseded_by" not in frontmatter


@pytest.mark.parametrize("status", ["active", "draft"])
def test_draft_refuses_a_page_that_is_not_retired(status: str) -> None:
    with pytest.raises(ValueError, match="not a retired page"):
        build_restore_draft(restore_request(), page_text(page(status)), today=TODAY)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"path": "../a.md"}, "path"),
        ({"reason": " "}, "reason"),
        ({"reason": "two\nlines"}, "reason"),
        ({"basis": "maybe"}, "basis"),
        ({"candidate_key": ""}, "candidate_key"),
    ],
)
def test_validation_names_the_bad_field(overrides: dict[str, object], field: str) -> None:
    problems = validate_restore(restore_request(**overrides))

    assert any(problem.startswith(field) for problem in problems)


def test_restore_of_an_active_page_is_rejected_without_calling_the_vault(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, page("active"))
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(vault,)).restore(restore_request())

    assert result.status == "rejected"
    assert writer.calls == [] and writer.proposals == []
    assert any("not a retired page" in message for message in result.messages)


def test_restore_of_a_missing_page_is_rejected_without_calling_the_vault(tmp_path: Path) -> None:
    writer = RecordingWriter()

    result = make_service(tmp_path, writer).restore(restore_request())

    assert result.status == "rejected"
    assert writer.calls == [] and writer.proposals == []


def test_stated_restore_is_published_through_publish_draft(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, RETIRED_PAGE)
    before = file_bytes(vault.path)
    writer = RecordingWriter(WriteOutcome("published", written_paths=(PATH,)))

    result = make_service(tmp_path, writer, vaults=(vault,)).restore(restore_request())

    assert result.status == "published"
    assert len(writer.calls) == 1 and writer.proposals == []
    assert writer.drafts[0]["frontmatter"] == {
        "status": "active",
        "restored_at": "2026-11-02",
        "restored_reason": "Postgres was rolled back.",
    }
    assert file_bytes(vault.path) == before


def test_inferred_restore_goes_to_review_propose(tmp_path: Path) -> None:
    vault = make_vault(tmp_path, "main")
    add_page(vault, PATH, RETIRED_PAGE)
    writer = RecordingWriter()

    result = make_service(tmp_path, writer, vaults=(vault,)).restore(restore_request(basis="inferred"))

    assert result.status == "proposed"
    assert writer.calls == [] and len(writer.proposals) == 1
