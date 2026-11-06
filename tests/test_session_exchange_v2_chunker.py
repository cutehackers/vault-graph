"""`session-exchange-v2` chunker on vault-session/v2 files (spec 2026-11-05 §4.2.6-3·4·5·7·10·11, §6, A-4 v2)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.fakes.search_readiness import ready_report
from vault_graph.indexing.ingestion.chunker_selection import CHUNKER_VERSIONS, embedding_input_for, select_chunker
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, NormalizedDocument
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import (
    CONTINUED_QUESTION,
    SESSION_EXCHANGE_V2_VERSION,
    SESSION_WINDOW_MAX_TOKENS,
    SessionExchangeV2Chunker,
    WindowLine,
    count_over_model_limit,
    drop_duplicate_exchanges,
    model_limit_warning,
    pack_exchange_windows,
)
from vault_graph.indexing.metadata_indexer import INDEX_CODE_PARTS
from vault_graph.operation.readiness.search_readiness import SearchReadinessReport
from vault_graph.operation.scope.vault_catalog import QueryScope, VaultCatalog, VaultCatalogEntry
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FIXTURES = Path(__file__).parent / "fixtures" / "session_v2"
SESSIONS = "raw/sessions/claude-code"
WITH_ORIGIN = f"{SESSIONS}/2026-11-01-11111111-1111-4111-8111-111111111111-part1.md"
SUBAGENT = f"{SESSIONS}/2026-11-03-33333333-3333-4333-8333-333333333333-part1.md"
LONG_PART1 = f"{SESSIONS}/2026-11-04-44444444-4444-4444-8444-444444444444-part1.md"
LONG_PART3 = f"{SESSIONS}/2026-11-04-44444444-4444-4444-8444-444444444444-part3.md"
ALL_FIXTURES = (WITH_ORIGIN, SUBAGENT, LONG_PART1, LONG_PART3)


def _extracted(path: str, text: str | None = None, *, vault_id: str = "project") -> ExtractedDocument:
    raw = (FIXTURES / path).read_bytes() if text is None else text.encode("utf-8")
    source = SourceDocument(
        vault_id=vault_id,
        root_path=FIXTURES,
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def _normalized(path: str, text: str | None = None) -> NormalizedDocument:
    return DocumentNormalizer().normalize(_extracted(path, text))


def _file_lines(path: str) -> list[str]:
    return (FIXTURES / path).read_text(encoding="utf-8").split("\n")


def _line_range(locator_coordinates: tuple[tuple[str, str], ...]) -> range:
    values = dict(locator_coordinates)
    first = int(values["line"])
    return range(first, int(values.get("line_end", first)) + 1)


def test_v2_schema_selects_the_session_exchange_v2_chunker() -> None:
    chunker = select_chunker(_extracted(WITH_ORIGIN))

    assert isinstance(chunker, SessionExchangeV2Chunker)
    assert chunker.version == SESSION_EXCHANGE_V2_VERSION == "session-exchange-v2"
    assert SESSION_EXCHANGE_V2_VERSION in CHUNKER_VERSIONS
    # The incremental precheck hashes INDEX_CODE_PARTS, so a new chunker version re-plans every file.
    assert SESSION_EXCHANGE_V2_VERSION in INDEX_CODE_PARTS


@pytest.mark.parametrize("path", ALL_FIXTURES)
def test_windows_hide_meta_lines_stay_within_160_tokens_and_do_not_overlap(path: str) -> None:
    normalized = _normalized(path)
    lines = _file_lines(path)
    meta_lines = [line for line in lines if line.startswith("<!-- vg:exchange ")]

    assert normalized.chunks
    assert meta_lines
    assert all(chunk.chunker_version == SESSION_EXCHANGE_V2_VERSION for chunk in normalized.chunks)
    for chunk in normalized.chunks:
        assert "<!-- vg:" not in chunk.text
        assert not any(meta in chunk.text for meta in meta_lines)
        assert chunk.token_count == len(chunk.text.split()) <= SESSION_WINDOW_MAX_TOKENS
        assert len(chunk.source_locators) == 1
        assert chunk.source_locators[0].scheme == "markdown"
        assert chunk.source_locators[0].offset_unit == "char"

    spans = sorted(
        (locator.start_offset or 0, locator.end_offset or 0)
        for chunk in normalized.chunks
        for locator in chunk.source_locators
    )
    for (_, end), (start, _) in zip(spans, spans[1:], strict=False):
        assert end <= start
    # Two windows share a line only when that one line is longer than the window.
    seen: dict[int, str] = {}
    for chunk in normalized.chunks:
        for number in _line_range(chunk.source_locators[0].coordinates):
            if number in seen and seen[number] != chunk.chunk_id:
                assert len(lines[number - 1].split()) > SESSION_WINDOW_MAX_TOKENS
            seen[number] = chunk.chunk_id
    assert len({chunk.chunk_id for chunk in normalized.chunks}) == len(normalized.chunks)
    assert normalized.warnings == ()


def test_short_exchange_is_one_window_with_turn_text_and_action_lines() -> None:
    normalized = _normalized(WITH_ORIGIN)

    assert len(normalized.chunks) == 1
    chunk = normalized.chunks[0]
    assert chunk.text == (
        "Fix the failing test in src/app.py. The db password=[REDACTED:secret] is in .env.\n\n"
        "I will edit the file.\n\n"
        "- Edit\n"
        "- Bash → 실패: "
        "Auth failed: Bearer [REDACTED:bearer] rejected\n"
        "- WebFetch\n\n"
        "Fixed. The test passes now.\n\n"
        "<task-notification><task-id>t1</task-id><status>completed</status></task-notification>\n\n"
        "<system-reminder>context</system-reminder>"
    )
    assert chunk.section_path == (
        "Session 2026-11-01 part1",
        "Q: Fix the failing test in src/app.py. The db password=[REDACTED:secret] is in .env",
    )
    assert chunk.parent_key == "11111111-1111-4111-8111-111111111111:u-001"
    assert [dict(locator.coordinates) for locator in chunk.parent_locators] == [{"line": "24", "line_end": "49"}]
    assert dict(chunk.source_locators[0].coordinates) == {"line": "29", "line_end": "49"}
    assert chunk.keyword_metadata == (
        "files: /work/demo-app/src/app.py "
        "commands: ANTHROPIC_API_KEY=[REDACTED:anthropic-key] pytest -q tests/test_app.py "
        "tools: Bash:1 Edit:1 WebFetch:1 errors: 1 outcome: answered"
    )


def test_embedding_input_has_session_and_question_lines_and_no_exchange_meta() -> None:
    chunk = _normalized(WITH_ORIGIN).chunks[0]

    embedding_input = embedding_input_for(chunk)

    assert embedding_input == (
        "Session: 2026-11-01 part1\n"
        "Question: Fix the failing test in src/app.py. The db password=[REDACTED:secret] is in .env\n\n" + chunk.text
    )
    assert "vg:exchange" not in embedding_input
    assert "outcome:" not in embedding_input
    assert "errors:" not in embedding_input


def test_subagent_exchange_names_the_agent_in_the_section_path() -> None:
    chunks = _normalized(SUBAGENT).chunks

    assert [chunk.parent_key for chunk in chunks] == [
        "33333333-3333-4333-8333-333333333333:u-201",
        "33333333-3333-4333-8333-333333333333:s-301",
    ]
    main, subagent = chunks
    assert main.section_path == ("Session 2026-11-03 part1", "Q: Review src/app.py with a reviewer subagent.")
    assert subagent.section_path == ("Session 2026-11-03 part1 subagent a7f3", "Q: Review src/app.py for bugs.")
    assert subagent.text == (
        "Review src/app.py for bugs.\n\n- Read\n\nOne issue: line 3 sets password=[REDACTED:secret] in code."
    )
    assert subagent.keyword_metadata == (
        "files: /work/demo-app/src/app.py commands: tools: Read:1 errors: 0 outcome: answered"
    )


def test_long_turn_is_split_at_word_boundaries_and_a_new_exchange_opens_a_new_window() -> None:
    chunks = _normalized(LONG_PART1).chunks
    by_exchange: dict[str | None, list[str]] = {}
    for chunk in chunks:
        by_exchange.setdefault(chunk.parent_key, []).append(chunk.text)

    long_session = "44444444-4444-4444-8444-444444444444"
    first = by_exchange[f"{long_session}:u-401"]
    assert len(first) >= 2
    words = " ".join(first).split()
    expected_words = [f"word{index:03d}" for index in range(1, 201)]
    assert [word for word in words if re.fullmatch(r"word\d{3}", word)] == expected_words
    assert words[0] == "Why"
    assert words[-1] == "quotes."
    assert by_exchange[f"{long_session}:u-410"] == [
        "Where is the tokenizer module?\n\nLet me list the source folder.\n\n- Bash\n\nIt is src/tokenizer.py."
    ]
    # Escaped heading and meta-looking lines from turn text stay as text.
    assert any("\\# not a heading" in text for text in first)
    assert any("&lt;!-- vg:exchange id=fake --> stays text" in text for text in first)


def test_continued_exchange_question_says_it_continues_from_an_earlier_part() -> None:
    chunks = _normalized(LONG_PART3).chunks

    continued = [chunk for chunk in chunks if chunk.parent_key and chunk.parent_key.endswith(":u-410")]
    assert [chunk.section_path for chunk in continued] == [("Session 2026-11-04 part3", "Q: (이전 파트에서 이어짐)")]
    assert continued[0].text == "- Bash\n\nIt is src/tokenizer.py."


def test_broken_meta_line_chunks_that_exchange_by_heading_with_one_warning() -> None:
    text = (FIXTURES / LONG_PART1).read_text(encoding="utf-8")
    broken = re.sub(r"<!-- vg:exchange id=u-410 [^\n]*", "<!-- vg:exchange scope=main tools=Bash:1", text)

    normalized = _normalized(LONG_PART1, broken)

    warnings = [warning for warning in normalized.warnings if warning.startswith("session_exchange_meta_invalid: ")]
    assert len(warnings) == 1
    assert "\n" not in warnings[0]
    assert LONG_PART1 in warnings[0]
    heading = "Where is the tokenizer module? 2026-11-04T09:01:00.000Z · u-410"
    fallback = [chunk for chunk in normalized.chunks if chunk.parent_key == f"{LONG_PART1}:{heading}:0"]
    assert [chunk.text for chunk in fallback] == [
        "Where is the tokenizer module?\n\nLet me list the source folder.\n\n- Bash\n\nIt is src/tokenizer.py."
    ]
    assert fallback[0].keyword_metadata is None
    assert all("<!-- vg:" not in chunk.text for chunk in normalized.chunks)
    # The other exchanges keep their exchange ids.
    assert {chunk.parent_key for chunk in normalized.chunks} == {
        "44444444-4444-4444-8444-444444444444:u-401",
        f"{LONG_PART1}:{heading}:0",
        "44444444-4444-4444-8444-444444444444:u-420",
    }


def test_missing_meta_line_also_falls_back_with_one_warning() -> None:
    text = (FIXTURES / WITH_ORIGIN).read_text(encoding="utf-8")
    without = re.sub(r"<!-- vg:exchange [^\n]*\n", "", text)

    normalized = _normalized(WITH_ORIGIN, without)

    assert len([warning for warning in normalized.warnings if "session_exchange_meta_invalid" in warning]) == 1
    assert [chunk.parent_key for chunk in normalized.chunks] == [
        f"{WITH_ORIGIN}:Fix the failing test in src/app.py. The db password=[REDACTE 2026-11-01T10:00:00.000Z · u-001:0"
    ]


def test_same_exchange_id_twice_in_one_file_keeps_the_first_with_one_warning() -> None:
    text = (FIXTURES / WITH_ORIGIN).read_text(encoding="utf-8")
    body = text.split("\n---\n", 1)[1]
    doubled = text + body

    normalized = _normalized(WITH_ORIGIN, doubled)

    assert len(normalized.chunks) == 1
    duplicate = [warning for warning in normalized.warnings if warning.startswith("session_exchange_duplicate: ")]
    assert len(duplicate) == 1
    assert "u-001" in duplicate[0]


def test_same_exchange_id_in_two_files_keeps_the_path_sorted_first_with_one_warning_each() -> None:
    part1 = _normalized(LONG_PART1)
    part3 = _normalized(LONG_PART3)

    kept, warnings = drop_duplicate_exchanges((part3, part1))

    assert [document.document.path for document in kept] == [LONG_PART1, LONG_PART3]
    assert kept[0] == part1
    assert kept[1].chunks == ()
    assert len(warnings) == 2
    assert all("\n" not in warning and warning.startswith("session_exchange_duplicate: ") for warning in warnings)
    assert any("u-410" in warning and LONG_PART3 in warning and LONG_PART1 in warning for warning in warnings)


def test_same_whole_exchange_in_part2_and_part10_keeps_part2_by_part_number() -> None:
    """A plain path sort puts part10 before part2; the rule orders by the frontmatter part number."""
    text = (FIXTURES / LONG_PART1).read_text(encoding="utf-8")
    part2_path = LONG_PART1.replace("-part1.md", "-part2.md")
    part10_path = LONG_PART1.replace("-part1.md", "-part10.md")
    part2 = _normalized(part2_path, text.replace("\npart: 1\n", "\npart: 2\n", 1))
    part10 = _normalized(part10_path, text.replace("\npart: 1\n", "\npart: 10\n", 1))
    assert part10_path < part2_path

    kept, warnings = drop_duplicate_exchanges((part10, part2))

    assert [document.document.path for document in kept] == [part2_path, part10_path]
    assert kept[0] == part2
    assert kept[1].chunks == ()
    assert warnings and all(part2_path in warning for warning in warnings)


def test_a_whole_copy_in_a_later_part_wins_over_a_continued_copy() -> None:
    """After `vg session export --recapture` the whole exchange sits in a later part (A-37)."""
    part1 = _normalized(LONG_PART1)
    part3 = _normalized(LONG_PART3)
    continued = {chunk.parent_key for chunk in part3.chunks if chunk.section_path[1:2] == (f"Q: {CONTINUED_QUESTION}",)}
    assert continued, "fixture part3 must start inside an exchange"
    whole_later = _normalized(
        LONG_PART3.replace("-part3.md", "-part5.md"),
        (FIXTURES / LONG_PART1).read_text(encoding="utf-8").replace("\npart: 1\n", "\npart: 5\n", 1),
    )

    kept, _ = drop_duplicate_exchanges((part3, whole_later))

    by_path = {document.document.path: document for document in kept}
    owners_of_continued = {
        path for path, document in by_path.items() for chunk in document.chunks if chunk.parent_key in continued
    }
    assert continued <= {chunk.parent_key for chunk in whole_later.chunks}
    assert owners_of_continued == {whole_later.document.path}
    assert part1.chunks


def test_files_without_shared_exchanges_pass_through_unchanged() -> None:
    documents = (_normalized(WITH_ORIGIN), _normalized(SUBAGENT))

    kept, warnings = drop_duplicate_exchanges(documents)

    assert kept == documents
    assert warnings == ()


def test_pack_exchange_windows_splits_one_long_line_with_disjoint_char_ranges() -> None:
    long_line = " ".join(f"w{index}" for index in range(400))
    lines = (
        WindowLine(text="short opening line", line=10, start_offset=100, end_offset=118, group=0),
        WindowLine(text=long_line, line=12, start_offset=120, end_offset=120 + len(long_line), group=1),
    )

    windows = pack_exchange_windows(lines)

    assert [window.token_count for window in windows] == [160, 160, 83]
    assert " ".join(window.text for window in windows).split() == ["short", "opening", "line", *long_line.split()]
    ranges = [(window.start_offset, window.end_offset) for window in windows]
    assert ranges[0][0] == 100
    assert ranges[-1][1] == 120 + len(long_line)
    for (_, end), (start, _) in zip(ranges, ranges[1:], strict=False):
        assert end < start


def test_model_token_limit_warning_counts_windows_over_512() -> None:
    inputs = ("a " * 10, "b " * 600, "c " * 513, "d " * 512)

    count = count_over_model_limit(inputs, lambda text: len(text.split()))

    assert count == 2
    warning = model_limit_warning(count)
    assert warning is not None and "\n" not in warning and "2" in warning
    assert model_limit_warning(0) is None


class _ReadySearch:
    def check(self, *, actual_scopes: tuple[QueryScope, ...]) -> SearchReadinessReport:
        return ready_report(vector_ok=False)


@pytest.mark.parametrize(
    ("path", "edited_file", "exchange_id"),
    [
        (LONG_PART1, "/work/demo-app/src/parser.py", "u-401"),
        (WITH_ORIGIN, "/work/demo-app/src/app.py", "u-001"),
    ],
)
def test_edited_file_path_finds_the_exchange_but_is_not_in_window_text_or_embedding_input(
    tmp_path: Path, path: str, edited_file: str, exchange_id: str
) -> None:
    # Spec §4.2.6-8, 결정12, A-6: action targets go only to the keyword frontmatter column.
    root = tmp_path / "default"
    root.mkdir()
    normalized = DocumentNormalizer().normalize(_extracted(path, vault_id="default"))
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(
        index_revision="metadata-1", documents=[normalized.document], chunks=list(normalized.chunks), tombstones=[]
    )
    catalog = VaultCatalog.from_entries(
        entries=[VaultCatalogEntry.from_root(vault_id="default", root_path=root)], active_vault_id="default"
    )
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store,
        keyword_index=SQLiteKeywordIndex(tmp_path / "metadata.sqlite3"),
        readiness=_ReadySearch(),
    )

    response = service.search(query_text=edited_file, requested_scope=catalog.default_scope(), limit=10, mode="all")

    exchange_chunks = {
        chunk.chunk_id
        for chunk in normalized.chunks
        if chunk.parent_key and chunk.parent_key.endswith(f":{exchange_id}")
    }
    assert exchange_chunks
    assert any(result.evidence[0].chunk_id in exchange_chunks for result in response.results[:5])
    for chunk in normalized.chunks:
        assert edited_file not in chunk.text
        assert edited_file not in embedding_input_for(chunk)
