"""Measure 1: compare top-5 hit rate and latency of Vault search and `vg search`.

Run from the repository root:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.measure_vault_search_parity \
    --questions <questions.jsonl> --vault <vault root> --graph-home <graph home> --out-dir <out dir>

The question file and out_dir must be outside this repository. Each question line is
`{"id": str, "question": str, "expected": [Vault-relative document paths]}`.
Each system runs as a subprocess three times per question, so times include process start.
A question hits when any top-5 result path is in `expected`. A run that exits non-zero,
times out, or prints unreadable output makes the question "failed" for that system,
which is counted apart from misses. Per-question results go to `out_dir/results.jsonl`,
and `out_dir/summary.json` holds totals only, without question text.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TOP_K = 5
RUNS_PER_QUESTION = 3
RUN_TIMEOUT_SECONDS = 300.0
REPO_ROOT = Path(__file__).resolve().parents[2]
VAULT_NO_HITS = "No matching wiki pages."
_VAULT_HIT_LINE = re.compile(r"^- (?P<path>.+) \[[^\]]*\] score=-?\d+$")

System = Literal["vault", "vg"]
Outcome = Literal["hit", "miss", "failed"]


@dataclass(frozen=True)
class Question:
    question_id: str
    text: str
    expected: frozenset[str]


@dataclass(frozen=True)
class SystemResult:
    outcome: Outcome
    paths: tuple[str, ...]
    seconds: tuple[float, ...]
    error: str | None

    def to_json(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "paths": list(self.paths),
            "seconds": list(self.seconds),
            "first_seconds": self.seconds[0],
            "median_seconds": statistics.median(self.seconds),
            "error": self.error,
        }


def main(questions: Path, vault: Path, graph_home: Path, out_dir: Path) -> None:
    _require_outside_repository(questions, "questions")
    _require_outside_repository(out_dir, "out_dir")
    loaded = _load_questions(questions)
    commit = _repository_commit()
    rows: list[dict[str, object]] = []
    totals: dict[System, list[SystemResult]] = {"vault": [], "vg": []}
    for question in loaded:
        row: dict[str, object] = {"id": question.question_id}
        for system in ("vault", "vg"):
            result = _measure(system, question, vault=vault, graph_home=graph_home)
            totals[system].append(result)
            row[system] = result.to_json()
        rows.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    summary = {
        "question_count": len(loaded),
        "top_k": TOP_K,
        "runs_per_question": RUNS_PER_QUESTION,
        "commit": commit,
        "systems": {system: _system_summary(results, len(loaded)) for system, results in totals.items()},
        "judgment_blocked": any(result.outcome == "failed" for results in totals.values() for result in results),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_vault_hits(stdout: str) -> list[str]:
    """Read result paths from the text that Vault `render_hits` prints."""
    text = stdout.strip()
    if text == VAULT_NO_HITS:
        return []
    paths = [match["path"] for line in text.splitlines() if (match := _VAULT_HIT_LINE.match(line))]
    if not paths:
        raise ValueError("unrecognized Vault search output")
    return paths[:TOP_K]


def parse_vg_hits(stdout: str) -> list[str]:
    """Read the document path of each result from `vg search --format json`."""
    try:
        payload = json.loads(stdout)
        results = payload["results"]
        paths = [_normalize(str(result["evidence"][0]["path"])) for result in results]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise ValueError(f"unrecognized vg search output: {error}") from error
    return paths[:TOP_K]


def _measure(system: System, question: Question, *, vault: Path, graph_home: Path) -> SystemResult:
    if system == "vault":
        argv = [sys.executable, "-I", "-B", "tools/wiki/cli.py", "search", question.text, "--limit", str(TOP_K)]
        cwd: Path | None = vault
        parse = parse_vault_hits
    else:
        argv = [
            "vg",
            "search",
            question.text,
            "--graph-home",
            str(graph_home),
            "--limit",
            str(TOP_K),
            "--format",
            "json",
        ]
        cwd = None
        parse = parse_vg_hits
    seconds: list[float] = []
    first_paths: list[str] | None = None
    error: str | None = None
    for _ in range(RUNS_PER_QUESTION):
        started = time.perf_counter()
        try:
            completed = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            seconds.append(time.perf_counter() - started)
            error = error or f"{type(exc).__name__}: {exc}"
            continue
        seconds.append(time.perf_counter() - started)
        if completed.returncode != 0:
            error = error or f"exit {completed.returncode}: {completed.stderr.strip()[-500:]}"
            continue
        try:
            paths = parse(completed.stdout)
        except ValueError as exc:
            error = error or str(exc)
            continue
        if first_paths is None:
            first_paths = paths
    if error is not None or first_paths is None:
        return SystemResult("failed", tuple(first_paths or ()), tuple(seconds), error or "no successful run")
    outcome: Outcome = "hit" if question.expected.intersection(first_paths) else "miss"
    return SystemResult(outcome, tuple(first_paths), tuple(seconds), None)


def _system_summary(results: list[SystemResult], question_count: int) -> dict[str, object]:
    hits = sum(result.outcome == "hit" for result in results)
    return {
        "hits": hits,
        "misses": sum(result.outcome == "miss" for result in results),
        "failures": sum(result.outcome == "failed" for result in results),
        "hit_rate": hits / question_count if question_count else 0.0,
        "first_seconds_median": _median([result.seconds[0] for result in results]),
        "median_seconds_median": _median([statistics.median(result.seconds) for result in results]),
    }


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _load_questions(path: Path) -> list[Question]:
    questions: list[Question] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as error:
            raise ValueError(f"questions line {number}: not JSON") from error
        question_id, text, expected = (row.get(key) for key in ("id", "question", "expected"))
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"questions line {number}: id must be a non-empty string")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"questions line {number}: question must be a non-empty string")
        if not isinstance(expected, list) or not expected or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"questions line {number}: expected must be a non-empty list of paths")
        if question_id in seen:
            raise ValueError(f"questions line {number}: duplicate id {question_id!r}")
        seen.add(question_id)
        questions.append(Question(question_id, text, frozenset(_normalize(item) for item in expected)))
    if not questions:
        raise ValueError("questions file has no questions")
    return questions


def _normalize(path: str) -> str:
    return path.removeprefix("./")


def _require_outside_repository(path: Path, name: str) -> None:
    if path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError(f"{name} must be outside the repository so question text is never committed")


def _repository_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--graph-home", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    arguments = parser.parse_args()
    main(arguments.questions, arguments.vault, arguments.graph_home, arguments.out_dir)
