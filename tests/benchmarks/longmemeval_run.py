"""LongMemEval-S retrieval step: does `vg search --mode evidence` put every answer session in the top 5?

Spec 2026-11-11 §4.1.4, A-6, 결정10. Run from the repository root:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.longmemeval_run \
    --data <longmemeval_s_cleaned.json> --vault-builder <vault-builder checkout> \
    --work-dir <new empty folder> --out-dir <out dir> [--limit N] [--keep] [--reranker <preset>] [--date-rules] \
    [--types <type,...>] [--ids <id,...>] [--facts claude|llama-server --facts-cache <shared folder>]

Run measurement commands with ``TZ=UTC`` in front (spec 2026-11-16 R4): LongMemEval dates have no time zone and
the converter writes them as UTC, while vg compares date ranges on this computer's calendar.

For each non-abstention question (fixed order, see ``longmemeval_convert.select_questions``):

1. A new workspace under ``work_dir`` gets its own HOME, ``vault-map.json``, a project folder and a
   Vault installed and linked as the project's role project Vault by vault-builder's
   ``tools/vault_migration/cli.py``. ``vg setup --no-index`` registers it in a new Graph Home. With
   ``--reranker <preset>`` that Graph Home also gets ``configs/reranker.json`` turning reranking on with the
   preset (spec 2026-11-13 D15). Without it no such file is written and search runs as before.
   Every Graph Home also gets ``configs/facts.json`` (spec 2026-11-16 D19, A25). Without ``--facts`` it says
   ``enabled: false``, so a run never calls ``claude`` or ``llama-server``. ``--facts <extractor>`` with
   ``--facts-cache <folder>`` is the B measurement: the file turns facts on with that extractor.
2. Each haystack session becomes one ``vg-session-jsonl/1`` file outside the Vault, and the Vault's own
   ``tools/wiki/cli.py sessions capture --normalized <file>`` writes it into the Vault. vault-graph
   never writes Vault files. In the B measurement the runner then queues one fact job per captured part and runs
   ``vg facts worker --graph-home <workspace> --cache-dir <facts cache>`` in the foreground, so the Vault's own
   ``sessions attach-facts`` writes the attachments before indexing. All questions share the cache folder
   (D20), so an exchange already extracted is not sent again. ``results.jsonl`` records ``facts`` per question:
   ``cache_misses`` (new cache entries, the exchanges the extractor was given) and ``attachments_written``.
   ``summary.json`` records the extractor and both totals. A question whose worker leaves a job in the queue
   or ends a job other than ``written``, ``exists`` or ``no_facts`` is recorded as an error.
3. ``vg index --all-vaults`` builds keyword and vector indexes. ``vg search --mode evidence --limit 5``
   runs with the question text. With ``--date-rules`` (spec 2026-11-16 D15) the runner acts as an agent that
   fills in the date range: ``question_date_range`` picks one date expression of research X15 out of the
   question with fixed patterns and resolves it with ``resolve_date_expression(expression, question date)``.
   Only a question that resolves gets ``--since``/``--until``, and its search runs with ``TZ=UTC`` (R4).
   Other questions search as without the option. vg itself never reads a range out of the query (D13);
   this picking lives only in this measurement tool. ``results.jsonl`` then records ``date_range`` per
   question and ``summary.json`` records ``date_rules`` and ``date_range_questions_by_type``. Without
   ``--date-rules`` the commands and output are as before.
4. The question counts as found when the sessions of the top 5 results hold every
   ``answer_session_ids`` entry (recall_all@5); recall_any@5 is recorded too. This is stricter than
   LongMemEval's own session-level recall: several exchanges of one session take several of the 5 places.
   ``distinct_sessions_at_5`` records how many different haystack sessions the top 5 hold (spec 2026-11-16 D7),
   per question in ``results.jsonl``, and ``summary.json`` gives its mean overall and in
   ``distinct_sessions_at_5_by_type``.

Each step is timed. ``summary.json`` gives seconds per question, the estimated hours for all 470 questions
and the scope 결정10 picks: all 470 when they fit in two hours, else the fixed sample of 150.

``--types`` and ``--ids`` (comma lists) restrict the run for the B pilot (spec 2026-11-16 D23): ``--types`` keeps
questions of those types within the fixed sample of 150, ``--ids`` keeps those question ids, and ``--limit`` then
takes the first N that are left. ``--types multi-session,temporal-reasoning --limit 20`` is the pilot.

``work_dir`` must be new or empty, outside this repository and the default Graph Home, and must not be,
hold or sit inside a Vault in the person's ``vault-map.json`` or default Graph Home catalog. Each
workspace is removed after its question unless ``--keep`` is given. Rows in ``results.jsonl`` hold no
question text. Read the downloaded data file as JSON only; it is untrusted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Protocol, cast

from tests.benchmarks.longmemeval_convert import (
    PROJECT,
    LmeQuestion,
    load_questions,
    select_questions,
    write_question_sessions,
)
from vault_graph.interface.composition.adapters.fact_queue import enqueue_fact_job, list_fact_jobs
from vault_graph.interface.composition.adapters.rerank_presets import RERANK_PRESETS
from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.facts_settings import (
    FACT_EXTRACTORS,
    default_facts_settings,
    facts_settings_path,
    save_facts_settings,
)
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME
from vault_graph.operation.scope.reranker_selection import (
    RerankerSelection,
    reranker_config_path,
    save_reranker_selection,
)
from vault_graph.retrieval.search.date_expression import (
    DateArgumentError,
    DateRange,
    resolve_date_expression,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TOP = 5
FULL_QUESTIONS = 470
SAMPLE_QUESTIONS = 150
TIME_BUDGET_SECONDS = 2 * 3600
VAULT_NAME = "lme"
STEP_TIMEOUT_SECONDS = 1800.0
STEPS = ("prepare", "convert", "capture", "index", "search")
FACTS_STEP = "facts"
_FACT_JOB_DONE = frozenset({"written", "exists", "no_facts"})
_SESSION_FILE = re.compile(r"(?:^|/)raw/sessions/[^/]+/\d{4}-\d{2}-\d{2}-(?P<id>[0-9a-f-]{36})-part\d+\.md$")
_VG = (sys.executable, "-c", "from vault_graph.interface.cli.main import app; app()")


class StepError(RuntimeError):
    """One step of one question failed. The question is recorded as an error and the run goes on."""


@dataclass(frozen=True)
class Workspace:
    root: Path

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def config_dir(self) -> Path:
        return self.home / ".claude"

    @property
    def vault_map(self) -> Path:
        return self.config_dir / "vault-builder" / "vault-map.json"

    @property
    def vault(self) -> Path:
        return self.root / "vault"

    @property
    def project(self) -> Path:
        return self.root / "project"

    @property
    def graph_home(self) -> Path:
        return self.root / "graph-home"

    @property
    def normalized(self) -> Path:
        return self.root / "normalized"


class Tools(Protocol):
    def prepare(self, workspace: Workspace) -> None: ...

    def capture(self, workspace: Workspace, normalized: Path) -> str: ...

    def index(self, workspace: Workspace) -> None: ...

    def search(self, workspace: Workspace, query: str) -> list[list[str]]:
        """Search the question. With ``--date-rules`` and a range, the runner adds ``date_range=<DateRange>``."""
        ...


class FactTools(Tools, Protocol):
    def extract_facts(self, workspace: Workspace) -> FactCounts:
        """B measurement only: run the fact worker on the jobs queued by ``capture``."""
        ...


@dataclass(frozen=True)
class FactCounts:
    """What one question's fact worker run did (spec 2026-11-16 D20, D23)."""

    cache_misses: int
    """New entries in the shared cache: the exchanges the extractor was given."""
    attachments_written: int

    def to_json(self) -> dict[str, int]:
        return {"cache_misses": self.cache_misses, "attachments_written": self.attachments_written}


