from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.test_decision_memory_service import FakeMetadataStore, FakeStatusService, make_catalog
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.decision_memory import DecisionMemoryService
from vault_graph.memory.issue_memory import IssueMemoryService
from vault_graph.memory.memory_models import DecisionMemoryProjection, OpenQuestionsProjection
from vault_graph.memory.memory_request_context import MemoryRequestContext
from vault_graph.memory.memory_source_reader import MemorySourceReader
from vault_graph.memory.project_memory import ProjectMemoryService


class RecordingDecisionService:
    def __init__(self, projection: DecisionMemoryProjection) -> None:
        self.projection = projection
        self.contexts: list[MemoryRequestContext] = []

    def _list_decisions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        **kwargs: object,
    ) -> DecisionMemoryProjection:
        del kwargs
        self.contexts.append(context)
        return self.projection


class RecordingIssueService:
    def __init__(self, projection: OpenQuestionsProjection) -> None:
        self.projection = projection
        self.contexts: list[MemoryRequestContext] = []

    def _open_questions_from_context(
        self,
        *,
        context: MemoryRequestContext,
        **kwargs: object,
    ) -> OpenQuestionsProjection:
        del kwargs
        self.contexts.append(context)
        return self.projection


def test_project_memory_composes_decisions_and_open_questions(tmp_path: Path) -> None:
    decision_doc = make_document("main", "wiki/decisions/use-mcp.md", "decision")
    issue_doc = replace(make_document("main", "wiki/issues/open.md", "issue"), frontmatter={"status": "open"})
    chunks = (
        make_chunk("main", decision_doc.document_id, decision_doc.path, chunk_id="decision"),
        make_chunk("main", issue_doc.document_id, issue_doc.path, chunk_id="issue"),
    )
    service = make_service(tmp_path, documents=(decision_doc, issue_doc), chunks=chunks)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert projection.vaults[0].decisions[0].path == decision_doc.path
    assert projection.vaults[0].open_questions[0].path == issue_doc.path


def test_project_memory_reuses_one_request_context_for_decisions_and_open_questions(tmp_path: Path) -> None:
    document = make_document("main", "docs/status.md", "status")
    store = FakeMetadataStore((document,), (make_chunk("main", document.document_id, document.path),))
    base_service = make_service(tmp_path, metadata_store=store)
    context = base_service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))
    decision = RecordingDecisionService(
        DecisionMemoryProjection(
            requested_scope=context.requested_scope,
            actual_scopes=context.actual_scopes,
            topic=None,
            vaults=(),
            warnings=(),
            generated_at=context.generated_at,
        )
    )
    issue = RecordingIssueService(
        OpenQuestionsProjection(
            requested_scope=context.requested_scope,
            actual_scopes=context.actual_scopes,
            vaults=(),
            warnings=(),
            generated_at=context.generated_at,
        )
    )
    service = make_service(tmp_path, metadata_store=store, decision_service=decision, issue_service=issue)

    service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert len(store.document_reads) <= 2
    assert len(decision.contexts) == 1
    assert decision.contexts[0] is issue.contexts[0]


def test_project_memory_groups_current_state_constraints_priorities_and_stale_areas(tmp_path: Path) -> None:
    current = replace(make_document("main", "docs/status.md", "current"), frontmatter={"type": "project_status"})
    constraint = make_document("main", "docs/policy.md", "constraint")
    priority = make_document("main", "docs/roadmap.md", "priority")
    stale = replace(make_document("main", "docs/deprecated-area.md", "stale"), frontmatter={"status": "deprecated"})
    documents = (current, constraint, priority, stale)
    chunks = tuple(
        make_chunk("main", document.document_id, document.path, chunk_id=document.content_hash)
        for document in documents
    )
    service = make_service(tmp_path, documents=documents, chunks=chunks)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))
    vault = projection.vaults[0]

    assert [item.kind for item in vault.current_state] == ["current_state", "current_state"]
    assert [item.kind for item in vault.constraints] == ["constraint"]
    assert [item.kind for item in vault.next_priorities] == ["next_priority"]
    assert [item.kind for item in vault.stale_areas] == ["stale_area"]


def test_project_memory_marks_same_document_multi_group_matches_as_ambiguous(tmp_path: Path) -> None:
    roadmap = make_document("main", "docs/roadmap.md", "roadmap")
    chunk = make_chunk("main", roadmap.document_id, roadmap.path, chunk_id="roadmap")
    service = make_service(tmp_path, documents=(roadmap,), chunks=(chunk,))

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))
    vault = projection.vaults[0]

    assert vault.current_state[0].warnings[0].code == "ambiguous_classification"
    assert vault.next_priorities[0].warnings[0].code == "ambiguous_classification"


