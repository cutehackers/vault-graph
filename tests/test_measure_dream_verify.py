"""Scoring of the seeded-error measurement of the dream verify judgment (spec 2026-11-19 D3). No model runs here."""

from __future__ import annotations

from tests.benchmarks.measure_dream_verify import (
    CASES,
    ORDER,
    build_input,
    ordered_cases,
    page_text,
    passes_checks,
    score,
)
from vault_graph.interface.composition.adapters.dream_judge import VERIFY_ACTIONS, DreamJudgment
from vault_graph.interface.composition.adapters.dream_worker import BATCH_SIZE

ORDERED = ordered_cases()
ITEMS, PAGES = build_input(ORDERED)


def position(name: str) -> int:
    return next(index for index, case in enumerate(ORDERED) if case.name == name)


def judgment(name: str, action: str, **fields: str) -> DreamJudgment:
    index = position(name)
    return DreamJudgment(key=ITEMS[index].key, action=action, path=ITEMS[index].pages[0], **fields)


def test_the_cases_are_half_seeded_half_controls_in_two_languages() -> None:
    seeded = [case for case in CASES if case.wrong_claim is not None]

    assert len(seeded) == len(CASES) - len(seeded) == 10
    assert sum(1 for case in CASES if case.name.startswith("ko-")) == 10
    assert sum(1 for case in CASES if not case.claim_table) == 4
    assert all(str(case.wrong_claim) in page_text(case) for case in seeded)
    assert all(len(case.claims) == 2 for case in CASES if case.claim_table)
    assert sorted(ORDER) == list(range(len(CASES)))


def test_nothing_the_judge_sees_names_the_kind_of_a_case() -> None:
    for item, page, case in zip(ITEMS, PAGES, ORDERED, strict=True):
        shown = f"{item.key} {page.path}"
        assert case.name not in shown
        assert "control" not in shown and "seed:" in item.key  # every key has the same neutral prefix
        assert item.actions == VERIFY_ACTIONS and item.pages == (page.path,)


def test_every_batch_mixes_the_kinds_and_holds_no_page_text_twice() -> None:
    for start in range(0, len(ORDERED), BATCH_SIZE):
        batch = ORDERED[start : start + BATCH_SIZE]
        kinds = {case.wrong_claim is None for case in batch}
        texts = [page_text(case) for case in batch]

        assert kinds == {True, False}
        assert len(set(texts)) == len(texts)


def right_answer(index: int) -> DreamJudgment:
    case, item = ORDERED[index], ITEMS[index]
    if case.wrong_claim is None:
        return DreamJudgment(key=item.key, action="none")
    if not case.claim_table:
        return DreamJudgment(
            key=item.key, action="update_memory", quote=case.user_text, path=item.pages[0], addition="changed"
        )
    return DreamJudgment(
        key=item.key,
        action="supersede_claim",
        quote=case.user_text,
        path=item.pages[0],
        claim=case.wrong_claim,
        new_claim="replaced",
    )


def test_a_perfect_judge_scores_one_and_one() -> None:
    summary = score(ORDERED, ITEMS, [right_answer(index) for index in range(len(ORDERED))])

    assert (summary["detected"], summary["precision"], summary["recall"]) == (10, 1.0, 1.0)
    assert summary["missed"] == summary["false_alarms"] == summary["dropped_by_checks"] == []
    assert summary["retired_whole_page"] == []


def test_wrong_rows_whole_page_retires_invented_quotes_and_false_alarms_are_counted() -> None:
    first = CASES[0]
    answers = [
        # The right action on the wrong row: missed.
        judgment(first.name, "supersede_claim", quote=first.user_text, claim=first.claims[1], new_claim="x"),
        # Retiring a claim-table page whose other row is still true: missed, and counted on its own.
        judgment(CASES[1].name, "retire_memory", quote=CASES[1].user_text, reason="changed"),
        # A quote the user never typed: dropped by the checks, so also missed.
        judgment(CASES[2].name, "retire_memory", quote="the user never typed this sentence", reason="old"),
        # An update to a claim-table page: a dream run refuses the page shape, so it is dropped.
        judgment(CASES[3].name, "update_memory", quote=CASES[3].user_text, addition="changed"),
        # Retiring a one-fact page that is wrong now: detected.
        judgment("ko-note-seeded", "retire_memory", quote=CASES[16].user_text, reason="changed"),
        # A proposal on a negative control: a false alarm.
        judgment("en-note-control", "retire_memory", quote=CASES[19].user_text, reason="stale"),
    ]

    summary = score(ORDERED, ITEMS, answers)

    assert summary["detected"] == 1
    assert summary["retired_whole_page"] == [CASES[1].name]
    assert sorted(summary["dropped_by_checks"]) == sorted([CASES[2].name, CASES[3].name])  # type: ignore[call-overload]
    assert summary["false_alarms"] == ["en-note-control"]
    assert (summary["precision"], summary["recall"]) == (0.5, 0.1)
    assert not passes_checks(answers[2], ITEMS[position(CASES[2].name)], CASES[2])