@dataclass(frozen=True)
class TopScore:
    top5_sessions: tuple[str, ...]
    all_in_top5: bool
    any_in_top5: bool

    @property
    def distinct_sessions(self) -> int:
        """Different haystack sessions in the top 5 results (spec 2026-11-16 D7)."""
        return len(self.top5_sessions)


@dataclass(frozen=True)
class QuestionRun:
    question_id: str
    question_type: str
    answer_session_ids: tuple[str, ...]
    score: TopScore | None
    seconds: dict[str, float] = field(default_factory=dict)
    error: str | None = None
    date_rules: bool = False
    date_range: DateRange | None = None
    facts: bool = False
    fact_counts: FactCounts | None = None

    def to_json(self) -> dict[str, object]:
        row: dict[str, object] = {
            "id": self.question_id,
            "type": self.question_type,
            "answer_session_ids": list(self.answer_session_ids),
            "top5_sessions": list(self.score.top5_sessions) if self.score else None,
            "all_in_top5": self.score.all_in_top5 if self.score else None,
            "any_in_top5": self.score.any_in_top5 if self.score else None,
            "distinct_sessions_at_5": self.score.distinct_sessions if self.score else None,
            "seconds": {name: round(value, 3) for name, value in self.seconds.items()},
            "error": self.error,
        }
        if self.date_rules:
            row["date_range"] = (
                None
                if self.date_range is None
                else {"since": _iso(self.date_range.since), "until": _iso(self.date_range.until)}
            )
        if self.facts:
            row["facts"] = None if self.fact_counts is None else self.fact_counts.to_json()
        return row


