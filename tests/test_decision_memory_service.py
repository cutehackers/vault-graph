from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.test_graph_retrieval_contract import make_metadata_evidence_from_graph_ref
from tests.test_graph_store_contract import make_entity
from tests.test_mcp_tools import make_decision_trace_response, make_status_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.memory.decision_memory import DecisionMemoryService
from vault_graph.memory.memory_source_reader import MemorySourceReader
from vault_graph.retrieval.graph_retrieval import DecisionTraceResponse, DecisionTraceStep
from vault_graph.storage.interfaces.metadata_store import EvidenceReference


class FakeMetadataStore:
    def __init__(self, documents: tuple[DocumentSnapshot, ...], chunks: tuple[ChunkSnapshot, ...]) -> None:
        self.documents = documents
        self.chunks = chunks
        self.document_reads: list[str] = []

    def list_documents(self, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        return tuple(
            document
            for document in self.documents
            if document.vault_id in scope.vault_ids
            and any(
                document.path == content_scope or document.path.startswith(f"{content_scope}/")
                for content_scope in scope.content_scopes
            )
        )

    def list_document_chunks(self, *, vault_id: str, document_id: str) -> tuple[ChunkSnapshot, ...]:
        self.document_reads.append(document_id)
        return tuple(chunk for chunk in self.chunks if chunk.vault_id == vault_id and chunk.document_id == document_id)

    def resolve_chunk_evidence(self, *, vault_id: str, document_id: str, chunk_id: str) -> EvidenceReference | None:
        chunk = next(
            (
                value
                for value in self.chunks
                if value.vault_id == vault_id and value.document_id == document_id and value.chunk_id == chunk_id
            ),
            None,
        )
        if chunk is None:
            return None
        return EvidenceReference(
            vault_id=vault_id,
            document_id=document_id,
            chunk_id=chunk_id,
            path=chunk.path,
            section=chunk.section,
            anchor=chunk.anchor,
            content_hash=chunk.content_hash,
            raw_sha256="raw-sha",
            metadata_index_revision=chunk.index_revision,
            vault_revision="vault-1",
        )


class FakeStatusService:
    def __init__(self, *, metadata_ok: bool = True) -> None:
        self.report = make_status_report() if metadata_ok else replace(make_status_report(), metadata_ok=False)

    def status(self, *, scope: QueryScope | None = None) -> object:
        del scope
        return self.report


class RecordingDecisionTraceProvider:
    def __init__(self, response: DecisionTraceResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    def decision_trace(self, **kwargs: object) -> DecisionTraceResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_decision_service_returns_canonical_decision_path_as_stated(tmp_path: Path) -> None:
    document = make_document("main", "wiki/decisions/use-mcp.md", "hash")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision", text="Accepted decision")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    item = projection.vaults[0].decisions[0]
    assert item.claim_status == "stated"
    assert item.kind == "decision"
    assert item.document_resource_kinds == ("document", "page", "decision")


def test_decision_service_returns_frontmatter_decision_as_stated(tmp_path: Path) -> None:
    document = replace(make_document("main", "docs/decision.md", "hash"), frontmatter={"type": "decision"})
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision", text="Decision body")
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].decisions[0].claim_status == "stated"


def test_decision_service_marks_heading_only_decision_as_candidate(tmp_path: Path) -> None:
    document = make_document("main", "docs/decision-notes.md", "hash")
    chunk = replace(
        make_chunk("main", document.document_id, document.path, chunk_id="heading", text="Candidate"),
        section="Decision",
    )
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,))

    projection = service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    item = projection.vaults[0].decisions[0]
    assert item.claim_status == "heading_candidate"
    assert item.warnings[0].code == "candidate_decision"


def test_decision_service_does_not_scan_headings_for_unselected_documents(tmp_path: Path) -> None:
    selected = make_document("main", "docs/decision-notes.md", "selected")
    unselected = make_document("main", "docs/random.md", "unselected")
    chunks = (
        replace(make_chunk("main", selected.document_id, selected.path, chunk_id="selected"), section="Decision"),
        replace(make_chunk("main", unselected.document_id, unselected.path, chunk_id="unselected"), section="Decision"),
    )
    store = FakeMetadataStore((selected, unselected), chunks)
    service = make_service(tmp_path, metadata_store=store)

    service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert store.document_reads == [selected.document_id]


def test_decision_service_prefers_late_heading_evidence_chunk(tmp_path: Path) -> None:
    document = make_document("main", "docs/decision-notes.md", "hash")
    chunks = (
        replace(make_chunk("main", document.document_id, document.path, chunk_id="body"), section="Body"),
        replace(make_chunk("main", document.document_id, document.path, chunk_id="more"), section="Notes"),
        replace(make_chunk("main", document.document_id, document.path, chunk_id="late"), section="Decision"),
    )
    service = make_service(tmp_path, documents=(document,), chunks=chunks)

    projection = service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)))

    assert projection.vaults[0].decisions[0].evidence[0].chunk_id == "late"


def test_decision_service_enforces_candidate_read_limit_with_warning(tmp_path: Path) -> None:
    documents = tuple(make_document("main", f"docs/decision-{index}.md", str(index)) for index in range(55))
    chunks = tuple(
        replace(make_chunk("main", document.document_id, document.path, chunk_id=f"c{index}"), section="Decision")
        for index, document in enumerate(documents)
    )
    service = make_service(tmp_path, documents=documents, chunks=chunks)

    projection = service.list_decisions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("docs",)),
        limit=1,
    )

    assert len(projection.vaults[0].decisions) == 1
    assert any(warning.code == "candidate_scan_truncated" for warning in projection.vaults[0].warnings)


