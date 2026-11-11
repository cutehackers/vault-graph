"""Compare two search evaluation runs and print a summary to paste into a PR body.

Spec 2026-11-11 §4.1.3, A-4. Run from the repository root:
  uv run --python 3.12 python -m tests.benchmarks.compare_search_eval \
    --baseline <run dir or summary.json> --current <run dir or summary.json> \
    [--layer3-baseline <json> --layer3-current <json>] [--goal4 kept|broken] [--goal5 kept|broken]

A run is the output of `evaluate_search`: `summary.json` and, next to it, `results.jsonl`. A baseline may be
`summary.json` alone (layer 1 keeps numbers only in the repository); then the per-question counts show as
"확인 안 됨".

- Per kind and in total: scored questions, recall@5, recall@10 and MRR, before → after (change).
- Per question, matched by `id` over questions scored on either side: a lower `final_rank` is better and no
  rank is worse than any rank. A question missing from one side or failed on either side is not compared.
- Adoption rule (§4.1.3): the layer 1 test split improves, layer 3 drops by no more than one point, and
  goals 4 and 5 hold. A rule without its input is "확인 안 됨", never "통과", and the verdict is then
  "판정 보류" unless another rule failed.
  - Layer 1 improves when total recall@5 rises, or stays equal while MRR rises. Both runs must be
    layer 1 with split `test`.
  - Layer 3 files are JSON with a `recall_at_5` number on the 0 to 1 scale; one point is 0.01.
  - Goals 4 and 5 are measured elsewhere; pass `kept` or `broken`.

The report holds totals and counts only, no question text or question ids.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from tests.benchmarks.eval_dataset import KINDS

SUMMARY_FILE = "summary.json"
RESULTS_FILE = "results.jsonl"
LAYER1 = 1
ADOPTION_SPLIT = "test"
LAYER3_METRIC = "recall_all_at_5"
LAYER3_ALLOWED_DROP = 0.01
GOAL_STATES = ("kept", "broken")
METRICS = ("recall_at_5", "recall_at_10", "mrr")
SETTINGS = ("layer", "split", "include_graph")

PASSED = "통과"
FAILED = "실패"
UNCHECKED = "확인 안 됨"
ADOPT = "채택"
REJECT = "채택 안 함"
PENDING = "판정 보류"


@dataclass(frozen=True)
class EvalRun:
    summary: Mapping[str, object]
    rows: Mapping[str, Mapping[str, object]] | None  # by question id; None when results.jsonl is absent


@dataclass(frozen=True)
class Delta:
    before: float | None
    after: float | None

    @property
    def change(self) -> float | None:
        if self.before is None or self.after is None:
            return None
        return round(self.after - self.before, 4)


@dataclass(frozen=True)
class KindDelta:
    kind: str
    scored: tuple[int, int]
    recall_at_5: Delta
    recall_at_10: Delta
    mrr: Delta


@dataclass(frozen=True)
class QuestionChanges:
    improved: tuple[str, ...]
    regressed: tuple[str, ...]
    unchanged: int
    not_compared: tuple[str, ...]


@dataclass(frozen=True)
class RuleCheck:
    name: str
    status: str
    reason: str


@dataclass(frozen=True)
class Comparison:
    baseline: EvalRun
    current: EvalRun
    deltas: tuple[KindDelta, ...]
    changes: QuestionChanges | None
    adoption: tuple[RuleCheck, ...]
    warnings: tuple[str, ...]

    @property
    def verdict(self) -> str:
        statuses = {check.status for check in self.adoption}
        if FAILED in statuses:
            return REJECT
        if UNCHECKED in statuses:
            return PENDING
        return ADOPT


def load_run(path: Path) -> EvalRun:
    """Read a run directory, or a `summary.json` with an optional `results.jsonl` beside it."""
    summary_path = path / SUMMARY_FILE if path.is_dir() else path
    if not summary_path.is_file():
        raise ValueError(f"{SUMMARY_FILE} not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict):
        raise ValueError(f"{summary_path} must hold a JSON object")
    results_path = summary_path.parent / RESULTS_FILE
    if not results_path.is_file():
        return EvalRun(summary=summary, rows=None)
    rows: dict[str, Mapping[str, object]] = {}
    for line in results_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["id"])] = row
    return EvalRun(summary=summary, rows=rows)


def load_layer3(path: Path) -> float:
    """Read the layer 3 score: a JSON object with a `recall_at_5` number."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = payload.get(LAYER3_METRIC) if isinstance(payload, dict) else None
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{path} must hold a numeric {LAYER3_METRIC}")
    return float(value)