def _iso(day: date | None) -> str | None:
    return None if day is None else day.isoformat()


# Scoring --------------------------------------------------------------------------------------------


def result_paths(payload: object) -> list[list[str]]:
    """Evidence paths of each result of `vg search --format json`, in rank order."""
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("vg search output has no results list")
    return [[str(item.get("path", "")) for item in result.get("evidence", [])] for result in payload["results"]]


def score_top5(answers: Sequence[str], ranked: Sequence[Sequence[str]], haystack_ids: Mapping[str, str]) -> TopScore:
    """Haystack sessions of the top 5 results, and whether they hold all or any answer session."""
    sessions: dict[str, None] = {}
    for paths in ranked[:TOP]:
        for path in paths:
            match = _SESSION_FILE.search(path)
            if match is not None and match["id"] in haystack_ids:
                sessions.setdefault(haystack_ids[match["id"]], None)
    found = set(sessions)
    return TopScore(
        top5_sessions=tuple(sessions),
        all_in_top5=bool(answers) and all(answer in found for answer in answers),
        any_in_top5=any(answer in found for answer in answers),
    )


def scope_for(mean_seconds: float) -> str:
    """결정10: all 470 questions when they fit in two hours, else the fixed sample of 150."""
    return (
        f"full-{FULL_QUESTIONS}"
        if mean_seconds * FULL_QUESTIONS <= TIME_BUDGET_SECONDS
        else f"sample-{SAMPLE_QUESTIONS}"
    )


# Date rules -----------------------------------------------------------------------------------------

# The expression forms of spec 2026-11-16 research X15, longest form first at each position. The runner only
# picks the span; ``resolve_date_expression`` decides the range. Month names must be whole words after "in" or
# "during", or be followed by a day, so "May I ..." is not a month.
_MONTH_WORDS = r"(?:january|february|march|april|may|june|july|august|september|october|november|december)"
_WEEKDAY_WORDS = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_COUNT_WORDS = r"(?:\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_DATE_FORMS = "|".join(
    (
        rf"(?:the )?{_WEEKDAY_WORDS} {_COUNT_WORDS} (?:week|month)s? ago",
        r"(?:a couple of|a few|couple of|few) days ago",
        rf"{_COUNT_WORDS} (?:day|week|month)s? ago",
        rf"last (?:{_WEEKDAY_WORDS}|week|month)",
        rf"(?:in|during|over|within) the (?:past|last) (?:{_COUNT_WORDS} )?(?:day|week|month)s?",
        rf"(?:in|during) {_MONTH_WORDS} and {_MONTH_WORDS}",
        rf"(?:in|during) {_MONTH_WORDS}(?:,? \d{{4}})?",
        rf"{_MONTH_WORDS} \d{{1,2}}(?:st|nd|rd|th)?(?:,? \d{{4}})?",
    )
)
_DATE_EXPRESSION = re.compile(rf"\b(?:{_DATE_FORMS})\b")


