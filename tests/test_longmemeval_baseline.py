"""Layer 3 baseline holds what later runs compare against (spec 2026-11-11 §4.1.4, A-6, 목표9)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.benchmarks.compare_search_eval import FAILED, LAYER3_METRIC, PASSED, _layer3_rule, load_layer3
from tests.benchmarks.longmemeval_run import SAMPLE_QUESTIONS

BASELINE = Path(__file__).parent / "fixtures" / "longmemeval_baseline.json"


def test_baseline_names_data_version_question_count_settings_and_commit() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    assert len(baseline["data"]["sha256"]) == 64
    assert baseline["data"]["file"] == "longmemeval_s_cleaned.json"
    assert baseline["questions"] == baseline["settings"]["limit"] == SAMPLE_QUESTIONS
    assert baseline["failed"] == 0
    assert baseline["settings"]["scope"] == "sample-150"
    assert baseline["settings"]["metric"] == LAYER3_METRIC
    assert baseline["commit"]
    assert sum(row["questions"] for row in baseline["by_type"].values()) == baseline["questions"]


def test_compare_reads_the_baseline_and_sees_no_change_against_itself() -> None:
    score = load_layer3(BASELINE)

    assert 0.0 <= score <= 1.0
    check = _layer3_rule(score, score)
    assert check.status == PASSED
    assert check.reason.endswith("(+0.0)")


def test_a_drop_of_more_than_one_point_fails() -> None:
    score = load_layer3(BASELINE)

    assert _layer3_rule(score, round(score - 0.02, 4)).status == FAILED
