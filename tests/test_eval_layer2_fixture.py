"""Layer 2 search evaluation set stays valid (spec 2026-11-11 §4.1.1, A-5)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from tests.benchmarks.eval_dataset import KINDS, load_dataset

FIXTURE = Path(__file__).parent / "fixtures" / "eval_layer2"
VAULT = FIXTURE / "vault"
LAYER1_BASELINE = Path(__file__).parent / "fixtures" / "eval_layer1_baseline"


def test_every_kind_has_thirty_questions_split_in_half() -> None:
    dataset = load_dataset(FIXTURE / "questions.json")

    assert dataset.layer == 2
    for kind in KINDS:
        rows = [question for question in dataset.questions if question.kind == kind]
        splits = Counter(question.split for question in rows)
        assert len(rows) >= 30, kind
        assert splits["dev"] == splits["test"], kind


def test_every_expected_page_and_exchange_is_in_the_vault() -> None:
    dataset = load_dataset(FIXTURE / "questions.json")

    for question in dataset.questions:
        for page in question.pages:
            assert page.vault == "eval2", question.question_id
            assert (VAULT / page.path).is_file(), question.question_id
        for exchange in question.exchanges:
            lines = (VAULT / exchange.path).read_text(encoding="utf-8").splitlines()
            assert exchange.last_line <= len(lines), question.question_id
            first = lines[exchange.first_line - 1]
            assert first.startswith("## ") and first.endswith(" user"), question.question_id


def test_baselines_hold_numbers_for_each_split() -> None:
    for root, layer in ((FIXTURE / "baseline", 2), (LAYER1_BASELINE, 1)):
        for split in ("dev", "test", "all"):
            summary = json.loads((root / split / "summary.json").read_text(encoding="utf-8"))
            assert summary["layer"] == layer
            assert summary["split"] == split
            assert isinstance(summary["recall_at_5"], float)


def test_layer1_baseline_holds_no_question_text() -> None:
    for path in LAYER1_BASELINE.rglob("*"):
        if path.is_file():
            assert path.name == "summary.json", path
            assert '"question"' not in path.read_text(encoding="utf-8"), path
