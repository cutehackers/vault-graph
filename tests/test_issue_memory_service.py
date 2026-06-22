from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_decision_memory_service import FakeMetadataStore, FakeStatusService, make_catalog
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.issue_memory import IssueMemoryService
from vault_graph.memory.memory_source_reader import MemorySourceReader


def test_issue_service_returns_open_issue_path_with_active_status(tmp_path: Path) -> None:
    document = replace(make_document("main", "wiki/issues/open.md", "hash"), frontmatter={"status": "open"})
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="issue", text="Open issue")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    item = projection.vaults[0].questions[0]
    assert item.kind == "open_question"
    assert item.claim_status == "stated"
    assert item.status == "open"
    assert item.document_resource_kinds == ("document", "page", "issue")


def test_issue_service_returns_frontmatter_question_with_active_status(tmp_path: Path) -> None:
    document = replace(
        make_document("main", "docs/question.md", "hash"),
        frontmatter={"type": "question", "status": "todo"},
    )
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="question", text="Question")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].questions[0].claim_status == "stated"


@pytest.mark.parametrize("status", ["closed", "resolved", "done", "accepted", "superseded", "deprecated", "cancelled"])
def test_issue_service_excludes_closed_resolved_done_and_accepted_statuses(tmp_path: Path, status: str) -> None:
    document = replace(make_document("main", "wiki/issues/old.md", "hash"), frontmatter={"status": status})
    chunk = replace(make_chunk("main", document.document_id, document.path, chunk_id="old"), section="TODO")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert projection.vaults[0].questions == ()


def test_issue_service_missing_status_requires_explicit_open_heading_warning(tmp_path: Path) -> None:
    document = make_document("main", "wiki/issues/missing-status.md", "hash")
    chunk = replace(make_chunk("main", document.document_id, document.path, chunk_id="todo"), section="Open Questions")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    item = projection.vaults[0].questions[0]
    assert item.claim_status == "heading_candidate"
    assert item.warnings[0].code == "missing_issue_status"


def test_issue_service_heading_todo_inside_metadata_selected_document_is_candidate(tmp_path: Path) -> None:
    document = make_document("main", "docs/todo-list.md", "hash")
    chunk = replace(make_chunk("main", document.document_id, document.path, chunk_id="todo"), section="TODO")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].questions[0].claim_status == "heading_candidate"


def test_issue_service_does_not_scan_todo_headings_for_unselected_documents(tmp_path: Path) -> None:
    selected = make_document("main", "docs/todo-list.md", "selected")
    unselected = make_document("main", "docs/random.md", "unselected")
    chunks = (
        replace(make_chunk("main", selected.document_id, selected.path, chunk_id="selected"), section="TODO"),
        replace(make_chunk("main", unselected.document_id, unselected.path, chunk_id="unselected"), section="TODO"),
    )
    store = FakeMetadataStore((selected, unselected), chunks)
    service = make_service(tmp_path, metadata_store=store)

    service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert store.document_reads == [selected.document_id]


def test_issue_service_prefers_late_todo_heading_evidence_chunk(tmp_path: Path) -> None:
    document = make_document("main", "docs/todo-list.md", "hash")
    chunks = (
        replace(make_chunk("main", document.document_id, document.path, chunk_id="body"), section="Body"),
        replace(make_chunk("main", document.document_id, document.path, chunk_id="notes"), section="Notes"),
        replace(make_chunk("main", document.document_id, document.path, chunk_id="todo"), section="TODO"),
    )
    service = make_service(tmp_path, documents=(document,), chunks=chunks)

    projection = service.open_questions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].questions[0].evidence[0].chunk_id == "todo"


def test_issue_service_enforces_candidate_read_limit_with_warning(tmp_path: Path) -> None:
    documents = tuple(make_document("main", f"docs/todo-{index}.md", str(index)) for index in range(55))
    chunks = tuple(
        replace(make_chunk("main", document.document_id, document.path, chunk_id=f"c{index}"), section="TODO")
        for index, document in enumerate(documents)
    )
    service = make_service(tmp_path, documents=documents, chunks=chunks)

    projection = service.open_questions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)),
        limit=1,
    )

    assert len(projection.vaults[0].questions) == 1
    assert any(warning.code == "candidate_scan_truncated" for warning in projection.vaults[0].warnings)


def test_issue_service_excluded_statuses_do_not_consume_candidate_cap(tmp_path: Path) -> None:
    closed = tuple(
        replace(
            make_document("main", f"wiki/issues/closed-{index:02}.md", str(index)),
            frontmatter={"status": "closed"},
        )
        for index in range(55)
    )
    active = replace(make_document("main", "wiki/issues/open.md", "active"), frontmatter={"status": "open"})
    documents = (*closed, active)
    chunks = tuple(
        make_chunk("main", document.document_id, document.path, chunk_id=f"c{index}")
        for index, document in enumerate(documents)
    )
    service = make_service(tmp_path, documents=documents, chunks=chunks)

    projection = service.open_questions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        limit=1,
    )

    assert [item.path for item in projection.vaults[0].questions] == ["wiki/issues/open.md"]


def test_issue_service_groups_identical_issues_by_vault_without_id_collision(tmp_path: Path) -> None:
    main = replace(make_document("main", "wiki/issues/same.md", "main"), frontmatter={"status": "open"})
    work = replace(make_document("work", "wiki/issues/same.md", "work"), frontmatter={"status": "open"})
    chunks = (
        make_chunk("main", main.document_id, main.path, chunk_id="same", text="Same"),
        make_chunk("work", work.document_id, work.path, chunk_id="same", text="Same"),
    )
    service = make_service(tmp_path, vault_ids=("main", "work"), documents=(main, work), chunks=chunks)

    projection = service.open_questions(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",))
    )

    assert [vault.vault_id for vault in projection.vaults] == ["main", "work"]
    assert projection.vaults[0].questions[0].item_id != projection.vaults[1].questions[0].item_id


def make_service(
    tmp_path: Path,
    *,
    vault_ids: tuple[str, ...] = ("main",),
    documents: tuple[DocumentSnapshot, ...] = (),
    chunks: tuple[ChunkSnapshot, ...] = (),
    metadata_store: FakeMetadataStore | None = None,
) -> IssueMemoryService:
    store = metadata_store or FakeMetadataStore(documents, chunks)
    return IssueMemoryService(
        catalog=make_catalog(tmp_path, vault_ids=vault_ids),
        source_reader=MemorySourceReader(metadata_store=store),  # type: ignore[arg-type]
        status_service=FakeStatusService(),  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