def question_date_range(question: str, asked_on: date) -> DateRange | None:
    """The range of the first date expression in ``question`` that resolves from ``asked_on``, else None.

    This emulates an agent that turns "two weeks ago" into dates before it searches (spec 2026-11-16 D15). It
    belongs to this measurement tool only: vg does not read ranges out of query text (D13).
    """
    text = " ".join(question.lower().split())
    for match in _DATE_EXPRESSION.finditer(text):
        try:
            return resolve_date_expression(match.group(0), asked_on)
        except DateArgumentError:
            continue
    return None


# Target folder refusal ------------------------------------------------------------------------------


def registered_vault_roots(
    *, vault_map: Path | None = None, default_graph_home: Path = DEFAULT_GRAPH_HOME
) -> list[Path]:
    """Vault roots in the person's vault-map.json and default Graph Home catalog. Raises when unreadable."""
    roots: list[Path] = []
    opening = open_vault_map(vault_map or vault_map_path())
    if opening.state == "invalid":
        raise ValueError(f"cannot check registered Vaults: {opening.warning}")
    if opening.vault_map is not None:
        roots.extend(vault.path for vault in opening.vault_map.vaults)
    if (default_graph_home / "configs" / "vaults.yaml").exists():
        catalog = CatalogService(graph_home_path=default_graph_home).load_catalog()
        roots.extend(entry.root_path for entry in catalog.entries())
    return [_resolve(root) for root in roots]


def check_work_dir(work_dir: Path, *, registered: Iterable[Path], default_graph_home: Path) -> None:
    """Refuse a work folder that overlaps a registered Vault, the default Graph Home or this repository."""
    target = _resolve(work_dir)
    for root in registered:
        vault = _resolve(root)
        if _overlaps(target, vault):
            raise ValueError(f"work_dir {work_dir} overlaps registered Vault {root}; use a new temporary folder")
    if _overlaps(target, _resolve(default_graph_home)):
        raise ValueError(f"work_dir {work_dir} overlaps the default Graph Home; use a new temporary folder")
    if _overlaps(target, REPO_ROOT):
        raise ValueError(f"work_dir {work_dir} overlaps this repository; use a new temporary folder")
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError(f"work_dir {work_dir} must be new or empty")


def _overlaps(first: Path, second: Path) -> bool:
    return first.is_relative_to(second) or second.is_relative_to(first)


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve()


# Running --------------------------------------------------------------------------------------------


def run_question(
    question: LmeQuestion,
    *,
    workspace: Workspace,
    tools: Tools,
    clock: Callable[[], float] = time.perf_counter,
    date_rules: bool = False,
    facts: bool = False,
) -> QuestionRun:
    seconds: dict[str, float] = {}
    started = clock()
    step_started = started

    def lap(name: str) -> None:
        nonlocal step_started
        now = clock()
        seconds[name] = now - step_started
        step_started = now

    score: TopScore | None = None
    error: str | None = None
    fact_counts: FactCounts | None = None
    date_range = question_date_range(question.question, question.asked_on) if date_rules else None
    try:
        tools.prepare(workspace)
        lap("prepare")
        written = write_question_sessions(question, workspace.normalized, cwd=str(workspace.project))
        lap("convert")
        for path in written.files:
            tools.capture(workspace, path)
        lap("capture")
        if facts:
            fact_counts = cast(FactTools, tools).extract_facts(workspace)
            lap(FACTS_STEP)
        tools.index(workspace)
        lap("index")
        if date_range is None:
            ranked = tools.search(workspace, question.question)
        else:
            ranked = tools.search(workspace, question.question, date_range=date_range)  # type: ignore[call-arg]
        lap("search")
        score = score_top5(question.answer_session_ids, ranked, written.haystack_ids)
    except (StepError, ValueError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc)[:300]
    seconds["total"] = clock() - started
    for name in (*STEPS, FACTS_STEP) if facts else STEPS:
        seconds.setdefault(name, 0.0)
    return QuestionRun(
        question.question_id,
        question.question_type,
        question.answer_session_ids,
        score,
        seconds,
        error,
        date_rules=date_rules,
        date_range=date_range,
        facts=facts,
        fact_counts=fact_counts,
    )


