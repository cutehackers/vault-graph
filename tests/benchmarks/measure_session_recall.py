"""Session recall measurement: exchange-level recall@5, recall@10 and MRR of `vg search`.

Spec 2026-11-05-session-memory-indexing §4.2.10, A-8. Run from the repository root:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.measure_session_recall \
    --questions <questions.jsonl> --graph-home <graph home> --out-dir <out dir> --stage <a|b|c> [--vault-id ID]

The question file and out_dir must be outside this repository: the questions hold personal session
content. Each question line is
`{"id": str, "question": str, "expected_exchanges": [str, ...], "kind": str}`, where `kind` is one of
`decision`, `how`, `file`, `error`, `paraphrase`, and each expected exchange is the location vg shows
for an exchange, `<Vault-relative path> L<first line>-L<last line>`. A location works at every stage:
the old document chunks (a), the v1 exchange chunker (b) and the v2 exchange chunker (c).

A result matches an expected exchange when one of its evidence items has the same path and a line
range that overlaps the exchange. Search groups the windows of one exchange into one result, so
several windows of an exchange count once. `vg search --mode evidence` runs as a subprocess once per
question. Per-question rows go to `out_dir/results.jsonl` and `out_dir/summary.json` holds totals only,
without question text.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

RESULT_LIMIT = 20
RUN_TIMEOUT_SECONDS = 300.0
KINDS = ("decision", "how", "file", "error", "paraphrase")
STAGES = ("a", "b", "c")
REPO_ROOT = Path(__file__).resolve().parents[2]
_LOCATION = re.compile(r"^(?P<path>\S.*?) L(?P<first>\d+)-L(?P<last>\d+)$")


@dataclass(frozen=True)
class ExchangeLocation:
    path: str
    first_line: int
    last_line: int

    def overlaps(self, path: str, first_line: int, last_line: int) -> bool:
        return path == self.path and first_line <= self.last_line and last_line >= self.first_line


@dataclass(frozen=True)
class Question:
    question_id: str
    text: str
    expected: tuple[ExchangeLocation, ...]
    kind: str


@dataclass(frozen=True)
class ResultUnit:
    """One search result reduced to what matching needs: its evidence spans and whether it is a subagent window."""

    spans: tuple[tuple[str, int, int], ...]
    subagent: bool


@dataclass(frozen=True)
class QuestionScore:
    question_id: str
    kind: str
    first_rank: int | None
    subagent_in_top10: int
    top10: int
    seconds: float
    error: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.question_id,
            "kind": self.kind,
            "first_rank": self.first_rank,
            "subagent_in_top10": self.subagent_in_top10,
            "top10": self.top10,
            "seconds": round(self.seconds, 3),
            "error": self.error,
        }


def parse_location(text: str) -> ExchangeLocation:
    match = _LOCATION.match(text.strip())
    if match is None:
        raise ValueError(f"expected exchange must look like '<path> L<a>-L<b>': {text!r}")
    first, last = int(match["first"]), int(match["last"])
    if first > last:
        raise ValueError(f"expected exchange line range is reversed: {text!r}")
    return ExchangeLocation(path=match["path"], first_line=first, last_line=last)


def load_questions(path: Path) -> tuple[Question, ...]:
    questions: list[Question] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: a question must be a JSON object")
        question_id, text, kind = row.get("id"), row.get("question"), row.get("kind")
        expected = row.get("expected_exchanges")
        if not isinstance(question_id, str) or not isinstance(text, str) or not text.strip():
            raise ValueError(f"line {number}: id and question must be non-empty strings")
        if kind not in KINDS:
            raise ValueError(f"line {number}: kind must be one of {', '.join(KINDS)}")
        if not isinstance(expected, list) or not expected or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"line {number}: expected_exchanges must be a non-empty list of locations")
        if question_id in seen:
            raise ValueError(f"line {number}: duplicate id {question_id!r}")
        seen.add(question_id)
        questions.append(Question(question_id, text, tuple(parse_location(item) for item in expected), str(kind)))
    return tuple(questions)


def result_units(payload: object) -> tuple[ResultUnit, ...]:
    """Read `vg search --format json` output into result units, in rank order."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("vg search output has no results list")
    units: list[ResultUnit] = []
    for result in payload["results"]:
        spans: list[tuple[str, int, int]] = []
        subagent = False
        for evidence in result.get("evidence", []):
            path = str(evidence.get("path", ""))
            section_path = [str(part) for part in evidence.get("section_path", [])]
            subagent = subagent or any(" subagent " in f" {part} " for part in section_path)
            for locator in evidence.get("source_locators", []):
                lines = _locator_lines(locator)
                if lines is not None:
                    spans.append((path, *lines))
        units.append(ResultUnit(spans=tuple(spans), subagent=subagent))
    return tuple(units)


