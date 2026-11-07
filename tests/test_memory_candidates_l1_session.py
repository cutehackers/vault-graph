"""Cleanup candidates: L1 notes and session exchanges (spec 2026-11-05 §4.4.4, A-22, A-38).

Vault citation format (risk D2, D11), read from vault-builder ``docs/agent/OPERATING-SCHEMA.md``
§2.2 and §16.1 "Claim evidence" and ``tools/wiki/lib/lint.py`` ``_extract_raw_evidence_refs``:
a claim cites ``raw/sessions/...`` directly, with an optional ``#sha256=<file hash>``. Lint reads a
raw path up to whitespace or one of `` ` | , ; ) > ] ``, so an exchange location is written after a
space (``<path> L<a>-L<b>``). The Vault defines no exchange-level evidence yet, so a page written
outside vg usually cites only the file path, and that removes no exchange.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vault_graph.context.memory.memory_candidates import (
    CORRECTION_SIGNALS,
    DECISION_WORDS,
    DIRECTION_CHANGE_WORDS,
    SESSION_CANDIDATE_MAX_AGE,
    L1Note,
    MemoryCandidate,
    SessionExchange,
    SimilarPage,
    WikiPageText,
    build_memory_candidates,
    exchange_location,
)
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SESSION_A = "raw/sessions/claude-code/2026-11-01-aaaa1111-part1.md"
SESSION_B = "raw/sessions/claude-code/2026-11-02-bbbb2222-part1.md"
_SESSION_IDS = {SESSION_A: "sess-aaaa11", SESSION_B: "sess-bbbb22"}
PROJECT_SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"demo"}))


@dataclass
class FakeFinder:
    pages: Sequence[SimilarPage] = ()
    queries: list[str] = field(default_factory=list)

    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]:
        self.queries.append(query)
        return tuple(self.pages[:limit])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _note(name: str, text: str) -> L1Note:
    return L1Note(path=f"memory/{name}", sha256=_sha(text), text=text)


def _exchange(
    exchange_id: str,
    *,
    path: str = SESSION_A,
    lines: tuple[int, int] = (10, 20),
    days_ago: float = 1,
    human: str | None = None,
    outcome: str = "answered",
) -> SessionExchange:
    return SessionExchange(
        parent_key=f"{_SESSION_IDS[path]}:{exchange_id}",
        path=path,
        line_start=lines[0],
        line_end=lines[1],
        started_at=NOW - timedelta(days=days_ago),
        # Distinct exchanges get distinct text: the same time and text in two files is one copied exchange.
        human_text=human if human is not None else f"parser 테스트를 돌려 줘 ({exchange_id})",
        outcome=outcome,
        exchange_id=exchange_id,
    )


def _page(path: str, frontmatter: Mapping[str, object] | None = None) -> SimilarPage:
    return SimilarPage(
        vault_id="demo-vault",
        path=path,
        title=path.rsplit("/", 1)[-1],
        frontmatter=frontmatter or {"status": "active"},
        vault_scope=PROJECT_SCOPE,
        evidence_date="2026-11-01",
    )


def _build(
    *,
    notes: Sequence[L1Note] = (),
    imported: frozenset[str] = frozenset(),
    exchanges: Sequence[SessionExchange] = (),
    pages: Sequence[WikiPageText] = (),
    reviewed: frozenset[str] = frozenset(),
    finder: FakeFinder | None = None,
    limit: int | None = None,
) -> tuple[MemoryCandidate, ...]:
    return build_memory_candidates(
        project_id="demo",
        l1_notes=notes,
        imported_raw_sha256=imported,
        exchanges=exchanges,
        wiki_pages=pages,
        reviewed_keys=reviewed,
        similar_pages=finder or FakeFinder(),
        now=NOW,
        limit=limit,
    )


def _keys(candidates: Sequence[MemoryCandidate]) -> list[str]:
    return [candidate.key for candidate in candidates]


def test_l1_notes_not_imported_are_candidates_keyed_by_sha256() -> None:
    kept = _note("feedback_a.md", "pytest는 -q로 돌린다")
    imported = _note("feedback_b.md", "이미 Vault에 사본이 있다")
    index = _note("MEMORY.md", "- [a](feedback_a.md)")

    candidates = _build(notes=[imported, kept, index], imported=frozenset({imported.sha256}))

    assert _keys(candidates) == [f"l1:{kept.sha256}"]
    assert candidates[0].kind == "l1_note"
    assert candidates[0].location == "memory/feedback_a.md"


def test_l1_notes_with_the_same_content_give_one_candidate() -> None:
    first = _note("a.md", "같은 내용")
    second = _note("b.md", "같은 내용")

    assert _keys(_build(notes=[second, first])) == [f"l1:{first.sha256}"]


def test_session_exchanges_cited_by_no_wiki_page_are_candidates_with_exchange_location() -> None:
    exchange = _exchange("u-1000000001", lines=(12, 40))

    candidates = _build(exchanges=[exchange])

    assert _keys(candidates) == ["session:sess-aaaa11:u-1000000001"]
    assert candidates[0].kind == "session_exchange"
    assert candidates[0].location == f"{SESSION_A} L12-L40"
    assert exchange_location(SESSION_A, 12, 40) == f"{SESSION_A} L12-L40"


def test_a_citation_with_only_the_file_path_removes_no_exchange() -> None:
    exchanges = [_exchange("u-1", lines=(10, 20)), _exchange("u-2", lines=(21, 30))]
    page = WikiPageText(
        path="wiki/decisions/parser.md",
        text=f"---\nprimary_sources:\n  - {SESSION_A}\n---\n| claim | `{SESSION_A}#sha256=abc` |\n",
    )

    assert len(_build(exchanges=exchanges, pages=[page])) == 2


def test_a_citation_with_a_line_range_removes_only_that_exchange() -> None:
    exchanges = [
        _exchange("u-1", lines=(10, 20)),
        _exchange("u-2", lines=(21, 30)),
        _exchange("u-3", path=SESSION_B, lines=(10, 20)),
    ]
    page = WikiPageText(path="wiki/decisions/parser.md", text=f"| 파서는 v2다 | `{SESSION_A}` L21-L30 |\n")

    assert _keys(_build(exchanges=exchanges, pages=[page])) == ["session:sess-aaaa11:u-1", "session:sess-bbbb22:u-3"]


def test_a_citation_with_the_exchange_id_first_8_chars_removes_only_that_exchange() -> None:
    exchanges = [_exchange("4f2a9c1d-0000-4000-8000-000000000001"), _exchange("9e8d7c6b-0000-4000-8000-000000000002")]
    page = WikiPageText(path="wiki/decisions/parser.md", text=f"Evidence: `{SESSION_A}` 교환 4f2a9c1d\n")

    assert _keys(_build(exchanges=exchanges, pages=[page])) == [
        "session:sess-aaaa11:9e8d7c6b-0000-4000-8000-000000000002"
    ]


def test_line_ranges_next_to_another_session_path_or_outside_wiki_do_not_count() -> None:
    exchanges = [_exchange("u-1", lines=(10, 20))]
    other_file = WikiPageText(path="wiki/a.md", text=f"`{SESSION_B}` L10-L20\n")
    not_wiki = WikiPageText(path="raw/sources/notes.md", text=f"`{SESSION_A}` L10-L20\n")

    assert len(_build(exchanges=exchanges, pages=[other_file, not_wiki])) == 1


def test_fragment_style_line_ranges_also_count() -> None:
    exchanges = [_exchange("u-1", lines=(10, 20)), _exchange("u-2", lines=(21, 30))]
    page = WikiPageText(path="wiki/a.md", text=f"<!-- provenance: {SESSION_A}#L12-L15 -->\n")

    assert _keys(_build(exchanges=exchanges, pages=[page])) == ["session:sess-aaaa11:u-2"]


def test_exchanges_older_than_180_days_are_not_candidates() -> None:
    assert SESSION_CANDIDATE_MAX_AGE == timedelta(days=180)
    exchanges = [_exchange("u-old", days_ago=180.5), _exchange("u-edge", days_ago=180), _exchange("u-new", days_ago=1)]

    assert _keys(_build(exchanges=exchanges)) == ["session:sess-aaaa11:u-new", "session:sess-aaaa11:u-edge"]


def test_reviewed_keys_are_not_offered_again() -> None:
    note = _note("a.md", "노트")
    exchange = _exchange("u-1")

    candidates = _build(notes=[note], exchanges=[exchange], reviewed=frozenset({f"l1:{note.sha256}"}))

    assert _keys(candidates) == ["session:sess-aaaa11:u-1"]


def test_session_order_is_correction_then_decision_then_unresolved_error_with_direction_change_then_newest() -> None:
    exchanges = [
        _exchange("u-plain-old", lines=(1, 5), days_ago=9),
        _exchange("u-error", lines=(6, 9), days_ago=8, outcome="tool_error_unresolved"),
        _exchange("u-after-error", lines=(10, 12), days_ago=7.9, human="그 방법 말고 다른 방법으로 해"),
        _exchange("u-decision", lines=(13, 15), days_ago=7, human="v2 형식으로 가기로 결정했어"),
        _exchange("u-correction", lines=(16, 18), days_ago=6, human="아니야, 그건 틀렸어"),
        _exchange("u-error-no-turn", lines=(19, 20), days_ago=5, outcome="tool_error_unresolved"),
        _exchange("u-plain-new", lines=(21, 25), days_ago=1),
    ]

    keys = _keys(_build(exchanges=exchanges))

    assert keys == [
        "session:sess-aaaa11:u-correction",
        "session:sess-aaaa11:u-decision",
        "session:sess-aaaa11:u-error",
        "session:sess-aaaa11:u-plain-new",
        "session:sess-aaaa11:u-error-no-turn",
        "session:sess-aaaa11:u-after-error",
        "session:sess-aaaa11:u-plain-old",
    ]


def test_signal_word_lists_are_small_and_fixed() -> None:
    for words in (CORRECTION_SIGNALS, DECISION_WORDS, DIRECTION_CHANGE_WORDS):
        assert isinstance(words, tuple)
        assert 0 < len(words) <= 12
        assert all(word == word.casefold() for word in words)


def test_l1_candidates_come_before_session_candidates_and_limit_cuts_the_tail() -> None:
    note = _note("a.md", "노트")
    exchanges = [_exchange("u-1", days_ago=2), _exchange("u-2", lines=(21, 30), days_ago=1)]

    keys = _keys(_build(notes=[note], exchanges=exchanges, limit=2))

    assert keys == [f"l1:{note.sha256}", "session:sess-aaaa11:u-2"]


def test_comparison_material_is_at_most_5_project_pages_with_status_and_replacement() -> None:
    other_project = SimilarPage(
        vault_id="personal",
        path="wiki/concepts/other.md",
        title="other",
        frontmatter={"project": "elsewhere"},
        vault_scope=FixedVaultProjectScope(linked_projects=frozenset({"demo", "elsewhere"})),
    )
    retired = _page(
        "wiki/decisions/old.md",
        {"status": "retired", "retired_reason": "v1 폐기", "superseded_by": "wiki/decisions/new.md"},
    )
    pages = [other_project, retired, *(_page(f"wiki/concepts/p{index}.md") for index in range(6))]
    finder = FakeFinder(pages=pages)
    note = _note("a.md", "파서 v2 결정")

    candidates = _build(notes=[note], finder=finder)

    material = candidates[0].comparison
    assert [page.path for page in material] == [
        "wiki/decisions/old.md",
        "wiki/concepts/p0.md",
        "wiki/concepts/p1.md",
        "wiki/concepts/p2.md",
        "wiki/concepts/p3.md",
    ]
    assert material[0].status == "retired"
    assert material[0].retired_reason == "v1 폐기"
    assert material[0].superseded_by == "wiki/decisions/new.md"
    assert material[0].evidence_date == "2026-11-01"
    assert finder.queries == ["파서 v2 결정"]


def test_session_comparison_query_is_the_human_text() -> None:
    finder = FakeFinder()

    _build(exchanges=[_exchange("u-1", human="파서를 v2로 바꿔")], finder=finder)

    assert finder.queries == ["파서를 v2로 바꿔"]


def test_same_inputs_give_the_same_result_twice() -> None:
    notes = [_note("b.md", "둘"), _note("a.md", "하나")]
    exchanges = [_exchange("u-2", lines=(21, 30)), _exchange("u-1", lines=(10, 20), human="결정했어")]
    finder = FakeFinder(pages=[_page("wiki/concepts/p.md")])

    first = _build(notes=notes, exchanges=exchanges, finder=finder)
    second = _build(notes=list(reversed(notes)), exchanges=list(reversed(exchanges)), finder=finder)

    assert first == second


def test_review_log_hides_a_candidate_until_the_file_is_deleted(tmp_path: Path) -> None:
    graph_home = tmp_path / "graph-home"
    graph_home.mkdir()
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
    (vault / "wiki" / "a.md").write_text("# a\n", encoding="utf-8")
    vault_before = {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    log = JsonlReviewedLog(graph_home)
    exchange = _exchange("u-1")

    log.append(["session:sess-aaaa11:u-1"], outcome="skipped")
    hidden = _build(exchanges=[exchange], reviewed=log.reviewed_keys())
    (graph_home / "memory" / "reviewed.jsonl").unlink()
    shown = _build(exchanges=[exchange], reviewed=log.reviewed_keys())

    assert hidden == ()
    assert _keys(shown) == ["session:sess-aaaa11:u-1"]
    assert {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()} == vault_before
    assert not list(vault.rglob("reviewed.jsonl"))


def test_the_same_exchange_copied_into_resumed_sessions_is_one_candidate() -> None:
    # A resumed or forked Claude Code session starts a new session file that repeats the earlier turns.
    first = _exchange("u-1", path=SESSION_A, lines=(10, 20), days_ago=3, human="v2 형식으로 가기로 결정했어")
    copy = _exchange("u-1", path=SESSION_B, lines=(10, 20), days_ago=3, human="v2 형식으로 가기로 결정했어")

    assert _keys(_build(exchanges=[first, copy])) == ["session:sess-aaaa11:u-1"]


def test_a_citation_of_one_copy_removes_every_copy() -> None:
    first = _exchange("u-1", path=SESSION_A, lines=(10, 20), days_ago=3, human="v2 형식으로 가기로 결정했어")
    copy = _exchange("u-1", path=SESSION_B, lines=(10, 20), days_ago=3, human="v2 형식으로 가기로 결정했어")
    page = WikiPageText(path="wiki/decisions/v2.md", text=f"근거: {SESSION_B} L10-L20")

    assert _build(exchanges=[first, copy], pages=[page]) == ()