def main(
    data: Path,
    *,
    work_dir: Path,
    out_dir: Path,
    tools: Tools,
    limit: int | None = None,
    keep: bool = False,
    registered: Iterable[Path] | None = None,
    default_graph_home: Path = DEFAULT_GRAPH_HOME,
    clock: Callable[[], float] = time.perf_counter,
    date_rules: bool = False,
    facts: str | None = None,
    types: Sequence[str] | None = None,
    ids: Sequence[str] | None = None,
) -> dict[str, object]:
    """Run the questions. ``facts`` names the extractor of a B measurement; the tools must turn it on too."""
    roots = (
        list(registered) if registered is not None else registered_vault_roots(default_graph_home=default_graph_home)
    )
    check_work_dir(work_dir, registered=roots, default_graph_home=default_graph_home)
    questions = pick_questions(load_questions(data), limit=limit, types=types, ids=ids)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs: list[QuestionRun] = []
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as stream:
        for number, question in enumerate(questions, start=1):
            workspace = Workspace(work_dir / f"q{number:04d}")
            try:
                result = run_question(
                    question,
                    workspace=workspace,
                    tools=tools,
                    clock=clock,
                    date_rules=date_rules,
                    facts=facts is not None,
                )
            finally:
                if not keep:
                    shutil.rmtree(workspace.root, ignore_errors=True)
            runs.append(result)
            stream.write(json.dumps(result.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
    summary = summarize(runs)
    if date_rules:
        summary.update(
            date_rules=True,
            date_range_questions_by_type={
                name: sum(1 for run in runs if run.question_type == name and run.date_range is not None)
                for name in sorted({run.question_type for run in runs})
            },
        )
    if facts is not None:
        counted = [run.fact_counts for run in runs if run.fact_counts is not None]
        summary["facts"] = {
            "extractor": facts,
            "cache_misses": sum(counts.cache_misses for counts in counted),
            "attachments_written": sum(counts.attachments_written for counts in counted),
        }
        steps = summary["seconds_by_step_mean"]
        scored = [run for run in runs if run.score is not None]
        if isinstance(steps, dict):
            steps[FACTS_STEP] = (
                round(statistics.fmean(run.seconds.get(FACTS_STEP, 0.0) for run in scored), 3) if scored else 0.0
            )
    if types is not None:
        summary["types"] = list(types)
    if ids is not None:
        summary["ids"] = list(ids)
    summary.update(data_file=data.name, data_sha256=_sha256(data), limit=limit, commit=_repository_commit())
    (out_dir / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def pick_questions(
    questions: Sequence[LmeQuestion],
    *,
    limit: int | None = None,
    types: Sequence[str] | None = None,
    ids: Sequence[str] | None = None,
) -> tuple[LmeQuestion, ...]:
    """Questions of the run in the fixed order (spec 2026-11-16 D23).

    Without ``types`` and ``ids`` this is ``select_questions(limit=limit)``. ``types`` keeps the questions of those
    types within the fixed sample of 150, ``ids`` keeps those ids, and ``limit`` takes the first N that are left.
    """
    if types is None and ids is None:
        return select_questions(questions, limit=limit)
    pool = select_questions(questions, limit=SAMPLE_QUESTIONS if types is not None else None)
    kept = [
        question
        for question in pool
        if (types is None or question.question_type in types) and (ids is None or question.question_id in ids)
    ]
    return tuple(kept if limit is None else kept[:limit])


def summarize(runs: Sequence[QuestionRun]) -> dict[str, object]:
    scored = [run for run in runs if run.score is not None]

    def rate(rows: Sequence[QuestionRun], key: Callable[[TopScore], bool]) -> float | None:
        values = [key(row.score) for row in rows if row.score is not None]
        return round(sum(values) / len(values), 4) if values else None

    def mean_sessions(rows: Sequence[QuestionRun]) -> float | None:
        values = [row.score.distinct_sessions for row in rows if row.score is not None]
        return round(statistics.fmean(values), 4) if values else None

    by_type: dict[str, dict[str, object]] = {}
    for name in sorted({run.question_type for run in runs}):
        rows = [run for run in runs if run.question_type == name]
        by_type[name] = {
            "questions": len(rows),
            "recall_all_at_5": rate(rows, lambda score: score.all_in_top5),
            "recall_any_at_5": rate(rows, lambda score: score.any_in_top5),
        }
    # A failed question stops early, so only finished questions say how long one question takes.
    totals = [run.seconds["total"] for run in scored]
    mean = statistics.fmean(totals) if totals else 0.0
    return {
        "questions": len(runs),
        "failed": len(runs) - len(scored),
        "recall_all_at_5": rate(runs, lambda score: score.all_in_top5),
        "recall_any_at_5": rate(runs, lambda score: score.any_in_top5),
        "distinct_sessions_at_5": mean_sessions(runs),
        # Kept apart from ``by_type`` so that block reads the same as before the count (spec 2026-11-16 D7).
        "distinct_sessions_at_5_by_type": {
            name: mean_sessions([run for run in runs if run.question_type == name]) for name in by_type
        },
        "by_type": by_type,
        "seconds_per_question": {
            "mean": round(mean, 3),
            "p50": round(statistics.median(totals), 3) if totals else 0.0,
            "max": round(max(totals), 3) if totals else 0.0,
            "total": round(sum(run.seconds["total"] for run in runs), 3),
        },
        "seconds_by_step_mean": {
            name: round(statistics.fmean(run.seconds.get(name, 0.0) for run in scored), 3) if scored else 0.0
            for name in STEPS
        },
        "estimated_hours_470": round(mean * FULL_QUESTIONS / 3600, 2),
        "scope": scope_for(mean),
    }


# Vault tool and vg ----------------------------------------------------------------------------------


def capture_command(vault: Path, normalized: Path) -> list[str]:
    """The Vault's own `sessions capture --normalized`. It picks the Vault from the cwd and vault-map.json."""
    return [
        sys.executable,
        "-B",
        str(vault / "tools" / "wiki" / "cli.py"),
        "sessions",
        "capture",
        "--normalized",
        str(normalized),
        "--json",
    ]


@dataclass(frozen=True)
class LocalTools:
    """Runs vault-builder, the Vault tool and vg as subprocesses inside one workspace.

    ``reranker`` names a rerank preset to turn on in each new Graph Home. ``None`` leaves reranking off.
    ``facts`` names the fact extractor of a B measurement and ``facts_cache`` the cache folder every question
    shares. Both or neither: ``None`` writes ``enabled: false`` in each Graph Home (spec 2026-11-16 D19, A25).
    """

    vault_builder: Path
    reranker: str | None = None
    facts: str | None = None
    facts_cache: Path | None = None

    def __post_init__(self) -> None:
        if self.reranker is not None and self.reranker not in RERANK_PRESETS:
            raise ValueError(f"unknown rerank preset {self.reranker!r}; choose one of {sorted(RERANK_PRESETS)}")
        if (self.facts is None) != (self.facts_cache is None):
            raise ValueError("--facts and --facts-cache go together")
        if self.facts is not None and self.facts not in FACT_EXTRACTORS:
            raise ValueError(f"unknown fact extractor {self.facts!r}; choose one of {list(FACT_EXTRACTORS)}")

    def prepare(self, workspace: Workspace) -> None:
        for folder in (workspace.config_dir, workspace.project):
            folder.mkdir(parents=True)
        _run(
            ["git", "init", "-q", str(workspace.project)],
            label="git init",
            env=self._vault_env(workspace),
            cwd=workspace.root,
        )
        builder = [sys.executable, "-B", str(self.vault_builder / "tools" / "vault_migration" / "cli.py")]
        env = self._vault_env(workspace)
        _run(
            [*builder, "install", str(workspace.vault), "--name", VAULT_NAME, "--role", "project"],
            label="vault install",
            env=env,
        )
        _run(
            [*builder, "link", VAULT_NAME, "--repo", str(workspace.project), "--project", PROJECT],
            label="vault link",
            env=env,
        )
        _run(
            [
                *_VG,
                "setup",
                "--vault",
                str(workspace.vault),
                "--vault-id",
                VAULT_NAME,
                "--graph-home",
                str(workspace.graph_home),
                "--vault-map",
                str(workspace.vault_map),
                "--no-index",
            ],
            label="vg setup",
            env=self._vg_env(workspace),
            cwd=workspace.project,
        )
        if self.reranker is not None:
            save_reranker_selection(
                reranker_config_path(workspace.graph_home), RerankerSelection(enabled=True, model=self.reranker)
            )
        settings = default_facts_settings(self.facts or "claude")
        if self.facts is None:
            settings = replace(settings, enabled=False)
        save_facts_settings(facts_settings_path(workspace.graph_home), settings)

    def capture(self, workspace: Workspace, normalized: Path) -> str:
        completed = _run(
            capture_command(workspace.vault, normalized),
            label="sessions capture",
            env=self._vault_env(workspace),
            cwd=workspace.project,
            check=False,
        )
        status, part = _capture_result(completed.stdout)
        if status != "written":
            raise StepError(f"capture {status} for {normalized.name}: {completed.stderr.strip()[-200:]}")
        if self.facts is not None:
            # The capture hook queues this job after a real capture; here the runner captures, so it queues it.
            if part is None:
                raise StepError(f"capture of {normalized.name} gave no part path")
            enqueue_fact_job(workspace.graph_home, vault_root=workspace.vault.resolve(), vault=VAULT_NAME, part=part)
        return status

    def extract_facts(self, workspace: Workspace) -> FactCounts:
        if self.facts is None or self.facts_cache is None:
            raise StepError("fact extraction is off for this run")
        before = _cache_entries(self.facts_cache)
        completed = _run(
            [
                *_VG,
                "facts",
                "worker",
                "--graph-home",
                str(workspace.graph_home),
                "--cache-dir",
                str(self.facts_cache),
            ],
            label="vg facts worker",
            env=self._vg_env(workspace),
            cwd=workspace.project,
        )
        statuses = _worker_statuses(completed.stdout)
        left = list_fact_jobs(workspace.graph_home)
        unfinished = sorted({status for status in statuses if status not in _FACT_JOB_DONE})
        if left or unfinished:
            raise StepError(
                f"facts worker left {len(left)} jobs, statuses {unfinished}: {completed.stdout.strip()[-300:]}"
            )
        return FactCounts(
            cache_misses=_cache_entries(self.facts_cache) - before,
            attachments_written=statuses.count("written"),
        )

    def index(self, workspace: Workspace) -> None:
        _run(
            [*_VG, "index", "--graph-home", str(workspace.graph_home), "--all-vaults"],
            label="vg index",
            env=self._vg_env(workspace),
            cwd=workspace.project,
        )

    def search(self, workspace: Workspace, query: str, date_range: DateRange | None = None) -> list[list[str]]:
        dates: list[str] = []
        env = self._vg_env(workspace)
        if date_range is not None:
            for option, day in (("--since", date_range.since), ("--until", date_range.until)):
                if day is not None:
                    dates.extend((option, day.isoformat()))
            env["TZ"] = "UTC"  # R4: the converter writes LongMemEval times, which have no zone, as UTC.
        completed = _run(
            [
                *_VG,
                "search",
                "--graph-home",
                str(workspace.graph_home),
                "--format",
                "json",
                "--limit",
                str(TOP),
                "--mode",
                "evidence",
                *dates,
                "--",
                query,
            ],
            label="vg search",
            env=env,
            cwd=workspace.project,
        )
        return result_paths(json.loads(completed.stdout))

    @staticmethod
    def _vault_env(workspace: Workspace) -> dict[str, str]:
        return _env(HOME=str(workspace.home), CLAUDE_CONFIG_DIR=str(workspace.config_dir))

    @staticmethod
    def _vg_env(workspace: Workspace) -> dict[str, str]:
        # HOME stays the person's so vg finds the downloaded embedding model; the map is the workspace's.
        return _env(CLAUDE_CONFIG_DIR=str(workspace.config_dir), VAULT_GRAPH_VAULT_MAP=str(workspace.vault_map))


def _env(**values: str) -> dict[str, str]:
    environ = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "VAULT_GRAPH_VAULT_MAP")}
    environ.update(PYTHONDONTWRITEBYTECODE="1", **values)
    return environ


def _run(
    command: Sequence[str], *, label: str, env: Mapping[str, str], cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        list(command),
        env=dict(env),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=STEP_TIMEOUT_SECONDS,
        check=False,
    )
    if check and completed.returncode != 0:
        raise StepError(f"{label} exited {completed.returncode}: {completed.stderr.strip()[-300:]}")
    return completed


def _capture_status(stdout: str) -> str:
    return _capture_result(stdout)[0]


def _capture_result(stdout: str) -> tuple[str, str | None]:
    """Status and part path (relative to the Vault root) of the last JSON line of ``sessions capture --json``."""
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("status"), str):
            path = payload.get("path")
            return str(payload["status"]), path if isinstance(path, str) and path else None
    return "unknown", None