def first_rank(expected: Sequence[ExchangeLocation], units: Sequence[ResultUnit]) -> int | None:
    """1-based rank of the first result that overlaps an expected exchange, or None when absent.

    Search already returns one result per v1/v2 exchange (parent grouping), so each rank is one exchange
    at stages (b) and (c). At stage (a) the old chunks are per turn, so one exchange may take several
    ranks; that is the baseline being measured.
    """
    for rank, unit in enumerate(units, start=1):
        if any(location.overlaps(*span) for location in expected for span in unit.spans):
            return rank
    return None


def summarize(scores: Sequence[QuestionScore], *, stage: str, commit: str) -> dict[str, object]:
    measured = [score for score in scores if score.error is None]

    def recall(limit: int, rows: Sequence[QuestionScore]) -> float | None:
        if not rows:
            return None
        return round(sum(1 for row in rows if row.first_rank is not None and row.first_rank <= limit) / len(rows), 4)

    def mrr(rows: Sequence[QuestionScore]) -> float | None:
        if not rows:
            return None
        return round(sum(1.0 / row.first_rank for row in rows if row.first_rank is not None) / len(rows), 4)

    top10 = sum(score.top10 for score in measured)
    return {
        "stage": stage,
        "commit": commit,
        "questions": len(scores),
        "failed": len(scores) - len(measured),
        "recall_at_5": recall(5, measured),
        "recall_at_10": recall(10, measured),
        "mrr": mrr(measured),
        "by_kind": {
            kind: {"questions": len(rows), "recall_at_5": recall(5, rows), "recall_at_10": recall(10, rows)}
            for kind in KINDS
            if (rows := [score for score in measured if score.kind == kind])
        },
        "subagent_share_in_top10": round(sum(s.subagent_in_top10 for s in measured) / top10, 4) if top10 else None,
        "median_seconds": round(statistics.median(score.seconds for score in measured), 3) if measured else None,
    }


def main(
    questions: Path, graph_home: Path, out_dir: Path, stage: str, vault_id: str | None = None
) -> dict[str, object]:
    _require_outside_repository(questions, "questions")
    _require_outside_repository(out_dir, "out_dir")
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    loaded = load_questions(questions)
    scores = [_score(question, graph_home=graph_home, vault_id=vault_id) for question in loaded]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.jsonl").write_text(
        "".join(json.dumps(score.to_json(), sort_keys=True) + "\n" for score in scores), encoding="utf-8"
    )
    summary = summarize(scores, stage=stage, commit=_repository_commit())
    (out_dir / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def _score(question: Question, *, graph_home: Path, vault_id: str | None) -> QuestionScore:
    command = [
        sys.executable,
        "-c",
        "from vault_graph.interface.cli.main import app; app()",
        "search",
        question.text,
        "--graph-home",
        str(graph_home),
        "--format",
        "json",
        "--limit",
        str(RESULT_LIMIT),
        # Session files are raw evidence; the default knowledge mode searches wiki pages only.
        "--mode",
        "evidence",
    ]
    if vault_id is not None:
        command += ["--vault-id", vault_id]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS, check=False, cwd=REPO_ROOT
        )
        seconds = time.monotonic() - started
        if completed.returncode != 0:
            raise ValueError(f"vg search exited {completed.returncode}: {completed.stderr.strip()[:200]}")
        units = result_units(json.loads(completed.stdout))
    except (subprocess.TimeoutExpired, ValueError) as exc:
        return QuestionScore(question.question_id, question.kind, None, 0, 0, time.monotonic() - started, str(exc))
    top = units[:10]
    return QuestionScore(
        question_id=question.question_id,
        kind=question.kind,
        first_rank=first_rank(question.expected, units),
        subagent_in_top10=sum(1 for unit in top if unit.subagent),
        top10=len(top),
        seconds=seconds,
        error=None,
    )


def _locator_lines(locator: object) -> tuple[int, int] | None:
    if not isinstance(locator, dict):
        return None
    coordinates = {str(key): str(value) for key, value in locator.get("coordinates", [])}
    if "line" not in coordinates:
        return None
    first = int(coordinates["line"])
    return first, int(coordinates.get("line_end", first))


def _require_outside_repository(path: Path, label: str) -> None:
    if path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError(f"{label} must be outside the repository: it holds personal session content")


def _repository_commit() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() or "unknown"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--graph-home", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--vault-id")
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    print(
        json.dumps(
            main(arguments.questions, arguments.graph_home, arguments.out_dir, arguments.stage, arguments.vault_id),
            sort_keys=True,
            indent=2,
        )
    )
