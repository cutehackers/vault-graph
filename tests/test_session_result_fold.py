"""Spec 2026-11-16 A1, A2: one session takes one result, its other matched exchanges attach as evidence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from tests.test_session_copy_and_replacement_folding import _exchange, _search
from tests.test_sqlite_metadata_store import make_chunk, make_document
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.retrieval.search.evidence_result_assembly import (
    DUPLICATE_CONTENT_WARNING,
    SESSION_EXCHANGES_WARNING,
    _fold_session_exchanges,
    _ParentGroup,
)
from vault_graph.retrieval.search.search_response import SearchResponse

QUERY = "tombstone sweeper archived folders"
STRONG = "### assistant\nThe tombstone sweeper skips archived folders: tombstone sweeper archived folders are frozen."
MIDDLE = "### assistant\nThe tombstone sweeper runs nightly over archived folders."
WEAK = "### assistant\nThe tombstone sweeper was renamed."
QUESTION = "### user\nHow does the sweeper behave?"


def _session(path: str, session_id: str, *, agent: str | None = "claude") -> DocumentSnapshot:
    frontmatter: dict[str, object] = {"schema": "vault-session/v2", "session_id": session_id}
    if agent is not None:
        frontmatter["agent"] = agent
    return replace(
        make_document("default", path, f"hash:{path}"),
        kind="raw",
        frontmatter=frontmatter,
        source_role="raw_evidence",
    )


def _one_window(document: DocumentSnapshot, exchange_id: str, text: str, *, line: int) -> list[ChunkSnapshot]:
    return _exchange(document, exchange_id, first_line=line, texts=(text,))


def _evidence(response: SearchResponse) -> list[list[tuple[str, str]]]:
    return [[(item.path, item.chunk_id) for item in result.evidence] for result in response.results]


def _two_part_session(*, agent: str | None) -> tuple[list[DocumentSnapshot], list[ChunkSnapshot]]:
    """Session one has three matched exchanges over two part files. A session forked from it holds the first
    part of ex-1 (a copy that ranks lower). Session two has one exchange that ranks between them."""
    part1 = _session("raw/sessions/2026-11-01-one-part1.md", "one", agent=agent)
    part2 = _session("raw/sessions/2026-11-02-one-part2.md", "one", agent=agent)
    fork = _session("raw/sessions/2026-11-02-fork-part1.md", "fork", agent=agent)
    other = _session("raw/sessions/2026-11-03-two-part1.md", "two", agent=agent)
    chunks = [
        *_exchange(part1, "ex-1", first_line=5, texts=(QUESTION, STRONG, "### assistant\nThe sweeper wrote the fix.")),
        *_one_window(part1, "ex-2", MIDDLE, line=20),
        *_one_window(part2, "ex-3", WEAK, line=70),
        *_exchange(fork, "ex-1", first_line=5, texts=(QUESTION, "### assistant\nThe tomb")),
        *_one_window(other, "ex-9", MIDDLE + " Folders.", line=5),
    ]
    return [part1, part2, fork, other], chunks


def test_one_session_is_one_result_with_its_other_exchanges_attached(tmp_path: Path) -> None:
    (tmp_path / "before").mkdir()
    (tmp_path / "after").mkdir()
    before = _search(tmp_path / "before", *_two_part_session(agent=None), QUERY, mode="evidence")
    after = _search(tmp_path / "after", *_two_part_session(agent="claude"), QUERY, mode="evidence")

    # Without `agent` there is no session key (F2): every exchange is a result, ex-1 and its copy fold once.
    unfolded = _evidence(before)
    assert len(unfolded) == 4
    one = [index for index, result in enumerate(before.results) if "-one-" in result.evidence[0].path]
    two = [index for index, result in enumerate(before.results) if "-two-" in result.evidence[0].path]
    assert len(one) == 3 and len(two) == 1

    # With the key, session one is one result at the place and score of its best exchange (D4).
    assert len(after.results) == 2
    best = before.results[one[0]]
    folded = next(result for result in after.results if "-one-" in result.evidence[0].path)
    assert folded.rank == (1 if one[0] < two[0] else 2)
    assert folded.signals == best.signals
    assert folded.summary == best.summary
    # Evidence order: itself, its copy, then the same-session exchanges in rank order (I4: same references).
    assert [(item.path, item.chunk_id) for item in folded.evidence] == [
        pair for index in one for pair in unfolded[index]
    ]
    assert [path for path, _ in unfolded[one[0]]] == [
        "raw/sessions/2026-11-01-one-part1.md",
        "raw/sessions/2026-11-02-fork-part1.md",
    ]
    assert any(warning.code == DUPLICATE_CONTENT_WARNING for warning in folded.warnings)
    attached = next(warning for warning in folded.warnings if warning.code == SESSION_EXCHANGES_WARNING)
    assert attached.severity == "info"
    assert "claude:one" in attached.message
    assert "2 other exchanges" in attached.message
    # The session-two result is unchanged.
    alone = next(result for result in after.results if "-two-" in result.evidence[0].path)
    assert [(item.path, item.chunk_id) for item in alone.evidence] == unfolded[two[0]]
    assert all(warning.code != SESSION_EXCHANGES_WARNING for warning in alone.warnings)


def test_attached_exchanges_are_references_and_at_most_three(tmp_path: Path) -> None:
    session = _session("raw/sessions/2026-11-01-five-part1.md", "five")
    texts = (STRONG, MIDDLE, MIDDLE + " Again.", WEAK, WEAK + " Again.")
    chunks = [
        chunk
        for number, text in enumerate(texts)
        for chunk in _one_window(session, f"ex-{number}", text, line=10 * number)
    ]
    unkeyed = replace(session, frontmatter={"schema": "vault-session/v2", "session_id": "five"})
    (tmp_path / "before").mkdir()
    (tmp_path / "after").mkdir()
    before = _search(tmp_path / "before", [unkeyed], chunks, QUERY, mode="evidence")
    after = _search(tmp_path / "after", [session], chunks, QUERY, mode="evidence")

    assert len(before.results) == 5
    assert len(after.results) == 1
    result = after.results[0]
    # Itself and the three highest other exchanges, each as a path and the exchange line range only.
    assert [(item.chunk_id, item.source_locators) for item in result.evidence] == [
        (item.evidence[0].chunk_id, item.evidence[0].source_locators) for item in before.results[:4]
    ]
    assert result.summary == before.results[0].summary
    warning = next(warning for warning in result.warnings if warning.code == SESSION_EXCHANGES_WARNING)
    assert "5 exchanges" in warning.message
    assert "1 left out" in warning.message


def _unit(
    path: str, parent_key: str | None, *, frontmatter: Mapping[str, object], vault_id: str = "default"
) -> _ParentGroup:
    document = replace(make_document(vault_id, path, f"hash:{path}"), frontmatter=dict(frontmatter))
    chunk = replace(
        make_chunk(vault_id, document.document_id, path, chunk_id=f"{path}:{parent_key}"), parent_key=parent_key
    )
    candidate = SimpleNamespace(vault_id=vault_id, document_id=chunk.document_id, chunk_id=chunk.chunk_id)
    return _ParentGroup(
        item=(candidate, SimpleNamespace(vault_id=vault_id, path=path), ""),  # type: ignore[arg-type]
        chunk=chunk,
        document=document,
    )


def test_fold_keeps_other_vaults_unkeyed_files_and_pages_apart() -> None:
    session = {"schema": "vault-session/v2", "agent": "claude", "session_id": "s1"}
    other_session = {"schema": "vault-session/v2", "agent": "claude", "session_id": "s2"}
    other_agent = {"schema": "vault-session/v2", "agent": "codex", "session_id": "s1"}
    no_agent = {"schema": "vault-session/v2", "session_id": "s1"}

    top = _unit("raw/sessions/s1-part1.md", "s1:ex-1", frontmatter=session)
    page = _unit("wiki/page.md", None, frontmatter={})
    second = _unit("raw/sessions/s2.md", "s2:ex-1", frontmatter=other_session)
    later_part = _unit("raw/sessions/s1-part2.md", "s1:ex-4", frontmatter=session)
    codex = _unit("raw/sessions/codex-s1.md", "s1:ex-1", frontmatter=other_agent)
    unkeyed_a = _unit("raw/sessions/nokey.md", "s1:ex-1", frontmatter=no_agent)
    unkeyed_b = _unit("raw/sessions/nokey.md", "s1:ex-2", frontmatter=no_agent)
    other_vault = _unit("raw/sessions/s1-part1.md", "s1:ex-2", frontmatter=session, vault_id="second")
    same_part = _unit("raw/sessions/s1-part1.md", "s1:ex-2", frontmatter=session)
    no_document = replace(_unit("raw/sessions/s1-part3.md", "s1:ex-5", frontmatter=session), document=None)

    folded = _fold_session_exchanges(
        (top, page, second, later_part, codex, unkeyed_a, unkeyed_b, other_vault, same_part, no_document)
    )

    assert folded == (
        replace(top, session_exchanges=(later_part, same_part)),
        page,
        second,
        codex,
        unkeyed_a,
        unkeyed_b,
        other_vault,
        no_document,
    )
