"""The four Vault drafts (add, update, retire, retire with replacement) depend only on input and date.

Source: spec 2026-11-02-vault-long-term-memory V3 draft table, 계약2, 계약3, 결정S6, 결정S8.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from vault_graph.operation.memory import memory_drafts
from vault_graph.operation.memory.memory_drafts import (
    build_remember_draft,
    build_retire_draft,
    build_update_draft,
)
from vault_graph.operation.memory.memory_ports import PageText
from vault_graph.operation.memory.memory_requests import RememberRequest, RetireRequest, UpdateRequest

TODAY = date(2026, 11, 2)

CURRENT_PAGE = """---
title: Use SQLite
type: decision
status: active
created: 2026-10-01
updated: 2026-10-01
owner: human
summary: Use SQLite
source_count: 1
tags: [storage, index]
related: []
confidence: high
quality:
  provenance: section
  links: unchecked
  review_required: false
---

# Use SQLite

Old body.
"""


def remember_request(**overrides: object) -> RememberRequest:
    values: dict[str, object] = {
        "title": "Use SQLite",
        "kind": "decision",
        "body": "We keep the index in SQLite.",
        "evidence": ("Session note A",),
        "basis": "stated",
    }
    values.update(overrides)
    return RememberRequest(**values)  # type: ignore[arg-type]


def update_request(**overrides: object) -> UpdateRequest:
    values: dict[str, object] = {
        "path": "wiki/decisions/use-sqlite.md",
        "body": "We keep the index in SQLite files under Graph Home.",
        "evidence": ("User correction 2026-11-02",),
        "basis": "stated",
    }
    values.update(overrides)
    return UpdateRequest(**values)  # type: ignore[arg-type]


def current_page(text: str = CURRENT_PAGE) -> PageText:
    return PageText(text=text, sha256="0" * 64)


def test_remember_draft_without_memory_fields_is_the_previous_upsert_page() -> None:
    draft = build_remember_draft(remember_request(evidence=("Session note A", "Session note B")), today=TODAY)

    assert draft["operation"] == "upsert-page"
    assert draft["path"] == "wiki/decisions/use-sqlite.md"
    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert "memory_schema" not in frontmatter and "pin" not in frontmatter and "memory_kind" not in frontmatter
    assert draft["body"] == (
        "# Use SQLite\n\nWe keep the index in SQLite.\n\n## Evidence\n\nStatus: stated\n\n"
        "- Evidence: Session note A\n- Evidence: Session note B\n"
    )


def test_remember_draft_adds_memory_schema_with_pin_and_memory_kind() -> None:
    draft = build_remember_draft(remember_request(pin=True, memory_kind="rule"), today=TODAY)

    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert frontmatter["memory_schema"] == "vault-memory/v1"
    assert frontmatter["pin"] is True
    assert frontmatter["memory_kind"] == "rule"


def test_remember_draft_with_only_memory_kind_has_no_pin_field() -> None:
    frontmatter = build_remember_draft(remember_request(memory_kind="preference"), today=TODAY)["frontmatter"]

    assert isinstance(frontmatter, dict)
    assert frontmatter["memory_schema"] == "vault-memory/v1"
    assert "pin" not in frontmatter


def test_remember_draft_writes_the_basis_in_the_evidence_status_line() -> None:
    draft = build_remember_draft(remember_request(basis="inferred"), today=TODAY)

    assert "Status: inferred" in str(draft["body"])


def test_update_draft_keeps_current_frontmatter_and_replaces_the_body() -> None:
    draft = build_update_draft(update_request(), current_page(), today=TODAY)

    assert draft == {
        "version": 1,
        "operation": "upsert-page",
        "path": "wiki/decisions/use-sqlite.md",
        "frontmatter": {
            "title": "Use SQLite",
            "type": "decision",
            "status": "active",
            "created": "2026-10-01",
            "updated": "2026-11-02",
            "owner": "human",
            "summary": "Use SQLite",
            "source_count": 1,
            "tags": ["storage", "index"],
            "related": [],
            "confidence": "high",
            "quality": {"provenance": "section", "links": "unchecked", "review_required": False},
        },
        "body": (
            "# Use SQLite\n\nWe keep the index in SQLite files under Graph Home.\n\n## Evidence\n\n"
            "Status: stated\n\n- Evidence: User correction 2026-11-02\n"
        ),
        "log": {
            "event_type": "decision",
            "title": "Update memory: Use SQLite",
            "items": ["Updated [[decisions/use-sqlite]]."],
        },
    }


def test_update_draft_changes_only_the_given_fields() -> None:
    draft = build_update_draft(
        update_request(title="Use SQLite files", pin=False, memory_kind="decision", evidence=("A", "B")),
        current_page(),
        today=TODAY,
    )

    frontmatter = draft["frontmatter"]
    assert isinstance(frontmatter, dict)
    assert frontmatter["title"] == frontmatter["summary"] == "Use SQLite files"
    assert frontmatter["pin"] is False
    assert frontmatter["memory_kind"] == "decision"
    assert frontmatter["memory_schema"] == "vault-memory/v1"
    assert frontmatter["source_count"] == 2
    assert frontmatter["owner"] == "human"
    assert str(draft["body"]).startswith("# Use SQLite files\n\n")


def test_update_draft_of_a_page_without_frontmatter_raises() -> None:
    with pytest.raises(ValueError, match="frontmatter"):
        build_update_draft(update_request(), current_page("# No frontmatter\n"), today=TODAY)


def test_retire_draft_without_replacement_is_a_frontmatter_only_patch() -> None:
    draft = build_retire_draft(
        RetireRequest(path="wiki/decisions/use-sqlite.md", reason="We moved to Postgres.", basis="stated"),
        today=TODAY,
    )

    assert draft == {
        "version": 1,
        "operation": "patch-page",
        "path": "wiki/decisions/use-sqlite.md",
        "frontmatter": {"status": "retired", "retired_reason": "We moved to Postgres.", "retired_at": "2026-11-02"},
        "log": {
            "event_type": "manual-note",
            "title": "Retire memory: decisions/use-sqlite",
            "items": ["Retired [[decisions/use-sqlite]]: We moved to Postgres."],
        },
    }


def test_retire_draft_with_replacement_deprecates_and_links_the_replacement() -> None:
    draft = build_retire_draft(
        RetireRequest(
            path="wiki/decisions/use-sqlite.md",
            reason="Replaced.",
            basis="stated",
            replaced_by="wiki/decisions/use-postgres.md",
        ),
        today=TODAY,
    )

    assert draft["operation"] == "patch-page"
    assert "edits" not in draft and "body" not in draft
    assert draft["frontmatter"] == {"status": "deprecated", "superseded_by": ["decisions/use-postgres"]}
    assert draft["log"] == {
        "event_type": "manual-note",
        "title": "Retire memory: decisions/use-sqlite",
        "items": ["Retired [[decisions/use-sqlite]], replaced by [[decisions/use-postgres]]: Replaced."],
    }


@pytest.mark.parametrize(
    ("build", "args"),
    [
        (build_remember_draft, (remember_request(pin=True, memory_kind="rule"),)),
        (build_update_draft, (update_request(title="T", pin=True), current_page())),
        (build_retire_draft, (RetireRequest(path="wiki/a.md", reason="r", basis="stated"),)),
        (
            build_retire_draft,
            (RetireRequest(path="wiki/a.md", reason="r", basis="stated", replaced_by="wiki/b.md"),),
        ),
    ],
    ids=["add", "update", "retire", "retire-replaced"],
)
def test_drafts_are_pure_functions_of_input_and_date(build: object, args: tuple[object, ...]) -> None:
    assert callable(build)
    first = build(*args, today=TODAY)
    second = build(*args, today=TODAY)

    assert first == second
    assert list(inspect.signature(build).parameters)[-1] == "today"


def test_draft_module_reads_no_files_and_no_clock() -> None:
    source = inspect.getsource(memory_drafts)

    for forbidden in ("open(", "read_text", "read_bytes", "date.today", "datetime.now", "Path("):
        assert forbidden not in source
