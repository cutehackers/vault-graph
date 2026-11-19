"""The backlog question measurement of dreaming (spec 2026-11-19 §7, C8). No model and no index run here."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.benchmarks.measure_dream_backlog import (
    cites_expected,
    citing_pages,
    load_backlog_questions,
    main,
    summarize,
)
from vault_graph.operation.memory.evidence_quote import ExchangeCitation

PART = "raw/sessions/claude-code/2026-11-10-s1-part1.md"
EXPECTED = (ExchangeCitation(PART, 10, 20),)


def write_questions(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


def test_questions_name_the_exchanges_that_hold_the_answer(tmp_path: Path) -> None:
    path = write_questions(
        tmp_path / "q.jsonl",
        [{"id": "q1", "question": "기본 임베딩 모델은?", "cwd": "/repo", "expected_exchanges": [f"{PART} L10-L20"]}],
    )

    (question,) = load_backlog_questions(path)

    assert (question.question_id, question.cwd, question.expected) == ("q1", Path("/repo"), EXPECTED)


@pytest.mark.parametrize(
    ("row", "words"),
    [
        ({"id": "", "question": "q", "cwd": "/repo", "expected_exchanges": [f"{PART} L1-L2"]}, "id and question"),
        ({"id": "a", "question": "q", "cwd": "repo", "expected_exchanges": [f"{PART} L1-L2"]}, "absolute"),
        ({"id": "a", "question": "q", "cwd": "/repo", "expected_exchanges": []}, "at least one"),
        ({"id": "a", "question": "q", "cwd": "/repo", "expected_exchanges": [PART]}, "L<a>-L<b>"),
        ({"id": "a", "question": "q", "cwd": "/repo", "expected_exchanges": ["wiki/a.md L1-L2"]}, "L<a>-L<b>"),
    ],
)
def test_a_question_without_a_usable_exchange_location_is_refused(
    tmp_path: Path, row: dict[str, object], words: str
) -> None:
    with pytest.raises(ValueError, match=words):
        load_backlog_questions(write_questions(tmp_path / "q.jsonl", [row]))


def test_duplicate_ids_are_refused(tmp_path: Path) -> None:
    row: dict[str, object] = {"id": "a", "question": "q", "cwd": "/repo", "expected_exchanges": [f"{PART} L1-L2"]}

    with pytest.raises(ValueError, match="duplicate id"):
        load_backlog_questions(write_questions(tmp_path / "q.jsonl", [row, row]))


def test_a_page_cites_an_expected_exchange_when_the_line_ranges_overlap() -> None:
    assert cites_expected(f'- Evidence: {PART} L10-L20 "임베딩 모델은 arctic-m으로 정했어"', EXPECTED)
    assert cites_expected(f"| claim | inferred | {PART} L18-L30 |", EXPECTED)
    assert not cites_expected(f"- Evidence: {PART} L21-L30", EXPECTED)
    assert not cites_expected(f"- Evidence: {PART}", EXPECTED)
    assert not cites_expected("- Evidence: raw/sessions/other.md L10-L20", EXPECTED)


def test_citing_pages_reads_only_wiki_pages_of_the_given_vaults(tmp_path: Path) -> None:
    vault, other = tmp_path / "vault", tmp_path / "other"
    (vault / "wiki" / "decisions").mkdir(parents=True)
    (vault / "scratch" / "review").mkdir(parents=True)
    (other / "wiki").mkdir(parents=True)
    (vault / "wiki" / "decisions" / "model.md").write_text(f"# Model\n\n- Evidence: {PART} L10-L20\n", encoding="utf-8")
    (vault / "wiki" / "decisions" / "else.md").write_text("# Else\n", encoding="utf-8")
    # A proposal that waits for review is not memory yet.
    (vault / "scratch" / "review" / "r1.md").write_text(f"- Evidence: {PART} L10-L20\n", encoding="utf-8")
    (other / "wiki" / "copy.md").write_text(f"- Evidence: {PART} L10-L20\n", encoding="utf-8")

    assert citing_pages([vault], EXPECTED) == ((vault, "wiki/decisions/model.md"),)
    assert citing_pages([tmp_path / "missing"], EXPECTED) == ()


def test_the_summary_counts_remembered_and_found_questions() -> None:
    rows: list[dict[str, object]] = [
        {"id": "a", "remembered": True, "context_hit": True, "error": None},
        {"id": "b", "remembered": True, "context_hit": False, "error": None},
        {"id": "c", "remembered": False, "context_hit": False, "error": None},
        {"id": "d", "remembered": False, "context_hit": False, "error": "timeout"},
    ]

    assert summarize(rows) == {
        "questions": 4,
        "errors": 1,
        "remembered": 2,
        "context_hit": 1,
        "remembered_rate": 0.67,
        "context_hit_rate": 0.33,
    }
    assert summarize([])["context_hit_rate"] is None


def test_the_question_file_must_be_outside_the_repository(tmp_path: Path) -> None:
    inside = Path(__file__).parent / "questions.jsonl"

    with pytest.raises(ValueError, match="outside the repository"):
        main(inside, graph_home=tmp_path, vault_map=tmp_path / "vault-map.json", out_dir=tmp_path / "out")