def kind_deltas(baseline: EvalRun, current: EvalRun) -> list[KindDelta]:
    """Before and after per kind, in the question set's kind order, then the total."""
    before_kinds, after_kinds = _by_kind(baseline.summary), _by_kind(current.summary)
    present = set(before_kinds) | set(after_kinds)
    kinds = [kind for kind in KINDS if kind in present] + sorted(present - set(KINDS))
    blocks = [(kind, before_kinds.get(kind, {}), after_kinds.get(kind, {})) for kind in kinds]
    blocks.append(("total", baseline.summary, current.summary))
    return [_delta(kind, before, after) for kind, before, after in blocks]


def question_changes(baseline: EvalRun, current: EvalRun) -> QuestionChanges | None:
    """Count questions whose final rank got better or worse. None when either run has no per-question rows."""
    if baseline.rows is None or current.rows is None:
        return None
    improved: list[str] = []
    regressed: list[str] = []
    not_compared: list[str] = []
    unchanged = 0
    for question_id in sorted(set(baseline.rows) | set(current.rows)):
        before, after = baseline.rows.get(question_id), current.rows.get(question_id)
        if not any(row is not None and row.get("scored") is True for row in (before, after)):
            continue
        if before is None or after is None or before.get("error") is not None or after.get("error") is not None:
            not_compared.append(question_id)
            continue
        old, new = _rank_order(before), _rank_order(after)
        if new < old:
            improved.append(question_id)
        elif new > old:
            regressed.append(question_id)
        else:
            unchanged += 1
    return QuestionChanges(tuple(improved), tuple(regressed), unchanged, tuple(not_compared))


def compare(
    baseline: EvalRun,
    current: EvalRun,
    *,
    layer3_baseline: float | None = None,
    layer3_current: float | None = None,
    goal4: str | None = None,
    goal5: str | None = None,
) -> Comparison:
    adoption = (
        _layer1_rule(baseline, current),
        _layer3_rule(layer3_baseline, layer3_current),
        _goal_rule("목표4", goal4),
        _goal_rule("목표5", goal5),
    )
    warnings = tuple(
        f"기준값과 새 결과의 {key}가 다르다: {baseline.summary.get(key)} → {current.summary.get(key)}"
        for key in SETTINGS
        if baseline.summary.get(key) != current.summary.get(key)
    )
    return Comparison(
        baseline=baseline,
        current=current,
        deltas=tuple(kind_deltas(baseline, current)),
        changes=question_changes(baseline, current),
        adoption=adoption,
        warnings=warnings,
    )


def format_report(comparison: Comparison) -> str:
    """Markdown for a PR body: kind table, question counts, adoption rule table and verdict."""
    lines = [
        "### 검색 평가 비교",
        "",
        f"기준값: {_run_label(comparison.baseline)} → 새 결과: {_run_label(comparison.current)}",
        "",
        "| kind | scored | recall@5 | recall@10 | MRR |",
        "|---|---|---|---|---|",
    ]
    for delta in comparison.deltas:
        cells = (
            delta.kind,
            f"{delta.scored[0]} → {delta.scored[1]}",
            *(_delta_cell(metric) for metric in (delta.recall_at_5, delta.recall_at_10, delta.mrr)),
        )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    changes = comparison.changes
    if changes is None:
        lines.append(f"좋아진 문항: {UNCHECKED}, 나빠진 문항: {UNCHECKED} (한쪽에 {RESULTS_FILE}이 없다)")
    else:
        lines.append(
            f"좋아진 문항 {len(changes.improved)}개, 나빠진 문항 {len(changes.regressed)}개 "
            f"(그대로 {changes.unchanged}개, 비교 못 함 {len(changes.not_compared)}개)"
        )
    lines += ["", "#### 채택 규칙 (spec §4.1.3)", "", "| 항목 | 판정 | 근거 |", "|---|---|---|"]
    lines += [f"| {check.name} | {check.status} | {check.reason} |" for check in comparison.adoption]
    lines += ["", f"판정: {comparison.verdict}"]
    if comparison.warnings:
        lines += ["", *(f"주의: {warning}" for warning in comparison.warnings)]
    return "\n".join(lines)


