"""Scoring of the seeded-error measurement of the dream verify judgment (spec 2026-11-19 D3). No model runs here."""

from __future__ import annotations

from tests.benchmarks.measure_dream_verify import CASES, build_input, page_text, passes_checks, score
from vault_graph.interface.composition.adapters.dream_judge import VERIFY_ACTIONS, DreamJudgment


def judgment(index: int, action: str, **fields: str) -> DreamJudgment:
    items, _ = build_input(CASES)
    return DreamJudgment(key=items[index].key, action=action, **fields)


def test_the_cases_are_half_seeded_half_controls_in_two_languages() -> None:
    seeded = [case for case in CASES if case.wrong_claim is not None]

    assert len(seeded) == len(CASES) - len(seeded) == 8
    assert sum(1 for case in CASES if case.name.startswith("ko-")) == 8
    assert all(case.wrong_claim in case.claims for case in seeded)
    assert all(str(case.wrong_claim) in page_text(case) for case in seeded)
    items, pages = build_input(CASES)
    assert all(
        item.actions == VERIFY_ACTIONS and item.pages == (page.path,) for item, page in zip(items, pages, strict=True)
    )


def test_a_perfect_judge_scores_one_and_one() -> None:
    items, _ = build_input(CASES)
    answers = [
        DreamJudgment(key=item.key, action="none")
        if case.wrong_claim is None
        else DreamJudgment(
            key=item.key,
            action="supersede_claim",
            quote=case.user_text,
            path=item.pages[0],
            claim=case.wrong_claim,
            new_claim="replaced",
        )
        for case, item in zip(CASES, items, strict=True)
    ]

    summary = score(CASES, items, answers)

    assert (summary["detected"], summary["precision"], summary["recall"]) == (8, 1.0, 1.0)
    assert summary["missed"] == summary["false_alarms"] == summary["dropped_by_checks"] == []


def test_wrong_rows_invented_quotes_and_false_alarms_are_counted() -> None:
    items, _ = build_input(CASES)
    first, control = CASES[0], CASES[8]
    assert first.wrong_claim is not None and control.wrong_claim is None
    answers = [
        # The right action on the wrong row: missed.
        judgment(
            0, "supersede_claim", quote=first.user_text, path=items[0].pages[0], claim=first.claims[1], new_claim="x"
        ),
        # A quote the user never typed: dropped by the checks, so also missed.
        judgment(1, "retire_memory", quote="the user never typed this sentence", path=items[1].pages[0], reason="old"),
        # A retire with a real quote: detected.
        judgment(2, "retire_memory", quote=CASES[2].user_text, path=items[2].pages[0], reason="changed"),
        # A proposal on a negative control: a false alarm.
        judgment(8, "retire_memory", quote=control.user_text, path=items[8].pages[0], reason="stale"),
    ]

    summary = score(CASES, items, answers)

    assert summary["detected"] == 1
    assert summary["false_alarms"] == [control.name]
    assert summary["dropped_by_checks"] == [CASES[1].name]
    assert (summary["precision"], summary["recall"]) == (0.5, 0.12)
    assert not passes_checks(answers[1], items[1], CASES[1])
