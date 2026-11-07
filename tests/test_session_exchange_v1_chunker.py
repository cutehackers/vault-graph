"""`session-exchange-v1` chunker for `vault-session/v1` files (spec 2026-11-05 §4.2.7, A-4 v1, A-9).

Fixture provenance. `2026-11-03-33333333-...-part1.md` started as a real `sessions capture` result:
vault-builder `tools/wiki/lib/session_capture.py` `read_turns` + `render_session_file` (vault-builder 687f5d8)
run on the synthetic transcript `tests/fixtures/session_adapter/subagent_compact/raw/`, with
project `demo-app`, part 1, trigger `SessionEnd`. After that a `/compact` command turn, a trailing
`Tools: Edit` line and a second exchange were added by hand, and `last_turn_*`/`turn_count` were updated.
`body_sha256` is left as rendered, so it no longer matches. The other two fixtures are written by hand
in the same format.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from vault_graph.indexing.ingestion.chunker_selection import CHUNKER_VERSIONS, select_chunker
from vault_graph.indexing.ingestion.document_chunking import CHUNKER_VERSION, ChunkDraft, DocumentChunker
from vault_graph.indexing.ingestion.document_models import ExtractedDocument, SourceDocument, SourceLocator
from vault_graph.indexing.ingestion.document_normalizer import DocumentNormalizer, stable_id
from vault_graph.indexing.ingestion.document_readers import MarkdownDocumentReader
from vault_graph.indexing.ingestion.session_exchange_v1_chunker import (
    MAX_WINDOW_TOKENS,
    SESSION_EXCHANGE_V1_VERSION,
    SessionExchangeV1Chunker,
)

_FIXTURES = Path(__file__).parent / "fixtures" / "session_v1"
_CAPTURED = "2026-11-03-33333333-3333-4333-8333-333333333333-part1.md"
_CONTINUED_LONG = "2026-11-04-44444444-4444-4444-8444-444444444444-part2.md"
_NO_HUMAN = "2026-11-05-55555555-5555-4555-8555-555555555555-part3.md"


def _extracted_text(path: str, text: str) -> ExtractedDocument:
    raw = text.encode("utf-8")
    source = SourceDocument(
        vault_id="default",
        root_path=Path("/vault"),
        path=path,
        suffix=".md",
        raw_bytes=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )
    return MarkdownDocumentReader().read(source)


def _extracted(name: str) -> ExtractedDocument:
    return _extracted_text(f"raw/sessions/claude-code/{name}", (_FIXTURES / name).read_text(encoding="utf-8"))


def _lines(*ranges: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    return ranges


def _line_ranges(locators: tuple[SourceLocator, ...]) -> tuple[tuple[int, int], ...]:
    result: list[tuple[int, int]] = []
    for locator in locators:
        coordinates = dict(locator.coordinates)
        start = int(coordinates["line"])
        result.append((start, int(coordinates.get("line_end", start))))
    return tuple(result)


def _view(draft: ChunkDraft) -> tuple[object, ...]:
    return (
        draft.section_path,
        draft.text,
        draft.parent_key,
        draft.keyword_metadata,
        _line_ranges(draft.source_locators),
        _line_ranges(draft.parent_locators),
    )


def _words(prefix: str, first: int, last: int) -> str:
    return " ".join(f"{prefix}{index:03d}" for index in range(first, last + 1))


_CAPTURED_KEY = f"raw/sessions/claude-code/{_CAPTURED}"
_CONTINUED_KEY = f"raw/sessions/claude-code/{_CONTINUED_LONG}"
_NO_HUMAN_KEY = f"raw/sessions/claude-code/{_NO_HUMAN}"
_CONTINUED_Q = "Q: (이전 파트에서 이어짐)"

_EXPECTED: dict[str, list[tuple[object, ...]]] = {
    # Tool-only turns, a tag-wrapped user turn, a compaction summary, a subagent, two main exchanges.
    _CAPTURED: [
        (
            ("Session 2026-11-03 part1", "Q: Review src/app.py with a reviewer subagent."),
            "Review src/app.py with a reviewer subagent.\n\n"
            "<command-name>/compact</command-name>\n\n"
            "This session is being continued from a previous conversation. Summary: the user asked for a review.\n\n"
            "The reviewer found one issue: a hard-coded secret.\n"
            "I will move it to the environment.",
            f"{_CAPTURED_KEY}:2026-11-03T14:00:00.000Z user:1",
            "tools: Agent, Edit",
            _lines((21, 21), (41, 41), (45, 45), (49, 50)),
            _lines((19, 25), (39, 52)),
        ),
        (
            ("Session 2026-11-03 part1 subagent a7f3", "Q: Review src/app.py for bugs."),
            "Review src/app.py for bugs.\n\nOne issue: line 3 sets password=[REDACTED:secret] in code.",
            f"{_CAPTURED_KEY}:2026-11-03T14:00:02.000Z subagent a7f3 user:1",
            "tools: Read",
            _lines((29, 29), (37, 37)),
            _lines((27, 37)),
        ),
        (
            ("Session 2026-11-03 part1", "Q: Thanks. Run the tests too."),
            "Thanks. Run the tests too.\n\nAll tests pass.",
            f"{_CAPTURED_KEY}:2026-11-03T14:07:00.000Z user:1",
            "tools: Bash",
            _lines((56, 56), (64, 64)),
            _lines((54, 64)),
        ),
    ],
    # A continued exchange first, then turns over 96 whitespace tokens.
    _CONTINUED_LONG: [
        (
            ("Session 2026-11-04 part2", _CONTINUED_Q),
            "Continuing the migration from the last part.",
            f"{_CONTINUED_KEY}:2026-11-04T09:00:00.000Z assistant:1",
            "tools: Bash",
            _lines((21, 21)),
            _lines((19, 23)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            "Explain the new schema in detail.",
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((27, 27)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("a", 1, 96),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((31, 31)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("a", 97, 100),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((31, 31)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("b", 1, 96),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((32, 32)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("b", 97, 100),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((32, 32)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("c", 1, 96),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((34, 34)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("c", 97, 192),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((34, 34)),
            _lines((25, 34)),
        ),
        (
            ("Session 2026-11-04 part2", "Q: Explain the new schema in detail."),
            _words("c", 193, 200),
            f"{_CONTINUED_KEY}:2026-11-04T09:00:30.000Z user:1",
            None,
            _lines((34, 34)),
            _lines((25, 34)),
        ),
    ],
    # No human turn at all: a continued main exchange and a continued subagent exchange.
    _NO_HUMAN: [
        (
            ("Session 2026-11-05 part3", _CONTINUED_Q),
            "<task-notification><task-id>t1</task-id><status>completed</status></task-notification>\n\n"
            "The background task finished.",
            f"{_NO_HUMAN_KEY}:2026-11-05T10:00:00.000Z user:1",
            "tools: Read",
            _lines((21, 21), (25, 25)),
            _lines((19, 25), (35, 37)),
        ),
        (
            ("Session 2026-11-05 part3 subagent b9c1", _CONTINUED_Q),
            "Found two call sites.",
            f"{_NO_HUMAN_KEY}:2026-11-05T10:00:02.000Z subagent b9c1 assistant:1",
            "tools: Grep",
            _lines((33, 33)),
            _lines((27, 33)),
        ),
    ],
}


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_fixture_windows_match_the_expected_list(name: str) -> None:
    drafts = SessionExchangeV1Chunker().chunk(_extracted(name))

    assert [_view(draft) for draft in drafts] == _EXPECTED[name]
    assert [draft.document_order for draft in drafts] == list(range(len(drafts)))


@pytest.mark.parametrize("name", sorted(_EXPECTED))
def test_windows_stay_within_96_tokens_and_never_hold_tool_lines(name: str) -> None:
    drafts = SessionExchangeV1Chunker().chunk(_extracted(name))

    for draft in drafts:
        assert draft.token_count == len(draft.text.split()) <= MAX_WINDOW_TOKENS == 96
        assert "Tools:" not in draft.text
        assert not any(line.startswith("## ") for line in draft.text.splitlines())


def test_split_pieces_of_one_long_line_point_at_their_own_characters() -> None:
    extracted = _extracted(_CONTINUED_LONG)
    text = extracted.source.raw_bytes.decode("utf-8")
    drafts = SessionExchangeV1Chunker().chunk(extracted)

    for draft in drafts:
        located = "\n".join(
            text[locator.start_offset : locator.end_offset]
            for locator in draft.source_locators
            if locator.start_offset is not None and locator.end_offset is not None
        )
        assert located.split() == draft.text.split()
    pieces = [draft.source_locators[0] for draft in drafts[-2:]]
    assert pieces[0].end_offset is not None and pieces[1].start_offset is not None
    assert pieces[0].end_offset < pieces[1].start_offset


def test_chunk_ids_follow_heading_occurrence_and_window_number() -> None:
    body = (
        "## 2026-11-06T08:00:00.000Z user\n\nfirst question\n\n"
        "## 2026-11-06T08:00:01.000Z assistant\n\n## Plan\n\nanswer one\n\n"
        "## 2026-11-06T08:00:00.000Z user\n\nsecond question\n"
    )
    extracted = _extracted_text(
        "raw/sessions/claude-code/2026-11-06-x-part1.md",
        f'---\nschema: vault-session/v1\npart: 1\nfirst_turn_at: "2026-11-06T08:00:00.000Z"\n---\n\n{body}',
    )
    drafts = SessionExchangeV1Chunker().chunk(extracted)

    assert [draft.text for draft in drafts] == ["first question\n\n## Plan\n\nanswer one", "second question"]
    path = extracted.source.path
    assert [draft.parent_key for draft in drafts] == [
        f"{path}:2026-11-06T08:00:00.000Z user:1",
        f"{path}:2026-11-06T08:00:00.000Z user:2",
    ]
    assert [draft.boundary_key for draft in drafts] == [
        "2026-11-06T08:00:00.000Z user:1:0",
        "2026-11-06T08:00:00.000Z user:2:0",
    ]


def test_question_value_uses_the_first_80_characters_on_one_line() -> None:
    question = "word " * 30
    extracted = _extracted_text(
        "raw/sessions/claude-code/2026-11-06-y-part1.md",
        '---\nschema: vault-session/v1\npart: 4\nfirst_turn_at: "2026-11-06T08:00:00.000Z"\n---\n\n'
        f"## 2026-11-06T08:00:00.000Z user\n\n{question}\nsecond line\n",
    )
    (draft,) = SessionExchangeV1Chunker().chunk(extracted)

    assert draft.section_path == ("Session 2026-11-06 part4", "Q: " + " ".join(["word"] * 30)[:80].strip())


def test_embedding_input_puts_session_and_question_before_the_window() -> None:
    chunker = SessionExchangeV1Chunker()

    assert chunker.embedding_input(("Session 2026-11-03 part1", "Q: Fix the test"), "body") == (
        "Session: 2026-11-03 part1\nQuestion: Fix the test\n\nbody"
    )
    assert chunker.embedding_input(("Session 2026-11-03 part1 subagent a7f3", _CONTINUED_Q), "body") == (
        "Session: 2026-11-03 part1 subagent a7f3\nQuestion: (이전 파트에서 이어짐)\n\nbody"
    )


def test_chunker_matches_the_document_chunker_protocol() -> None:
    chunker = SessionExchangeV1Chunker()

    assert chunker.version == SESSION_EXCHANGE_V1_VERSION == "session-exchange-v1-w96"
    assert isinstance(chunker, DocumentChunker)


def test_registered_v1_chunker_leaves_no_generic_windows_in_a_session_file() -> None:
    extracted = _extracted(_CAPTURED)
    assert isinstance(select_chunker(extracted), SessionExchangeV1Chunker)
    assert SESSION_EXCHANGE_V1_VERSION in CHUNKER_VERSIONS

    normalized = DocumentNormalizer().normalize(extracted)

    versions = [chunk.chunker_version for chunk in normalized.chunks]
    assert versions and versions.count(CHUNKER_VERSION) == 0
    assert set(versions) == {"session-exchange-v1-w96"}
    first = normalized.chunks[0]
    assert first.chunk_id == stable_id(
        "chunk",
        "session-exchange-v1-w96",
        "default",
        extracted.source.path,
        "2026-11-03T14:00:00.000Z user",
        "1",
        "0",
    )
