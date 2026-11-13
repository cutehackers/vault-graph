"""Spec 2026-11-11 결정17, A-16: same-Vault session exchange copies fold into one result, and pages folded by
`supersedes`/`superseded_by` stay on the kept result as evidence."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from tests.benchmarks import eval_scoring
from tests.benchmarks.measure_session_recall import ExchangeLocation
from tests.fakes.search_readiness import ready_report
from tests.test_document_result_ranking import StaticReadiness, _catalog, _chunk, _document, _paths
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_models import SourceLocator
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.retrieval.search.evidence_result_assembly import (
    DUPLICATE_CONTENT_WARNING,
    REPLACED_PAGES_WARNING,
    ExchangeSignature,
    _fold_exchange_copies,
    _ParentGroup,
)
from vault_graph.retrieval.search.retrieval_service import RetrievalService
from vault_graph.retrieval.search.search_response import SearchMode, SearchResponse
from vault_graph.storage.local.sqlite_keyword_index import SQLiteKeywordIndex
from vault_graph.storage.local.sqlite_metadata_store import SQLiteMetadataStore

FIRST_PATH = "raw/sessions/2026-11-05-session-a.md"
SECOND_PATH = "raw/sessions/2026-11-06-session-b.md"
QUESTION = "Why does the tombstone sweeper skip archived folders?"
ANSWER = "The tombstone sweeper skips archived folders because their rows are already frozen."
OTHER_ANSWER = "The tombstone sweeper has a allowlist; archived folders are simply not on it yet."
QUERY = "tombstone sweeper archived folders"


def line_locator(first: int, last: int) -> SourceLocator:
    """A line range in the markdown reader's locator shape, as the session chunkers write it."""
    return SourceLocator(
        scheme="markdown",
        coordinates=(("line", str(first)), ("line_end", str(last))),
        start_offset=first,
        end_offset=last,
        offset_unit="char",
    )


def _session(path: str, session_id: str, vault_id: str = "default") -> DocumentSnapshot:
    return replace(
        make_document(vault_id, path, f"hash:{path}"),
        kind="raw",
        frontmatter={"schema": "vault-session/v2", "session_id": session_id},
        source_role="raw_evidence",
    )


def _exchange(
    document: DocumentSnapshot,
    exchange_id: str,
    *,
    first_line: int,
    texts: tuple[str, ...],
    first_order: int = 0,
    metadata: str = "files: src/sweeper.py commands: pytest -q tools: Bash errors: 0 outcome: answered",
) -> list[ChunkSnapshot]:
    """Windows of one exchange, two lines each, as the v2 chunker emits them."""
    session_id = str(document.frontmatter["session_id"])
    parent_locator = line_locator(first_line, first_line + 2 * len(texts))
    return [
        replace(
            make_chunk(
                document.vault_id,
                document.document_id,
                document.path,
                chunk_id=f"{session_id}:{exchange_id}:w{number}",
                text=text,
            ),
            source_role="raw_evidence",
            provenance_family_id=document.provenance_family_id,
            section=f"Q: {QUESTION}",
            anchor=None,
            source_locators=(line_locator(first_line + 1 + 2 * number, first_line + 2 + 2 * number),),
            document_order=first_order + number,
            parent_key=f"{session_id}:{exchange_id}",
            parent_locators=(parent_locator,),
            keyword_metadata=metadata,
        )
        for number, text in enumerate(texts)
    ]


class WholeDocumentStore:
    """The same store without ``list_parent_chunk_hashes``, so the assembly reads the whole document."""

    def __init__(self, store: SQLiteMetadataStore) -> None:
        self._store = store

    def __getattr__(self, name: str) -> Any:
        if name == "list_parent_chunk_hashes":
            raise AttributeError(name)
        return getattr(self._store, name)


