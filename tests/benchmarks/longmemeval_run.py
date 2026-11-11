"""LongMemEval-S retrieval step: does `vg search --mode evidence` put every answer session in the top 5?

Spec 2026-11-11 §4.1.4, A-6, 결정10. Run from the repository root:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.longmemeval_run \
    --data <longmemeval_s_cleaned.json> --vault-builder <vault-builder checkout> \
    --work-dir <new empty folder> --out-dir <out dir> [--limit N] [--keep]

For each non-abstention question (fixed order, see ``longmemeval_convert.select_questions``):

1. A new workspace under ``work_dir`` gets its own HOME, ``vault-map.json``, a project folder and a
   Vault installed and linked as the project's role project Vault by vault-builder's
   ``tools/vault_migration/cli.py``. ``vg setup --no-index`` registers it in a new Graph Home.
2. Each haystack session becomes one ``vg-session-jsonl/1`` file outside the Vault, and the Vault's own
   ``tools/wiki/cli.py sessions capture --normalized <file>`` writes it into the Vault. vault-graph
   never writes Vault files.
3. ``vg index --all-vaults`` builds keyword and vector indexes. ``vg search --mode evidence --limit 5``
   runs with the question text.
4. The question counts as found when the sessions of the top 5 results hold every
   ``answer_session_ids`` entry (recall_all@5); recall_any@5 is recorded too. This is stricter than
   LongMemEval's own session-level recall: several exchanges of one session take several of the 5 places.

Each step is timed. ``summary.json`` gives seconds per question, the estimated hours for all 470 questions
and the scope 결정10 picks: all 470 when they fit in two hours, else the fixed sample of 150.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from tests.benchmarks.longmemeval_convert import (
    PROJECT,
    LmeQuestion,
    load_questions,
    select_questions,
    write_question_sessions,
)
from vault_graph.operation.integration.vault_map import open_vault_map, vault_map_path
from vault_graph.operation.scope.catalog_service import CatalogService
from vault_graph.operation.scope.graph_home import DEFAULT_GRAPH_HOME

REPO_ROOT = Path(__file__).resolve().parents[2]
TOP = 5
FULL_QUESTIONS = 470
SAMPLE_QUESTIONS = 150
TIME_BUDGET_SECONDS = 2 * 3600
VAULT_NAME = "lme"
STEP_TIMEOUT_SECONDS = 1800.0
STEPS = ("prepare", "convert", "capture", "index", "search")
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

    def search(self, workspace: Workspace, query: str) -> list[list[str]]: ...


@dataclass(frozen=True)
class TopScore:
    top5_sessions: tuple[str, ...]
    all_in_top5: bool
    any_in_top5: bool


@dataclass(frozen=True)
class QuestionRun:
    question_id: str
    question_type: str
    answer_session_ids: tuple[str, ...]
    score: TopScore | None
    seconds: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.question_id,
            "type": self.question_type,
            "answer_session_ids": list(self.answer_session_ids),
            "top5_sessions": list(self.score.top5_sessions) if self.score else None,
            "all_in_top5": self.score.all_in_top5 if self.score else None,
            "any_in_top5": self.score.any_in_top5 if self.score else None,
            "seconds": {name: round(value, 3) for name, value in self.seconds.items()},
            "error": self.error,
        }


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
    question: LmeQuestion, *, workspace: Workspace, tools: Tools, clock: Callable[[], float] = time.perf_counter
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
    try:
        tools.prepare(workspace)
        lap("prepare")
        written = write_question_sessions(question, workspace.normalized, cwd=str(workspace.project))
        lap("convert")
        for path in written.files:
            tools.capture(workspace, path)
        lap("capture")
        tools.index(workspace)
        lap("index")
        ranked = tools.search(workspace, question.question)
        lap("search")
        score = score_top5(question.answer_session_ids, ranked, written.haystack_ids)
    except (StepError, ValueError, OSError, subprocess.SubprocessError) as exc:
        error = str(exc)[:300]
    seconds["total"] = clock() - started
    for name in STEPS:
        seconds.setdefault(name, 0.0)
    return QuestionRun(question.question_id, question.question_type, question.answer_session_ids, score, seconds, error)


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
) -> dict[str, object]:
    roots = (
        list(registered) if registered is not None else registered_vault_roots(default_graph_home=default_graph_home)
    )
    check_work_dir(work_dir, registered=roots, default_graph_home=default_graph_home)
    questions = select_questions(load_questions(data), limit=limit)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    runs: list[QuestionRun] = []
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as stream:
        for number, question in enumerate(questions, start=1):
            workspace = Workspace(work_dir / f"q{number:04d}")
            try:
                result = run_question(question, workspace=workspace, tools=tools, clock=clock)
            finally:
                if not keep:
                    shutil.rmtree(workspace.root, ignore_errors=True)
            runs.append(result)
            stream.write(json.dumps(result.to_json(), ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
    summary = summarize(runs)
    summary.update(data_file=data.name, data_sha256=_sha256(data), limit=limit, commit=_repository_commit())
    (out_dir / "summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return summary


def summarize(runs: Sequence[QuestionRun]) -> dict[str, object]:
    scored = [run for run in runs if run.score is not None]

    def rate(rows: Sequence[QuestionRun], key: Callable[[TopScore], bool]) -> float | None:
        values = [key(row.score) for row in rows if row.score is not None]
        return round(sum(values) / len(values), 4) if values else None

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
    """Runs vault-builder, the Vault tool and vg as subprocesses inside one workspace."""

    vault_builder: Path

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

    def capture(self, workspace: Workspace, normalized: Path) -> str:
        completed = _run(
            capture_command(workspace.vault, normalized),
            label="sessions capture",
            env=self._vault_env(workspace),
            cwd=workspace.project,
            check=False,
        )
        status = _capture_status(completed.stdout)
        if status != "written":
            raise StepError(f"capture {status} for {normalized.name}: {completed.stderr.strip()[-200:]}")
        return status

    def index(self, workspace: Workspace) -> None:
        _run(
            [*_VG, "index", "--graph-home", str(workspace.graph_home), "--all-vaults"],
            label="vg index",
            env=self._vg_env(workspace),
            cwd=workspace.project,
        )

    def search(self, workspace: Workspace, query: str) -> list[list[str]]:
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
                "--",
                query,
            ],
            label="vg search",
            env=self._vg_env(workspace),
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
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        if isinstance(payload, dict) and isinstance(payload.get("status"), str):
            return str(payload["status"])
    return "unknown"


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
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    result = main(
        arguments.data,
        work_dir=arguments.work_dir,
        out_dir=arguments.out_dir,
        tools=LocalTools(vault_builder=arguments.vault_builder.expanduser().resolve()),
        limit=arguments.limit,
        keep=arguments.keep,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
