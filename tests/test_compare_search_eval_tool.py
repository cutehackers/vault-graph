"""The search evaluation compare command (spec 2026-11-11 §4.1.3, A-4)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.benchmarks import compare_search_eval as tool
from tests.benchmarks import eval_scoring as scoring


def _score(
    question_id: str,
    kind: str,
    final_rank: int | None,
    *,
    split: str = "test",
    scored: bool = True,
    error: str | None = None,
) -> scoring.QuestionScore:
    ranks = scoring.StageRanks(3, None, None, 4, final_rank)
    return scoring.QuestionScore(question_id, kind, split, scored, final_rank, ranks, 0.1, error)


def _write_run(
    out_dir: Path,
    scores: Sequence[scoring.QuestionScore],
    *,
    layer: int = 1,
    split: str = "test",
    with_rows: bool = True,
) -> Path:
    """Write `summary.json` and `results.jsonl` the way `evaluate_search.main` does."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        **scoring.summarize(scores),
        "layer": layer,
        "split": split,
        "include_graph": False,
        "vault_ids": ["main"],
        "commit": "abc1234",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if with_rows:
        (out_dir / "results.jsonl").write_text(
            "".join(json.dumps(score.to_json(), sort_keys=True) + "\n" for score in scores), encoding="utf-8"
        )
    return out_dir


BASELINE = [
    _score("t1", "title", 1),
    _score("t2", "title", 7),
    _score("p1", "paraphrase", None),
    _score("p2", "paraphrase", 2),
    _score("p3", "paraphrase", 3),
    _score("h1", "how", 4),
    _score("n1", "no_answer", None, scored=False),
]
CURRENT = [
    _score("t1", "title", 1),  # same
    _score("t2", "title", 2),  # better
    _score("p1", "paraphrase", 5),  # better: None -> 5
    _score("p2", "paraphrase", None),  # worse
    _score("p3", "paraphrase", 4),  # worse
    _score("h1", "how", None, error="search failed"),  # not compared
    _score("n1", "no_answer", None, scored=False),  # not scored
    _score("d1", "decision", 1),  # only in current
]


def _layer3(path: Path, recall: float) -> Path:
    path.write_text(json.dumps({"recall_all_at_5": recall, "questions": 150}), encoding="utf-8")
    return path


def test_kind_deltas_cover_every_kind_and_the_total(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    deltas = {delta.kind: delta for delta in tool.kind_deltas(baseline, current)}

    assert list(deltas) == ["title", "paraphrase", "decision", "how", "no_answer", "total"]
    title = deltas["title"]
    assert (title.recall_at_5.before, title.recall_at_5.after, title.recall_at_5.change) == (0.5, 1.0, 0.5)
    assert (title.mrr.before, title.mrr.after, title.mrr.change) == (0.5714, 0.75, 0.1786)
    assert deltas["decision"].recall_at_5.before is None and deltas["decision"].recall_at_5.change is None
    assert deltas["no_answer"].recall_at_5.after is None
    assert deltas["total"].scored == (6, 6)


def test_question_changes_count_better_and_worse_ranks_by_id(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    changes = tool.question_changes(baseline, current)

    assert changes is not None
    assert changes.improved == ("p1", "t2")
    assert changes.regressed == ("p2", "p3")
    assert changes.unchanged == 1
    assert changes.not_compared == ("d1", "h1")


def test_question_changes_are_unknown_without_per_question_rows(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE, with_rows=False) / "summary.json")
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    assert tool.question_changes(baseline, current) is None
    report = tool.format_report(tool.compare(baseline, current))
    assert "좋아진 문항: 확인 안 됨" in report


def test_comparing_a_run_with_itself_shows_no_change(tmp_path: Path) -> None:
    run = tool.load_run(_write_run(tmp_path / "base", BASELINE))

    comparison = tool.compare(run, run)

    assert all(delta.recall_at_5.change in (0.0, None) for delta in comparison.deltas)
    assert all(delta.mrr.change in (0.0, None) for delta in comparison.deltas)
    assert comparison.changes is not None
    assert (len(comparison.changes.improved), len(comparison.changes.regressed)) == (0, 0)
    assert "좋아진 문항 0개, 나빠진 문항 0개" in tool.format_report(comparison)


def test_adoption_passes_only_when_every_rule_is_checked_and_met(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    comparison = tool.compare(
        baseline,
        current,
        layer3_baseline=tool.load_layer3(_layer3(tmp_path / "l3-base.json", 0.62)),
        layer3_current=tool.load_layer3(_layer3(tmp_path / "l3-cur.json", 0.61)),
        goal4="kept",
        goal5="kept",
    )

    assert [check.status for check in comparison.adoption] == ["통과"] * 4
    assert comparison.verdict == "채택"


def test_adoption_fails_when_layer3_drops_more_than_one_point(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    comparison = tool.compare(
        baseline,
        current,
        layer3_baseline=tool.load_layer3(_layer3(tmp_path / "l3-base.json", 0.62)),
        layer3_current=tool.load_layer3(_layer3(tmp_path / "l3-cur.json", 0.609)),
        goal4="kept",
        goal5="kept",
    )

    assert comparison.adoption[1].status == "실패"
    assert comparison.verdict == "채택 안 함"


def test_adoption_fails_when_layer1_test_does_not_improve_or_a_goal_breaks(tmp_path: Path) -> None:
    run = tool.load_run(_write_run(tmp_path / "base", BASELINE))

    comparison = tool.compare(run, run, goal5="broken")

    statuses = {check.name: check.status for check in comparison.adoption}
    assert statuses["층1 시험용"] == "실패"
    assert statuses["목표5"] == "실패"
    assert comparison.verdict == "채택 안 함"


def test_missing_inputs_show_as_unchecked_not_passed(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE, layer=2, split="all"))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT, layer=2, split="all"))

    comparison = tool.compare(baseline, current)

    assert [check.status for check in comparison.adoption] == ["확인 안 됨"] * 4
    assert comparison.verdict == "판정 보류"
    report = tool.format_report(comparison)
    assert report.count("확인 안 됨") >= 4
    assert "판정 보류" in report


def test_layer1_rule_needs_test_split_on_both_sides(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE, split="dev"))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    comparison = tool.compare(baseline, current)

    assert comparison.adoption[0].status == "확인 안 됨"
    assert any("split" in warning for warning in comparison.warnings)


def test_report_is_markdown_with_kind_table_counts_and_verdict(tmp_path: Path) -> None:
    baseline = tool.load_run(_write_run(tmp_path / "base", BASELINE))
    current = tool.load_run(_write_run(tmp_path / "cur", CURRENT))

    report = tool.format_report(tool.compare(baseline, current, goal4="kept"))

    assert "| kind | scored | recall@5 |" in report
    assert "| title | 2 → 2 | 0.5 → 1.0 (+0.5) |" in report
    assert "좋아진 문항 2개, 나빠진 문항 2개" in report
    assert "| 목표4 | 통과 |" in report
    assert "| 목표5 | 확인 안 됨 |" in report


def test_main_reads_directories_and_prints_the_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = _write_run(tmp_path / "base", BASELINE)
    cur = _write_run(tmp_path / "cur", CURRENT)

    tool.main(["--baseline", str(base), "--current", str(cur), "--goal4", "kept"])

    printed = capsys.readouterr().out
    assert "좋아진 문항 2개, 나빠진 문항 2개" in printed
    assert "판정 보류" in printed


def test_load_run_rejects_a_missing_summary(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="summary.json"):
        tool.load_run(tmp_path)