def main(argv: Sequence[str]) -> Comparison:
    arguments = _parse_args(argv)
    comparison = compare(
        load_run(arguments.baseline),
        load_run(arguments.current),
        layer3_baseline=load_layer3(arguments.layer3_baseline) if arguments.layer3_baseline else None,
        layer3_current=load_layer3(arguments.layer3_current) if arguments.layer3_current else None,
        goal4=arguments.goal4,
        goal5=arguments.goal5,
    )
    print(format_report(comparison))
    return comparison


def _layer1_rule(baseline: EvalRun, current: EvalRun) -> RuleCheck:
    name = "층1 시험용"
    for label, run in (("기준값", baseline), ("새 결과", current)):
        layer, split = run.summary.get("layer"), run.summary.get("split")
        if layer != LAYER1 or split != ADOPTION_SPLIT:
            return RuleCheck(name, UNCHECKED, f"{label}가 층1 {ADOPTION_SPLIT}이 아니다 (layer {layer}, split {split})")
    recall = Delta(_metric(baseline.summary, "recall_at_5"), _metric(current.summary, "recall_at_5"))
    mrr = Delta(_metric(baseline.summary, "mrr"), _metric(current.summary, "mrr"))
    reason = f"recall@5 {_delta_cell(recall)}, MRR {_delta_cell(mrr)}"
    if recall.change is None or mrr.change is None:
        return RuleCheck(name, UNCHECKED, reason)
    improved = recall.change > 0 or (recall.change == 0 and mrr.change > 0)
    return RuleCheck(name, PASSED if improved else FAILED, reason)


def _layer3_rule(before: float | None, after: float | None) -> RuleCheck:
    name = "층3 1점 넘게 떨어지지 않음"
    if before is None or after is None:
        return RuleCheck(name, UNCHECKED, "층3 기준값과 새 결과가 모두 주어지지 않았다")
    delta = Delta(before, after)
    drop = round(before - after, 4)
    status = FAILED if drop > LAYER3_ALLOWED_DROP else PASSED
    return RuleCheck(name, status, f"{LAYER3_METRIC} {_delta_cell(delta)}")


def _goal_rule(name: str, state: str | None) -> RuleCheck:
    if state is None:
        return RuleCheck(name, UNCHECKED, "결과가 주어지지 않았다")
    if state not in GOAL_STATES:
        raise ValueError(f"{name} must be one of {', '.join(GOAL_STATES)}")
    return RuleCheck(name, PASSED if state == "kept" else FAILED, "유지됨" if state == "kept" else "깨짐")


def _by_kind(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    by_kind = summary.get("by_kind")
    if not isinstance(by_kind, dict):
        return {}
    return {str(kind): block for kind, block in by_kind.items() if isinstance(block, dict)}


def _delta(kind: str, before: Mapping[str, object], after: Mapping[str, object]) -> KindDelta:
    recall_5, recall_10, mrr = (Delta(_metric(before, key), _metric(after, key)) for key in METRICS)
    return KindDelta(kind, (_count(before, "scored"), _count(after, "scored")), recall_5, recall_10, mrr)


def _metric(block: Mapping[str, object], key: str) -> float | None:
    value = block.get(key)
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _count(block: Mapping[str, object], key: str) -> int:
    value = block.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _rank_order(row: Mapping[str, object]) -> float:
    rank = row.get("final_rank")
    return float(rank) if isinstance(rank, int) and not isinstance(rank, bool) else float("inf")


def _delta_cell(delta: Delta) -> str:
    before = "-" if delta.before is None else str(delta.before)
    after = "-" if delta.after is None else str(delta.after)
    change = delta.change
    return f"{before} → {after}" if change is None else f"{before} → {after} ({change:+})"


def _run_label(run: EvalRun) -> str:
    summary = run.summary
    return f"층{summary.get('layer')} {summary.get('split')}, commit {summary.get('commit')}"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--baseline", type=Path, required=True, help="Baseline run directory or summary.json.")
    parser.add_argument("--current", type=Path, required=True, help="New run directory or summary.json.")
    parser.add_argument("--layer3-baseline", type=Path, help=f"Layer 3 baseline JSON with {LAYER3_METRIC}.")
    parser.add_argument("--layer3-current", type=Path, help=f"Layer 3 new JSON with {LAYER3_METRIC}.")
    parser.add_argument("--goal4", choices=GOAL_STATES, help="build_context_pack answer hit kept or broken.")
    parser.add_argument("--goal5", choices=GOAL_STATES, help="No retired or other-project memory injected.")
    return parser.parse_args(argv)


if __name__ == "__main__":
    main(sys.argv[1:])
