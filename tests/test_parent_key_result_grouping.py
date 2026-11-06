"""Spec 2026-11-05 §4.2.6-6, A-7: session windows of one exchange come back as one search result."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from tests.fakes.search_readiness import ready_report
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_models import SourceLocator
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.interface.mcp.mcp_tool_serialization import explanation_records_for_search
from vault_graph.interface.mcp.mcp_uri import parse_mcp_resource_uri
from vault_graph.interface.mcp.metadata_resource_reader import MetadataResourceReader
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchMode, SearchResponse
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

SESSION_PATH = "raw/sessions/2026-11-05-session-a.md"
SESSION_ID = "session-a"
HUMAN_TURN = "Please fix the keyword frontmatter writer so exchange metadata becomes searchable."
ANSWER_TURN = "I changed the keyword frontmatter writer and the exchange metadata is now searchable."
EDITED_FILE = "src/vault_graph/storage/local/sqlite_keyword_index.py"
TOOL_NAMES = ("Bash", "Edit")


def line_locator(start: int, end: int) -> SourceLocator:
    return SourceLocator(
        scheme="markdown",
        coordinates=(("line", f"{start}-{end}"),),
        start_offset=start,
        end_offset=end,
        offset_unit="line",
    )


EXCHANGE_LOCATOR = line_locator(5, 16)


def session_document(vault_id: str = "default") -> DocumentSnapshot:
    return replace(
        make_document(vault_id, SESSION_PATH, "session-hash"),
        kind="raw",
        frontmatter={"schema": "vault-session/v2", "session_id": SESSION_ID},
        source_role="raw_evidence",
    )


def session_window(
    document: DocumentSnapshot,
    *,
    exchange_id: str,
    window: int,
    text: str,
    locator: SourceLocator,
    parent_locator: SourceLocator,
    keyword_metadata: str | None,
) -> ChunkSnapshot:
    return replace(
        make_chunk(
            document.vault_id,
            document.document_id,
            document.path,
            chunk_id=f"{SESSION_ID}:{exchange_id}:w{window}",
            text=text,
        ),
        source_role="raw_evidence",
        provenance_family_id=document.provenance_family_id,
        section="Q: Please fix the keyword frontmatter writer",
        anchor=None,
        section_path=("Session 2026-11-05 part1", "Q: Please fix the keyword frontmatter writer"),
        source_locators=(locator,),
        document_order=window,
        parent_key=f"{SESSION_ID}:{exchange_id}",
        parent_locators=(parent_locator,),
        keyword_metadata=keyword_metadata,
    )


def exchange_metadata() -> str:
    return f"files: {EDITED_FILE} commands: pytest -q tools: {', '.join(TOOL_NAMES)} errors: 1 outcome: resolved"


def session_windows(document: DocumentSnapshot) -> list[ChunkSnapshot]:
    """Three windows of exchange ex-1 and one window of exchange ex-2, as the v2 chunker would emit them."""
    metadata = exchange_metadata()
    return [
        session_window(
            document,
            exchange_id="ex-1",
            window=0,
            text=f"### user\n{HUMAN_TURN}",
            locator=line_locator(7, 8),
            parent_locator=EXCHANGE_LOCATOR,
            keyword_metadata=metadata,
        ),
        session_window(
            document,
            exchange_id="ex-1",
            window=1,
            text=f"### assistant\n{ANSWER_TURN}",
            locator=line_locator(9, 12),
            parent_locator=EXCHANGE_LOCATOR,
            keyword_metadata=metadata,
        ),
        session_window(
            document,
            exchange_id="ex-1",
            window=2,
            text="### assistant\nThe frontmatter column now ends with the exchange metadata line.",
            locator=line_locator(13, 16),
            parent_locator=EXCHANGE_LOCATOR,
            keyword_metadata=metadata,
        ),
        session_window(
            document,
            exchange_id="ex-2",
            window=3,
            text="### user\nWhat did the release checklist say about tags?",
            locator=line_locator(19, 22),
            parent_locator=line_locator(17, 30),
            keyword_metadata="files: docs/RELEASE.md commands: git tag tools: Read errors: 0 outcome: answered",
        ),
    ]


def general_document_with_chunks(vault_id: str = "default") -> tuple[DocumentSnapshot, list[ChunkSnapshot]]:
    document = make_document(vault_id, "wiki/keyword-search.md", "wiki-hash")
    chunks = [
        replace(
            make_chunk(
                vault_id,
                document.document_id,
                document.path,
                chunk_id=f"wiki-chunk-{order}",
                text=f"Keyword search part {order} explains how the frontmatter column is ranked.",
            ),
            document_order=order,
            source_locators=(line_locator(order * 10 + 1, order * 10 + 5),),
        )
        for order in range(2)
    ]
    return document, chunks


class StaticReadiness:
    def __init__(self, report: SearchReadinessReport) -> None:
        self._report = report

    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return self._report


def catalog_for(tmp_path: Path) -> VaultCatalog:
    root = tmp_path / "default"
    root.mkdir(exist_ok=True)
    return VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)],
        active_vault_id="default",
    )


def indexed_store(tmp_path: Path) -> SQLiteMetadataStore:
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    session = session_document()
    general, general_chunks = general_document_with_chunks()
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[session, general],
        chunks=[*session_windows(session), *general_chunks],
        tombstones=[],
    )
    return store


def keyword_search(tmp_path: Path, query_text: str, *, mode: SearchMode = "all") -> SearchResponse:
    store = indexed_store(tmp_path)
    catalog = catalog_for(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=SQLiteKeywordIndex(tmp_path / "metadata.sqlite3"),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )
    return service.search(query_text=query_text, requested_scope=catalog.default_scope(), limit=10, mode=mode)


def test_store_keeps_parent_fields_and_keyword_metadata(tmp_path: Path) -> None:
    store = indexed_store(tmp_path)
    expected = {
        chunk.chunk_id: replace(chunk, index_revision="metadata-1") for chunk in session_windows(session_document())
    }

    resolved = store.resolve_chunk(vault_id="default", chunk_id=f"{SESSION_ID}:ex-1:w1")
    listed = store.list_document_chunks(vault_id="default", document_id=session_document().document_id)
    scoped = store.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("raw",)))

    assert resolved == expected[f"{SESSION_ID}:ex-1:w1"]
    assert {chunk.chunk_id: chunk for chunk in listed} == expected
    assert {chunk.chunk_id: chunk for chunk in scoped} == expected


def test_general_chunk_keeps_empty_parent_fields(tmp_path: Path) -> None:
    store = indexed_store(tmp_path)

    resolved = store.resolve_chunk(vault_id="default", chunk_id="wiki-chunk-0")

    assert resolved is not None
    assert (resolved.parent_key, resolved.parent_locators, resolved.keyword_metadata) == (None, (), None)


def test_store_without_parent_columns_stays_readable_and_upgrades_on_writable_open(tmp_path: Path) -> None:
    database_path = tmp_path / "metadata.sqlite3"
    indexed_store(tmp_path)
    with sqlite3.connect(database_path) as connection:
        for column in ("parent_key", "parent_locators_json", "keyword_metadata"):
            connection.execute(f"ALTER TABLE chunks DROP COLUMN {column}")

    reader = SQLiteMetadataStore(database_path, initialize=False)
    chunk = reader.resolve_chunk(vault_id="default", chunk_id=f"{SESSION_ID}:ex-1:w0")
    listed = reader.list_chunks(QueryScope(vault_ids=("default",), content_scopes=("raw", "wiki")))

    assert reader.health().ok is True
    assert chunk is not None
    assert (chunk.parent_key, chunk.parent_locators, chunk.keyword_metadata) == (None, (), None)
    assert len(listed) == 6

    writer = SQLiteMetadataStore(database_path, initialize=True)
    session = session_document()
    writer.apply_metadata_revision(
        index_revision="metadata-2", documents=[session], chunks=session_windows(session), tombstones=[]
    )
    upgraded = writer.resolve_chunk(vault_id="default", chunk_id=f"{SESSION_ID}:ex-1:w0")
    assert upgraded is not None
    assert upgraded.parent_key == f"{SESSION_ID}:ex-1"


def test_windows_of_one_exchange_return_as_one_result_at_exchange_range(tmp_path: Path) -> None:
    response = keyword_search(tmp_path, "searchable exchange metadata frontmatter writer")

    session_results = [result for result in response.results if result.evidence[0].path == SESSION_PATH]
    ex1_results = [result for result in session_results if ":ex-1:" in result.evidence[0].chunk_id]
    assert len(ex1_results) == 1
    grouped = ex1_results[0]
    assert grouped.evidence[0].source_locators == (EXCHANGE_LOCATOR,)
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3")
    best_window = store.resolve_chunk(vault_id="default", chunk_id=grouped.evidence[0].chunk_id)
    assert best_window is not None
    assert grouped.summary == " ".join(best_window.text.split())
    assert [warning.code for warning in grouped.warnings] == ["parent_grouped"]
    assert "3 windows" in grouped.warnings[0].message
    assert [result.rank for result in response.results] == list(range(1, len(response.results) + 1))


def test_grouped_window_count_is_in_result_explanation(tmp_path: Path) -> None:
    response = keyword_search(tmp_path, "searchable exchange metadata frontmatter writer")

    records = explanation_records_for_search(response)
    session_record = next(record for record in records if ":ex-1:" in record.evidence[0].chunk_id)

    assert any(
        warning.code == "parent_grouped" and "3 windows" in warning.message for warning in session_record.warnings
    )


def test_general_document_chunks_are_not_grouped(tmp_path: Path) -> None:
    response = keyword_search(tmp_path, "Keyword search part explains ranked")

    general = [result for result in response.results if result.evidence[0].path == "wiki/keyword-search.md"]
    assert sorted(result.evidence[0].chunk_id for result in general) == ["wiki-chunk-0", "wiki-chunk-1"]
    assert all(result.warnings == () for result in general)
    locators = {result.evidence[0].chunk_id: result.evidence[0].source_locators for result in general}
    assert locators == {"wiki-chunk-0": (line_locator(1, 5),), "wiki-chunk-1": (line_locator(11, 15),)}


def test_mcp_document_resource_at_grouped_location_has_human_turn_and_answer(tmp_path: Path) -> None:
    """A-7 MCP check with constructed v2 windows. The real v2 chunker fixture (#21) is not used here."""
    response = keyword_search(tmp_path, "searchable exchange metadata frontmatter writer")
    records = explanation_records_for_search(response)
    session_record = next(record for record in records if ":ex-1:" in record.evidence[0].chunk_id)
    document_link = next(link for link in session_record.resource_links if link["rel"] == "evidence")

    catalog = catalog_for(tmp_path)
    reader = MetadataResourceReader(catalog=catalog, metadata_store=SQLiteMetadataStore(tmp_path / "metadata.sqlite3"))
    body = reader.read_document(parse_mcp_resource_uri(str(document_link["uri"]), catalog=catalog))

    assert HUMAN_TURN in body.text
    assert ANSWER_TURN in body.text