def _search(
    tmp_path: Path,
    documents: list[DocumentSnapshot],
    chunks: list[ChunkSnapshot],
    query_text: str,
    *,
    mode: SearchMode,
    narrow_reads: bool = True,
) -> SearchResponse:
    database = tmp_path / "metadata.sqlite3"
    store = SQLiteMetadataStore(database, initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    catalog = _catalog(tmp_path)
    service = RetrievalService(
        catalog=catalog,
        metadata_store=store if narrow_reads else WholeDocumentStore(store),
        keyword_index=SQLiteKeywordIndex(database),
        readiness=StaticReadiness(ready_report(vector_ok=False)),
    )
    return service.search(
        query_text=query_text, requested_scope=catalog.scope_for_vault_ids(("default",)), limit=10, mode=mode
    )


def _copied_sessions() -> tuple[list[DocumentSnapshot], list[ChunkSnapshot]]:
    """Session b continues session a: it holds exchange ex-1 again at other lines, then a new exchange."""
    first = _session(FIRST_PATH, "session-a")
    second = _session(SECOND_PATH, "session-b")
    texts = (f"### user\n{QUESTION}", f"### assistant\n{ANSWER}")
    chunks = [
        *_exchange(first, "ex-1", first_line=5, texts=texts),
        *_exchange(second, "ex-1", first_line=40, texts=texts),
        # Same question and same first window, another answer: a different exchange.
        *_exchange(second, "ex-2", first_line=60, texts=(texts[0], f"### assistant\n{OTHER_ANSWER}"), first_order=2),
    ]
    return [first, second], chunks


# Session exchange copies inside one Vault.


def test_same_exchange_in_two_session_files_returns_once_and_lists_both_files(tmp_path: Path) -> None:
    documents, chunks = _copied_sessions()

    response = _search(tmp_path, documents, chunks, QUERY, mode="evidence")

    assert [result.evidence[0].chunk_id.rsplit(":", 1)[0] for result in response.results] == [
        "session-a:ex-1",
        "session-b:ex-2",
    ]
    assert [result.rank for result in response.results] == [1, 2]
    folded = response.results[0]
    assert [(item.path, item.source_locators) for item in folded.evidence] == [
        (FIRST_PATH, (line_locator(5, 9),)),
        (SECOND_PATH, (line_locator(40, 44),)),
    ]
    duplicate = next(warning for warning in folded.warnings if warning.code == DUPLICATE_CONTENT_WARNING)
    assert duplicate.severity == "info"
    assert f"default:{SECOND_PATH}" in duplicate.message
    assert FIRST_PATH in duplicate.message
    # The other exchange of session b keeps only its own evidence.
    assert [item.path for item in response.results[1].evidence] == [SECOND_PATH]
    assert all(warning.code != DUPLICATE_CONTENT_WARNING for warning in response.results[1].warnings)


def test_exchanges_that_differ_outside_the_matched_window_stay_separate(tmp_path: Path) -> None:
    first = _session(FIRST_PATH, "session-a")
    second = _session(SECOND_PATH, "session-b")
    question = f"### user\n{QUESTION}"
    chunks = [
        *_exchange(first, "ex-1", first_line=5, texts=(question, "### assistant\nIt reads the frozen flag.")),
        *_exchange(second, "ex-1", first_line=5, texts=(question, "### assistant\nIt checks an allowlist.")),
    ]

    response = _search(tmp_path, [first, second], chunks, QUERY, mode="evidence")

    assert _paths(response) == [f"default:{FIRST_PATH}", f"default:{SECOND_PATH}"]
    assert all(len(result.evidence) == 1 for result in response.results)


def test_exchanges_with_the_same_text_and_other_keyword_metadata_stay_separate(tmp_path: Path) -> None:
    first = _session(FIRST_PATH, "session-a")
    second = _session(SECOND_PATH, "session-b")
    texts = (f"### user\n{QUESTION}", "### assistant\n- Bash → ok")
    chunks = [
        *_exchange(first, "ex-1", first_line=5, texts=texts),
        *_exchange(second, "ex-1", first_line=5, texts=texts, metadata="files: src/other.py outcome: answered"),
    ]

    response = _search(tmp_path, [first, second], chunks, QUERY, mode="evidence")

    assert len(response.results) == 2


def test_forked_session_copy_of_the_first_part_of_an_exchange_folds_into_one_result(tmp_path: Path) -> None:
    """Session b was forked from session a inside the exchange: it holds the first two windows, cut in the
    third. Session a holds the whole exchange. Both are the same conversation, so one result lists both."""
    first = _session(FIRST_PATH, "session-a")
    second = _session(SECOND_PATH, "session-b")
    question = f"### user\n{QUESTION}"
    answer = f"### assistant\n{ANSWER}"
    chunks = [
        *_exchange(
            first,
            "ex-1",
            first_line=5,
            texts=(question, answer, "### assistant\nThen it wrote the fix.", "### assistant\nAnd ran the tests."),
        ),
        *_exchange(second, "ex-1", first_line=5, texts=(question, answer, "### assistant\nThen it")),
    ]

    response = _search(tmp_path, [first, second], chunks, QUERY, mode="evidence")

    assert len(response.results) == 1
    assert sorted(item.path for item in response.results[0].evidence) == sorted([FIRST_PATH, SECOND_PATH])


def _folded_shape(response: SearchResponse) -> list[tuple[object, ...]]:
    """What folding decides for each result: its rank, its evidence and its warnings."""
    return [
        (
            result.rank,
            tuple((item.chunk_id, item.path, item.source_locators) for item in result.evidence),
            tuple((warning.code, warning.message) for warning in result.warnings),
        )
        for result in response.results
    ]


def test_copy_folding_is_the_same_without_the_narrow_read_and_on_repeat(tmp_path: Path) -> None:
    documents, chunks = _copied_sessions()

    # One store per search. The comparison leaves out signal scores: BM25 statistics of equal keyword
    # indexes differ on some SQLite builds, and folding does not depend on the score.
    folders = [tmp_path / name for name in ("narrow", "again", "whole")]
    for folder in folders:
        folder.mkdir()
    narrow = _search(folders[0], documents, chunks, QUERY, mode="evidence")
    again = _search(folders[1], documents, chunks, QUERY, mode="evidence")
    whole = _search(folders[2], documents, chunks, QUERY, mode="evidence", narrow_reads=False)

    assert _folded_shape(narrow) == _folded_shape(again) == _folded_shape(whole)


def test_parent_chunk_hashes_are_the_exchange_windows_in_document_order(tmp_path: Path) -> None:
    documents, chunks = _copied_sessions()
    store = SQLiteMetadataStore(tmp_path / "metadata.sqlite3", initialize=True)
    store.apply_metadata_revision(index_revision="metadata-1", documents=documents, chunks=chunks, tombstones=[])
    second = documents[1].document_id

    hashes = store.list_parent_chunk_hashes(vault_id="default", document_id=second, parent_key="session-b:ex-2")

    assert hashes == (f"chunk:### user\n{QUESTION}", f"chunk:### assistant\n{OTHER_ANSWER}")
    assert store.list_parent_chunk_hashes(vault_id="default", document_id=second, parent_key="missing") == ()


def _unit(path: str, parent_key: str | None, *, vault_id: str = "default", section: str = "Q: same") -> _ParentGroup:
    chunk = replace(
        make_chunk(vault_id, f"{vault_id}:{path}", path, chunk_id=f"{path}:{parent_key}"),
        section=section,
        parent_key=parent_key,
    )
    candidate = SimpleNamespace(vault_id=vault_id, document_id=chunk.document_id, chunk_id=chunk.chunk_id)
    return _ParentGroup(item=(candidate, SimpleNamespace(vault_id=vault_id, path=path), ""), chunk=chunk)  # type: ignore[arg-type]


def test_folded_copies_take_the_position_of_the_highest_ranked_copy() -> None:
    content: dict[str, ExchangeSignature] = {
        "a:1": (None, ("x", "y")),
        "b:1": (None, ("x", "y")),
        "a:2": (None, ("z",)),
    }
    asked: list[str] = []

    def signature(group: _ParentGroup) -> ExchangeSignature | None:
        asked.append(str(group.chunk.parent_key))
        return content.get(str(group.chunk.parent_key))

    top = _unit("raw/sessions/a.md", "a:1")
    between = _unit("raw/sessions/a.md", "a:2")
    page = _unit("wiki/page.md", None)
    copy = _unit("raw/sessions/b.md", "b:1")
    unreadable = _unit("raw/sessions/c.md", "c:1")
    other_question = _unit("raw/sessions/d.md", "d:1", section="Q: other")
    other_vault = _unit("raw/sessions/a.md", "b:1", vault_id="second")

    folded = _fold_exchange_copies(
        (top, between, page, copy, unreadable, other_question, other_vault), signature=signature
    )

    assert folded == (replace(top, copies=(copy,)), between, page, unreadable, other_question, other_vault)
    # Only units that share a Vault and a question with another unit are read.
    assert asked == ["a:1", "a:2", "b:1", "c:1"]


# Pages folded by `supersedes` / `superseded_by`.


def _replacement_chain() -> tuple[list[DocumentSnapshot], list[ChunkSnapshot]]:
    family = "family:decision"
    new = _document("default", "wiki/decisions/new.md", frontmatter={"supersedes": "[[decisions/old]]"}, family=family)
    old = _document(
        "default", "wiki/decisions/old.md", frontmatter={"superseded_by": "wiki/decisions/new.md"}, family=family
    )
    other = _document("default", "wiki/concepts/other.md")
    chunks = [
        _chunk(new, 0, "Retention policy keeps tombstones for ninety days. Retention policy."),
        _chunk(old, 0, "Retention policy kept tombstones for thirty days before the change."),
        _chunk(other, 0, "Retention policy background reading for operators."),
    ]
    return [new, old, other], chunks


def test_replaced_page_is_attached_to_the_kept_result_as_evidence(tmp_path: Path) -> None:
    documents, chunks = _replacement_chain()

    response = _search(tmp_path, documents, chunks, "retention policy", mode="knowledge")

    assert sorted(_paths(response)) == ["default:wiki/concepts/other.md", "default:wiki/decisions/new.md"]
    assert [result.rank for result in response.results] == [1, 2]
    kept = next(result for result in response.results if result.evidence[0].path == "wiki/decisions/new.md")
    assert [(item.path, item.chunk_id) for item in kept.evidence] == [
        ("wiki/decisions/new.md", "wiki/decisions/new.md#0"),
        ("wiki/decisions/old.md", "wiki/decisions/old.md#0"),
    ]
    attached = next(warning for warning in kept.warnings if warning.code == REPLACED_PAGES_WARNING)
    assert attached.severity == "info"
    assert "wiki/decisions/old.md" in attached.message
    other = next(result for result in response.results if result.evidence[0].path == "wiki/concepts/other.md")
    assert len(other.evidence) == 1


def test_evidence_mode_does_not_fold_or_attach_replaced_pages(tmp_path: Path) -> None:
    documents, chunks = _replacement_chain()

    response = _search(tmp_path, documents, chunks, "retention policy", mode="all")

    assert len(response.results) == 3
    assert all(len(result.evidence) == 1 for result in response.results)


# The evaluation tool reads every evidence entry of a result, so folded items count at the kept rank.


def test_evaluation_scores_a_folded_copy_and_a_replaced_page_at_the_kept_rank(tmp_path: Path) -> None:
    documents, chunks = _copied_sessions()
    sessions = _search(tmp_path / "sessions", documents, chunks, QUERY, mode="evidence")
    copy_only = eval_scoring.Expected(pages=frozenset(), exchanges=(ExchangeLocation(SECOND_PATH, 40, 44),))

    assert eval_scoring.first_rank(copy_only, [eval_scoring.result_target(item) for item in sessions.results]) == 1

    documents, chunks = _replacement_chain()
    pages = _search(tmp_path / "pages", documents, chunks, "retention policy", mode="knowledge")
    kept_rank = next(item.rank for item in pages.results if item.evidence[0].path == "wiki/decisions/new.md")
    old_only = eval_scoring.Expected(pages=frozenset({("default", "wiki/decisions/old.md")}), exchanges=())

    assert eval_scoring.first_rank(old_only, [eval_scoring.result_target(item) for item in pages.results]) == kept_rank