def test_decision_service_groups_identical_titles_by_vault_without_id_collision(tmp_path: Path) -> None:
    main = make_document("main", "wiki/decisions/same.md", "main")
    work = make_document("work", "wiki/decisions/same.md", "work")
    chunks = (
        make_chunk("main", main.document_id, main.path, chunk_id="same", text="Same"),
        make_chunk("work", work.document_id, work.path, chunk_id="same", text="Same"),
    )
    service = make_service(tmp_path, vault_ids=("main", "work"), documents=(main, work), chunks=chunks)

    projection = service.list_decisions(
        requested_scope=QueryScope(vault_ids=("main", "work"), content_scopes=("wiki",))
    )

    assert [vault.vault_id for vault in projection.vaults] == ["main", "work"]
    assert projection.vaults[0].decisions[0].item_id != projection.vaults[1].decisions[0].item_id


def test_decision_service_raises_metadata_unavailable_before_document_listing(tmp_path: Path) -> None:
    store = FakeMetadataStore((make_document("main", "wiki/decisions/one.md", "hash"),), ())
    service = make_service(tmp_path, metadata_store=store, metadata_ok=False)

    with pytest.raises(MemoryProjectionError, match="metadata_unavailable"):
        service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)))

    assert store.document_reads == []


def test_decision_service_opens_graph_provider_only_for_topic_graph_enrichment(tmp_path: Path) -> None:
    document = make_document("main", "wiki/decisions/use-mcp.md", "hash")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision", text="Decision")
    provider = RecordingDecisionTraceProvider(make_decision_trace_response())
    calls = 0

    def provider_factory() -> RecordingDecisionTraceProvider:
        nonlocal calls
        calls += 1
        return provider

    service = make_service(tmp_path, documents=(document,), chunks=(chunk,), provider_factory=provider_factory)

    service.list_decisions(requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)), topic="MCP")
    assert calls == 0

    service.list_decisions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        topic="MCP",
        include_graph=True,
    )
    assert calls == 1


def test_decision_service_adds_graph_signal_to_matching_metadata_backed_item(tmp_path: Path) -> None:
    document = make_document("main", "wiki/decisions/use-mcp.md", "hash")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision", text="Decision")
    entity = make_entity("main", document_id=document.document_id, chunk_id=chunk.chunk_id)
    step = DecisionTraceStep(
        rank=1,
        role="decision",
        entity=entity,
        relationship_path=(),
        evidence=(make_metadata_evidence_from_graph_ref(entity.evidence_refs[0]),),
        relationship_status="not_applicable",
        explanation="decision",
    )
    graph_response = replace(make_decision_trace_response(), steps=(step,))
    provider = RecordingDecisionTraceProvider(graph_response)
    service = make_service(tmp_path, documents=(document,), chunks=(chunk,), provider_factory=lambda: provider)

    projection = service.list_decisions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        topic="MCP",
        include_graph=True,
    )

    assert "graph_decision_trace" in projection.vaults[0].decisions[0].matched_signals


def test_decision_service_warns_when_graph_enrichment_unavailable(tmp_path: Path) -> None:
    document = make_document("main", "wiki/decisions/use-mcp.md", "hash")
    chunk = make_chunk("main", document.document_id, document.path, chunk_id="decision", text="Decision")
    service = make_service(
        tmp_path,
        documents=(document,),
        chunks=(chunk,),
        provider_factory=lambda: RecordingDecisionTraceProvider(RuntimeError("graph down")),
    )

    projection = service.list_decisions(
        requested_scope=QueryScope(vault_ids=("main",), content_scopes=("wiki",)),
        topic="MCP",
        include_graph=True,
    )

    assert projection.vaults[0].decisions
    assert any(warning.code == "graph_decision_trace_unavailable" for warning in projection.warnings)


def make_service(
    tmp_path: Path,
    *,
    vault_ids: tuple[str, ...] = ("main",),
    documents: tuple[DocumentSnapshot, ...] = (),
    chunks: tuple[ChunkSnapshot, ...] = (),
    metadata_store: FakeMetadataStore | None = None,
    metadata_ok: bool = True,
    provider_factory: Any | None = None,
) -> DecisionMemoryService:
    store = metadata_store or FakeMetadataStore(documents, chunks)
    return DecisionMemoryService(
        catalog=make_catalog(tmp_path, vault_ids=vault_ids),
        source_reader=MemorySourceReader(metadata_store=store),  # type: ignore[arg-type]
        status_service=FakeStatusService(metadata_ok=metadata_ok),  # type: ignore[arg-type]
        decision_trace_provider_factory=provider_factory,
        clock=lambda: datetime(2026, 6, 18, tzinfo=UTC),
    )


def make_catalog(tmp_path: Path, *, vault_ids: tuple[str, ...]) -> VaultCatalog:
    entries = []
    for vault_id in vault_ids:
        root = tmp_path / vault_id
        root.mkdir(exist_ok=True)
        entries.append(VaultCatalogEntry.from_root(vault_id=vault_id, root_path=root, display_name=vault_id.title()))
    return VaultCatalog.from_entries(entries=entries, active_vault_id=vault_ids[0])