def test_project_memory_does_not_emit_backend_stale_as_stale_area_item(tmp_path: Path) -> None:
    service = make_service(tmp_path, status_service=FakeStatusService())

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].stale_areas == ()


def test_project_memory_empty_metadata_returns_no_memory_items_warning(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert any(warning.code == "no_memory_items_found" for warning in projection.vaults[0].warnings)


def test_project_memory_keeps_per_group_limit_per_vault(tmp_path: Path) -> None:
    documents = tuple(
        replace(make_document("main", f"docs/status-{index}.md", str(index)), frontmatter={"type": "project_status"})
        for index in range(3)
    )
    chunks = tuple(
        make_chunk("main", document.document_id, document.path, chunk_id=f"c{index}")
        for index, document in enumerate(documents)
    )
    service = make_service(tmp_path, documents=documents, chunks=chunks)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)), limit=2)

    assert len(projection.vaults[0].current_state) == 2


def test_project_memory_bounds_project_candidate_chunk_reads_before_scanning_all_matches(tmp_path: Path) -> None:
    documents = tuple(
        replace(make_document("main", f"docs/status-{index:02}.md", str(index)), frontmatter={"type": "project_status"})
        for index in range(80)
    )
    chunks = tuple(
        make_chunk("main", document.document_id, document.path, chunk_id=f"c{index}")
        for index, document in enumerate(documents)
    )
    store = FakeMetadataStore(documents, chunks)
    service = make_service(tmp_path, metadata_store=store)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)), limit=1)

    assert len(projection.vaults[0].current_state) == 1
    assert len(store.document_reads) == 1


def test_project_memory_multi_vault_output_stays_grouped_by_vault_id(tmp_path: Path) -> None:
    main = replace(make_document("main", "docs/status.md", "main"), frontmatter={"type": "project_status"})
    work = replace(make_document("work", "docs/status.md", "work"), frontmatter={"type": "project_status"})
    chunks = (
        make_chunk("main", main.document_id, main.path, chunk_id="same"),
        make_chunk("work", work.document_id, work.path, chunk_id="same"),
    )
    service = make_service(tmp_path, vault_ids=("main", "work"), documents=(main, work), chunks=chunks)

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("docs",)))

    assert [vault.vault_id for vault in projection.vaults] == ["main", "work"]
    assert projection.vaults[0].current_state[0].item_id != projection.vaults[1].current_state[0].item_id


def test_project_memory_does_not_open_graph_service_as_side_effect(tmp_path: Path) -> None:
    document = make_document("main", "wiki/decisions/use-mcp.md", "decision")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision")
    graph_calls = 0

    def provider_factory() -> object:
        nonlocal graph_calls
        graph_calls += 1
        raise AssertionError("graph should not open for project memory")

    service = make_service(tmp_path, documents=(document,), chunks=(chunk,), provider_factory=provider_factory)

    service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert graph_calls == 0


def test_project_memory_excludes_root_readme_from_current_state(tmp_path: Path) -> None:
    readme = replace(make_document("main", "README.md", "readme"), frontmatter={"type": "overview"})
    service = make_service(
        tmp_path,
        documents=(readme,),
        chunks=(make_chunk("main", readme.document_id, readme.path, chunk_id="readme"),),
    )

    projection = service.summarize(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].current_state == ()


def make_service(
    tmp_path: Path,
    *,
    vault_ids: tuple[str, ...] = ("main",),
    documents: tuple[DocumentSnapshot, ...] = (),
    chunks: tuple[ChunkSnapshot, ...] = (),
    metadata_store: FakeMetadataStore | None = None,
    status_service: FakeStatusService | None = None,
    provider_factory: Any | None = None,
    decision_service: Any | None = None,
    issue_service: Any | None = None,
) -> ProjectMemoryService:
    store = metadata_store or FakeMetadataStore(documents, chunks)
    catalog = make_catalog(tmp_path, vault_ids=vault_ids)
    source_reader = MemorySourceReader(metadata_store=store)  # type: ignore[arg-type]
    status = status_service or FakeStatusService()
    decision = decision_service or DecisionMemoryService(
        catalog=catalog,
        source_reader=source_reader,
        status_service=status,  # type: ignore[arg-type]
        decision_trace_provider_factory=provider_factory,
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    issue = issue_service or IssueMemoryService(
        catalog=catalog,
        source_reader=source_reader,
        status_service=status,  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
    return ProjectMemoryService(
        catalog=catalog,
        source_reader=source_reader,
        decision_service=decision,
        issue_service=issue,
        status_service=status,  # type: ignore[arg-type]
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )
