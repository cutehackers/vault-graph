"""`vault-session-facts/v1` attachments become `derived` chunks (spec 2026-11-16 D28, I1, A3, A18).

Contract: docs/contracts/vault-session-facts-v1.md §3 and §5.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from tests.fakes.search_readiness import ready_report
from vault_graph.indexing.ingestion.chunker_selection import (
    CHUNKER_VERSIONS,
    chunker_selection,
    embedding_input_for,
)
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.session_facts_chunker import SESSION_FACTS_VERSION, SessionFactsChunker
from vault_graph.indexing.ingestion.session_group import exchange_ranges, reprocess_session_groups, session_group_key
from vault_graph.indexing.metadata_indexer import INDEX_CODE_PARTS, MetadataIndexer
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.candidate_ranking import FACT_KEY_WEIGHT, SIGNAL_WEIGHTS, fact_key_score
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchResponse
from vault_graph.storage.interfaces.keyword_index import KeywordHit
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FIXTURES = Path(__file__).parent / "fixtures" / "session_v2"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
PART = f"raw/sessions/claude-code/2026-11-01-{SESSION_ID}-part1.md"
FACTS = f"raw/sessions/claude-code/2026-11-01-{SESSION_ID}-part1.facts.md"


def facts_text(*, schema: str = "vault-session-facts/v1", body: str | None = None) -> str:
    if body is None:
        body = (
            "- 2026-11-01 The user fixed the failing test in src/app.py. (exchange u-001)\n"
            "- 2026-10-30 사용자는 데이터베이스 비밀번호를 .env에 둔다. (exchange u-001)\n"
        )
    return (
        "---\n"
        f"schema: {schema}\n"
        "agent: claude-code\n"
        f'session_id: "{SESSION_ID}"\n'
        "part: 1\n"
        f"source: {PART}\n"
        'source_sha256: "abc"\n'
        "extractor: claude\n"
        "model: claude-sonnet-5-5\n"
        'generated_at: "2026-11-16T03:00:00Z"\n'
        "fact_count: 2\n"
        "---\n"
        "\n"
        f"{body}"
    )


def extracted(path: str, text: str) -> ExtractedDocument:
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="main",
        root_path=FIXTURES,
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def normalized(text: str) -> NormalizedDocument:
    return DocumentNormalizer().normalize(extracted(FACTS, text))


def test_v1_attachment_selects_the_session_facts_chunker_without_a_warning() -> None:
    selection = chunker_selection(extracted(FACTS, facts_text()))

    assert isinstance(selection.chunker, SessionFactsChunker)
    assert selection.warning is None
    assert SESSION_FACTS_VERSION in CHUNKER_VERSIONS
    assert SESSION_FACTS_VERSION in INDEX_CODE_PARTS


def test_each_fact_line_is_one_derived_chunk_keyed_to_the_original_exchange() -> None:
    item = normalized(facts_text())

    assert item.warnings == ()
    assert [chunk.chunker_version for chunk in item.chunks] == [SESSION_FACTS_VERSION] * 2
    assert [chunk.parent_key for chunk in item.chunks] == [f"{SESSION_ID}:u-001"] * 2
    assert [chunk.text for chunk in item.chunks] == [
        "The user fixed the failing test in src/app.py.",
        "사용자는 데이터베이스 비밀번호를 .env에 둔다.",
    ]
    assert [(chunk.started_at, chunk.ended_at) for chunk in item.chunks] == [
        ("2026-11-01T00:00:00Z", "2026-11-01T23:59:59Z"),
        ("2026-10-30T00:00:00Z", "2026-10-30T23:59:59Z"),
    ]
    lines = facts_text().split("\n")
    for chunk in item.chunks:
        line = int(dict(chunk.source_locators[0].coordinates)["line"])
        assert chunk.text in lines[line - 1]
    assert len({chunk.chunk_id for chunk in item.chunks}) == 2
    expected_input = "Session: 2026-11-01\n\nThe user fixed the failing test in src/app.py."
    assert embedding_input_for(item.chunks[0]) == expected_input


def test_attachment_is_not_a_session_file() -> None:
    document = extracted(FACTS, facts_text())

    assert session_group_key(document.frontmatter.data) is None
    assert exchange_ranges(document) == {}
    item = normalized(facts_text())
    result, warnings = reprocess_session_groups((item,), {})
    assert result == (item,)
    assert warnings == ()


def test_malformed_lines_are_skipped_with_one_warning() -> None:
    body = (
        "- 2026-11-01 Good fact. (exchange u-001)\n"
        "- 2026-13-40 Bad date. (exchange u-001)\n"
        "- 2026-11-01 No exchange marker.\n"
        "free text\n"
        "\n"
        "- 2026-11-02 Second good fact. (exchange u-002)\n"
    )
    item = normalized(facts_text(body=body))

    assert [chunk.text for chunk in item.chunks] == ["Good fact.", "Second good fact."]
    assert [chunk.parent_key for chunk in item.chunks] == [f"{SESSION_ID}:u-001", f"{SESSION_ID}:u-002"]
    assert len(item.warnings) == 1
    assert item.warnings[0].startswith(f"session_facts_line_invalid: {FACTS}: 3 lines")


def test_unknown_facts_version_is_not_indexed_with_one_warning() -> None:
    item = normalized(facts_text(schema="vault-session-facts/v2"))

    assert item.chunks == ()
    assert item.warnings == (f"unknown_session_facts_schema: {FACTS} has schema vault-session-facts/v2; not indexed",)


def _index(tmp_path: Path, root: Path, name: str) -> tuple[SQLiteMetadataStore, tuple[str, ...]]:
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=root)], active_vault_id="main"
    )
    store = SQLiteMetadataStore(tmp_path / name / "metadata.sqlite3", initialize=True)
    plan = MetadataIndexer(catalog=catalog, metadata_store=store).apply(scope=catalog.default_scope())
    return store, plan.warnings


def _vault(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    target = root / PART
    target.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES / PART, target)
    return root


def test_part_windows_are_byte_identical_when_an_attachment_sits_next_to_the_part(tmp_path: Path) -> None:
    alone = _vault(tmp_path, "alone")
    attached = _vault(tmp_path, "attached")
    (attached / FACTS).write_text(facts_text(), encoding="utf-8")

    alone_store, _ = _index(tmp_path, alone, "alone-index")
    attached_store, warnings = _index(tmp_path, attached, "attached-index")

    def windows(store: SQLiteMetadataStore) -> list[tuple[object, ...]]:
        scope = VaultCatalog.from_entries(
            entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=tmp_path)], active_vault_id="main"
        ).default_scope()
        return sorted(
            (chunk.chunk_id, chunk.text, chunk.source_locators, embedding_input_for(chunk), chunk.parent_key)
            for chunk in store.list_chunks(scope)
            if chunk.path == PART
        )

    assert windows(alone_store)
    assert windows(attached_store) == windows(alone_store)
    assert not any(FACTS in warning for warning in warnings)

    with attached_store.connect_for_tests() as connection:
        groups = dict(connection.execute("SELECT path, session_group_key FROM documents").fetchall())
        facts = connection.execute(
            "SELECT parent_key, chunker_version, started_at FROM chunks WHERE path = ? ORDER BY document_order",
            (FACTS,),
        ).fetchall()
    assert groups[PART] == f"claude-code:{SESSION_ID}"
    assert groups[FACTS] is None
    assert [tuple(row) for row in facts] == [
        (f"{SESSION_ID}:u-001", SESSION_FACTS_VERSION, "2026-11-01T00:00:00Z"),
        (f"{SESSION_ID}:u-001", SESSION_FACTS_VERSION, "2026-10-30T00:00:00Z"),
    ]
    parent_keys = {window[4] for window in windows(attached_store)}
    assert {row[0] for row in facts} <= parent_keys


# Search: fact chunks are keys that lead to the original exchange (spec 2026-11-16 D21, I3, I6, F12, A18).

FACT_ONLY_QUERY = "데이터베이스 비밀번호"
FACT_TEXTS = ("The user fixed the failing test in src/app.py.", "사용자는 데이터베이스 비밀번호를 .env에 둔다.")


class _ReadySearch:
    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return ready_report(vector_ok=False)


def _service(tmp_path: Path, *, part: bool = True, facts: bool = True) -> tuple[RetrievalService, QueryScope]:
    root = tmp_path / "root"
    root.mkdir()
    items = []
    if part:
        part_text = (FIXTURES / PART).read_text(encoding="utf-8")
        items.append(DocumentNormalizer().normalize(extracted(PART, part_text)))
    if facts:
        items.append(normalized(facts_text()))
    database = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database, initialize=True)
    store.apply_metadata_revision(
        index_revision="metadata-1",
        documents=[item.document for item in items],
        chunks=[chunk for item in items for chunk in item.chunks],
        tombstones=[],
    )
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="main", root_path=root)], active_vault_id="main"
    )
    service = RetrievalService(
        catalog=catalog, metadata_store=store, keyword_index=SQLiteKeywordIndex(database), readiness=_ReadySearch()
    )
    return service, catalog.default_scope()


def _search(
    tmp_path: Path, query: str, *, part: bool = True, facts: bool = True, include_fact_keys: bool = True
) -> SearchResponse:
    service, scope = _service(tmp_path, part=part, facts=facts)
    return service.search(
        query_text=query,
        requested_scope=scope,
        limit=10,
        mode="evidence",
        include_fact_keys=include_fact_keys,
        trace=True,
    )


def _shown(response: SearchResponse) -> list[tuple[object, ...]]:
    return [
        (
            result.title,
            result.summary,
            tuple((item.path, item.chunk_id, item.source_locators) for item in result.evidence),
            tuple(warning.code for warning in result.warnings),
        )
        for result in response.results
    ]


def _assert_no_fact_text(response: SearchResponse) -> None:
    for result in response.results:
        shown = [result.title, result.summary, *(item.path for item in result.evidence)]
        shown += [item.section or "" for item in result.evidence]
        for fact in FACT_TEXTS:
            assert all(fact not in text for text in shown)
        assert all(item.path != FACTS for item in result.evidence)
    for warning in response.warnings:
        assert all(fact not in warning.message for fact in FACT_TEXTS)


def test_fact_key_weight_equals_keyword_and_vector() -> None:
    # Spec 2026-11-16 D21: equal weight, the usual default (research X29). 0.5 barely helped (X26).
    assert FACT_KEY_WEIGHT == SIGNAL_WEIGHTS["keyword"] == SIGNAL_WEIGHTS["vector"] == 1.0
    assert fact_key_score(1.0) == FACT_KEY_WEIGHT


def test_a_fact_only_match_returns_the_original_exchange_first_window(tmp_path: Path) -> None:
    response = _search(tmp_path, FACT_ONLY_QUERY)

    assert len(response.results) == 1
    result = response.results[0]
    first = result.evidence[0]
    assert first.path == PART
    part_text = (FIXTURES / PART).read_text(encoding="utf-8")
    window = DocumentNormalizer().normalize(extracted(PART, part_text)).chunks
    exchange = sorted(
        (chunk for chunk in window if chunk.parent_key == f"{SESSION_ID}:u-001"), key=lambda c: c.document_order
    )
    assert first.chunk_id == exchange[0].chunk_id
    assert first.source_locators == exchange[0].parent_locators
    assert result.summary and " ".join(exchange[0].text.split()).startswith(result.summary.removesuffix("..."))
    assert result.title.startswith(PART)
    _assert_no_fact_text(response)
    assert response.stage_trace is not None
    assert [entry.path for entry in response.stage_trace.document_ranks] == [PART]


def test_fact_and_window_matches_of_one_exchange_return_it_once(tmp_path: Path) -> None:
    response = _search(tmp_path, "failing test src/app.py")

    assert [result.evidence[0].path for result in response.results] == [PART]
    _assert_no_fact_text(response)


def test_a_fact_whose_exchange_is_not_indexed_is_dropped_with_a_warning(tmp_path: Path) -> None:
    response = _search(tmp_path, FACT_ONLY_QUERY, part=False)

    assert response.results == ()
    codes = [warning.code for warning in response.warnings]
    assert "fact_source_missing" in codes
    _assert_no_fact_text(response)


def test_without_fact_keys_the_results_are_as_without_attachments(tmp_path: Path) -> None:
    (tmp_path / "alone").mkdir()
    (tmp_path / "off").mkdir()
    (tmp_path / "alone-fact").mkdir()
    (tmp_path / "off-fact").mkdir()
    (tmp_path / "on").mkdir()
    query = "failing test src/app.py"
    alone = _search(tmp_path / "alone", query, facts=False)
    off = _search(tmp_path / "off", query, include_fact_keys=False)
    on = _search(tmp_path / "on", query)
    # With fact keys on, the fact chunk is a keyword candidate too, so leaving it out is what keeps `off` equal.
    assert on.stage_trace is not None and alone.stage_trace is not None
    assert len(on.stage_trace.signal_ranks) > len(alone.stage_trace.signal_ranks)

    assert alone.results
    assert _shown(off) == _shown(alone)
    assert off.warnings == alone.warnings
    assert off.stage_trace is not None and alone.stage_trace is not None
    assert [(e.chunk_id, e.rank) for e in off.stage_trace.signal_ranks] == [
        (e.chunk_id, e.rank) for e in alone.stage_trace.signal_ranks
    ]

    assert _search(tmp_path / "alone-fact", FACT_ONLY_QUERY, facts=False).results == ()
    assert _search(tmp_path / "off-fact", FACT_ONLY_QUERY, include_fact_keys=False).results == ()


def test_without_fact_keys_a_signal_list_fills_up_past_the_facts_and_ranks_again(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)
    with service._metadata_store.connect_for_tests() as connection:  # type: ignore[attr-defined]
        rows = connection.execute(
            "SELECT document_id, chunk_id, chunker_version FROM chunks ORDER BY chunker_version DESC, chunk_id"
        ).fetchall()
    # Fact chunks first, then the part's windows: every fact takes a slot ahead of a window.
    hits = tuple(
        KeywordHit(
            vault_id="main",
            document_id=row[0],
            chunk_id=row[1],
            rank=rank,
            score=float(rank),
            backend="test",
            index_revision="metadata-1",
            matched_fields=(),
            provenance_family_id="family",
        )
        for rank, row in enumerate(rows, start=1)
    )
    facts = sum(1 for row in rows if row[2] == SESSION_FACTS_VERSION)
    windows = len(rows) - facts
    assert facts == 2 and windows >= 1
    asked: list[int] = []

    def fetch(limit: int) -> tuple[KeywordHit, ...]:
        asked.append(limit)
        return hits[:limit]

    kept = service._hits(fetch, limit=1, include_fact_keys=False)

    assert [(hit.chunk_id, hit.rank) for hit in kept] == [(rows[facts][1], 1)]
    assert asked == [1, 2, 3]
    assert service._hits(fetch, limit=1, include_fact_keys=True) == hits[:1]