def _worker_statuses(stdout: str) -> list[str]:
    """Job statuses from ``vg facts worker`` lines ``facts worker: <job> <status>[ <reason>: <message>]``.

    A job held back for its retry time prints ``<job> waiting for its retry time`` and counts as ``waiting``.
    """
    statuses: list[str] = []
    for line in stdout.splitlines():
        if not line.startswith("facts worker: "):
            continue
        words = line.removeprefix("facts worker: ").split(" ")
        if len(words) >= 2 and words[0].endswith(".json"):
            statuses.append(words[1])
    return statuses


def _cache_entries(cache: Path) -> int:
    """Entries in the fact cache folder (``<key[:2]>/<key>.json``). Names starting with ``.`` are being written."""
    if not cache.is_dir():
        return 0
    return sum(1 for entry in cache.glob("*/*.json") if not entry.name.startswith("."))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _repository_commit() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() or "unknown"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="longmemeval_s_cleaned.json")
    parser.add_argument("--vault-builder", type=Path, required=True, help="vault-builder checkout")
    parser.add_argument("--work-dir", type=Path, required=True, help="New or empty temporary folder.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, help="Run the first N questions of the fixed order (20, 150).")
    parser.add_argument("--keep", action="store_true", help="Keep each question's workspace.")
    parser.add_argument(
        "--reranker",
        choices=sorted(RERANK_PRESETS),
        help="Turn reranking on with this preset in each Graph Home. Leave out to keep reranking off.",
    )
    parser.add_argument(
        "--date-rules",
        action="store_true",
        help="Pass --since/--until for questions whose date expression resolves from the question date. "
        "Run with TZ=UTC.",
    )
    parser.add_argument(
        "--types",
        type=_comma_list,
        help="Comma list of question types: keep only those within the fixed sample of 150 (B pilot).",
    )
    parser.add_argument("--ids", type=_comma_list, help="Comma list of question ids to run.")
    parser.add_argument(
        "--facts",
        choices=list(FACT_EXTRACTORS),
        help="B measurement: turn session facts on with this extractor in each Graph Home. Needs --facts-cache.",
    )
    parser.add_argument("--facts-cache", type=Path, help="Fact cache folder every question shares. Goes with --facts.")
    arguments = parser.parse_args(argv)
    if (arguments.facts is None) != (arguments.facts_cache is None):
        parser.error("--facts and --facts-cache go together")
    return arguments


def _comma_list(value: str) -> tuple[str, ...]:
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError("expected a comma list with at least one item")
    return items


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    result = main(
        arguments.data,
        work_dir=arguments.work_dir,
        out_dir=arguments.out_dir,
        tools=LocalTools(
            vault_builder=arguments.vault_builder.expanduser().resolve(),
            reranker=arguments.reranker,
            facts=arguments.facts,
            facts_cache=None if arguments.facts_cache is None else arguments.facts_cache.expanduser().resolve(),
        ),
        limit=arguments.limit,
        keep=arguments.keep,
        date_rules=arguments.date_rules,
        facts=arguments.facts,
        types=arguments.types,
        ids=arguments.ids,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
