"""Memory quality measurement: answer pages in session start recall and `build_context_pack`, metrics 1-6.

Spec 2026-11-05-session-memory-indexing §4.4.10, A-28. Run from the repository root after `vg index`:
  uv run --python 3.12 --all-packages --all-extras python -m tests.benchmarks.measure_memory_recall \
    --questions <questions.jsonl> --graph-home <graph home> --vault-map <vault-map.json> --out-dir <out dir>

The question file and out_dir must be outside this repository: the questions hold personal content.
Each question line is
`{"id": str, "question": str, "cwd": str, "expected_pages": ["<vault>:<path>", ...], "axis": str}`.
`cwd` is the absolute project folder the question is asked in. `<vault>` is the Vault's
`vault-map.json` name or its Graph Home Vault id, `<path>` the Vault-relative page path
(`main:wiki/decisions/use-sqlite.md`). `axis` is one of 정보 추출, 여러 세션 추론, 시간 추론,
지식 갱신, 답하지 않기, 프로젝트 섞임, 대체된 결정 사용. Only 답하지 않기 may have no expected page;
such a question is counted but not scored.

Scoring is deterministic and uses no language model:

- Recall: `vg hook session-start` runs as a subprocess once per project folder (recall does not
  depend on the question), with `--refresh-budget 0` so the run changes no index and starts no
  catch-up index, and session id `SESSION_ID`. The page locations of the printed blocks are read,
  except block C (`## 변경 알림`), which reports replaced pages and is not memory injection.
  A question's `recall_found` is the number of its expected pages among them.
- Context pack: the MCP tool `build_context_pack` runs in a subprocess per question with the
  question as goal and `cwd` as project folder, so the project's Vault scope is the one the MCP
  server picks (`vg context` takes only one `--vault-id`). `context_found` is the number of expected
  pages among the pack evidence, `context_first_rank` the 1-based evidence rank of the first one.

Metrics. 1 and 2 read only the recall output and the index, so they do not depend on the questions:

1. Replaced or retired memory injected: printed pages whose indexed `status` is superseded,
   deprecated or retired, plus `superseded` claim rows of printed pages whose claim text is printed.
   Goal 0.
2. Share of printed pages that come from a Vault whose map `sharable` is false and that do not
   belong to the project by the scope rule (`page_in_project`), over all printed pages. Goal 0.
3. Open ratio from the Graph Home `usage/` log, read before the run: distinct items injected for the
   project, and those with a `fetched` event at or after their first injection. Events of this
   tool's `SESSION_ID` are skipped.
4. `inferred` proposal acceptance: `memory-proposal` items in each linked Vault's review queue
   (`scratch/review/*.md`), read directly from their frontmatter like the recall proposal counter.
   This is what `review list --json` reads, without starting a Vault process per Vault.
   Rate = accepted / (accepted + rejected).
5. Cleanup backlog age: days since `started_at` of the waiting session exchange candidates of
   `memory_candidate_package` (L1 notes have no start time).
6. Merge candidates of `memory_candidate_package`. 5 and 6 come from one in-process call without
   comparison material, so nothing is searched or written. Merge embeds the current pages with the
   configured local model only when it is already downloaded; otherwise the count is 0 with a warning.

Metrics 3-6 are recorded only. `gate_passed` is true when metrics 1 and 2 are 0 and every project
recall ran. Per-question rows go to `out_dir/results.jsonl`, per-project counts to
`out_dir/projects.jsonl`, and `out_dir/summary.json` holds totals only. None holds question text
or recall text.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

RUN_TIMEOUT_SECONDS = 300.0
REPO_ROOT = Path(__file__).resolve().parents[2]
SESSION_ID = "measure-memory-recall"
AXES = ("정보 추출", "여러 세션 추론", "시간 추론", "지식 갱신", "답하지 않기", "프로젝트 섞임", "대체된 결정 사용")
NO_ANSWER_AXIS = "답하지 않기"
STALE_PAGE_STATUSES = frozenset({"superseded", "deprecated", "retired"})
NOTICE_BLOCK_TITLE = "## 변경 알림"
PROPOSAL_STATUSES = ("accepted", "rejected", "pending", "resolved")
VAULT_MAP_ENV = "VAULT_GRAPH_VAULT_MAP"
_PAGE_REF = re.compile(r"^(?P<vault>[^\s:]+):(?P<path>\S.*)$")
_LOCATION = re.compile(r"\((?:(?P<vault>[^\s:()]+):)?(?P<path>wiki/[^()]*?\.md)(?:, [^()]*)?\)\s*$")
_VG = "from vault_graph.interface.cli.main import app; app()"
_CONTEXT_PACK = """
import json, sys
from pathlib import Path
from vault_graph.interface.mcp.mcp_server import McpServerConfig, create_mcp_server
from vault_graph.interface.mcp.mcp_tools import BuildContextPackInput
server = create_mcp_server(McpServerConfig(graph_home_path=Path(sys.argv[1])))
body = server.tool_registry.build_context_pack(BuildContextPackInput(goal=sys.argv[2], cwd=sys.argv[3]))
sys.stdout.write(json.dumps(body.to_json_dict(), ensure_ascii=False))
"""

PageKey = tuple[str, str]  # (Graph Home Vault id, Vault-relative path)
Resolver = Callable[[str | None], str | None]


@dataclass(frozen=True)
class PageRef:
    vault: str
    path: str


@dataclass(frozen=True)
class Question:
    question_id: str
    text: str
    cwd: Path
    expected: tuple[PageRef, ...]
    axis: str


@dataclass(frozen=True)
class PageFacts:
    """What metrics 1 and 2 need of one printed page, read from the index and the map."""

    status: str | None
    in_project: bool
    sharable: bool
    superseded_claims: tuple[str, ...]


@dataclass(frozen=True)
class InjectionScore:
    pages: int
    unresolved: int
    stale_pages: int
    superseded_claims: int
    unsharable_other: int

    @property
    def metric1(self) -> int:
        return self.stale_pages + self.superseded_claims

    @property
    def metric2(self) -> float | None:
        return round(self.unsharable_other / self.pages, 4) if self.pages else None

    def to_json(self) -> dict[str, object]:
        return {
            "pages": self.pages,
            "unresolved": self.unresolved,
            "stale_pages": self.stale_pages,
            "superseded_claims": self.superseded_claims,
            "unsharable_other": self.unsharable_other,
        }


@dataclass(frozen=True)
class QuestionScore:
    question_id: str
    axis: str
    project: str | None
    expected: int
    recall_found: int | None
    context_found: int | None
    context_first_rank: int | None
    seconds: float
    error: str | None

    @property
    def scored(self) -> bool:
        return self.error is None and self.expected > 0

    def to_json(self) -> dict[str, object]:
        return {
            "id": self.question_id,
            "axis": self.axis,
            "project": self.project,
            "expected": self.expected,
            "recall_found": self.recall_found,
            "context_found": self.context_found,
            "context_first_rank": self.context_first_rank,
            "seconds": round(self.seconds, 3),
            "error": self.error,
        }


@dataclass(frozen=True)
class ProjectReport:
    project: str
    error: str | None
    injection: InjectionScore | None
    usage: Mapping[str, object]
    backlog_ages: tuple[float, ...]
    merge_candidates: int
    warnings: tuple[str, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "project": self.project,
            "error": self.error,
            "injection": self.injection.to_json() if self.injection is not None else None,
            "metric1": self.injection.metric1 if self.injection is not None else None,
            "metric2": self.injection.metric2 if self.injection is not None else None,
            "metric3": dict(self.usage),
            "metric5": backlog_age(self.backlog_ages),
            "metric6": self.merge_candidates,
            "warnings": len(self.warnings),
        }


# Parsing ---------------------------------------------------------------------------------------


def parse_page_ref(text: str) -> PageRef:
    match = _PAGE_REF.match(text)
    if match is None or match["path"] != match["path"].strip():
        raise ValueError(f"expected page must look like '<vault>:<path>': {text!r}")
    return PageRef(match["vault"], match["path"])


def load_questions(path: Path) -> tuple[Question, ...]:
    questions: list[Question] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {number}: a question must be a JSON object")
        question_id, text, cwd, axis = row.get("id"), row.get("question"), row.get("cwd"), row.get("axis")
        expected = row.get("expected_pages")
        if not isinstance(question_id, str) or not question_id or not isinstance(text, str) or not text.strip():
            raise ValueError(f"line {number}: id and question must be non-empty strings")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError(f"line {number}: cwd must be an absolute project folder")
        if axis not in AXES:
            raise ValueError(f"line {number}: axis must be one of {', '.join(AXES)}")
        if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
            raise ValueError(f"line {number}: expected_pages must be a list of '<vault>:<path>'")
        if not expected and axis != NO_ANSWER_AXIS:
            raise ValueError(f"line {number}: only {NO_ANSWER_AXIS} may have no expected page")
        if question_id in seen:
            raise ValueError(f"line {number}: duplicate id {question_id!r}")
        seen.add(question_id)
        refs = tuple(parse_page_ref(item) for item in expected)
        questions.append(Question(question_id, text, Path(cwd), refs, str(axis)))
    return tuple(questions)


def injected_text(recall_text: str) -> str:
    """Recall text without block C, the change notices of replaced pages."""
    kept: list[str] = []
    skipping = False
    for line in recall_text.splitlines():
        if line.startswith("## "):
            skipping = line == NOTICE_BLOCK_TITLE
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def recall_locations(recall_text: str) -> tuple[tuple[str | None, str], ...]:
    """Distinct page locations of the injected blocks: (Vault label or None, path), in print order.

    A label is the map name or Vault id recall prints before the path when several Vaults are linked.
    """
    found: dict[tuple[str | None, str], None] = {}
    for line in injected_text(recall_text).splitlines():
        match = _LOCATION.search(line)
        if match is not None:
            found.setdefault((match["vault"], match["path"]), None)
    return tuple(found)


def context_pages(body: Mapping[str, object]) -> tuple[PageKey, ...]:
    """Distinct (Vault id, path) of `build_context_pack` evidence, in evidence order."""
    payload = body.get("payload")
    evidence = payload.get("evidence") if isinstance(payload, dict) else None
    if not isinstance(evidence, list):
        raise ValueError("build_context_pack returned no evidence list")
    found: dict[PageKey, None] = {}
    for item in evidence:
        ref = item.get("ref") if isinstance(item, dict) else None
        if isinstance(ref, dict) and isinstance(item, dict):
            found.setdefault((str(ref.get("vault_id", "")), str(item.get("path", ""))), None)
    return tuple(found)


# Scoring ---------------------------------------------------------------------------------------


def score_injection(
    recall_text: str, *, resolve: Resolver, facts: Callable[[PageKey], PageFacts | None]
) -> InjectionScore:
    """Metrics 1 and 2 of one recall output. A location the index does not know counts as unresolved."""
    text = injected_text(recall_text)
    pages = recall_locations(recall_text)
    unresolved = stale = claims = other = 0
    for label, path in pages:
        vault_id = resolve(label)
        page = facts((vault_id, path)) if vault_id is not None else None
        if page is None:
            unresolved += 1
            continue
        stale += page.status in STALE_PAGE_STATUSES
        claims += sum(1 for claim in page.superseded_claims if claim and claim in text)
        other += not page.sharable and not page.in_project
    return InjectionScore(len(pages), unresolved, stale, claims, other)


def resolve_expected(expected: Sequence[PageRef], *, resolve: Resolver) -> tuple[PageKey, ...]:
    keys: list[PageKey] = []
    for ref in expected:
        vault_id = resolve(ref.vault)
        if vault_id is None:
            raise ValueError(f"unknown Vault {ref.vault!r} for this project")
        keys.append((vault_id, ref.path))
    return tuple(keys)


def first_rank(expected: Sequence[PageKey], pages: Sequence[PageKey]) -> int | None:
    wanted = set(expected)
    return next((rank for rank, page in enumerate(pages, start=1) if page in wanted), None)


def open_ratio(events: Iterable[Mapping[str, object]], *, project_id: str) -> dict[str, object]:
    """Metric 3 for one project: injected items and those opened at or after their first injection."""
    first_injected: dict[str, datetime] = {}
    fetched: dict[str, list[datetime]] = {}
    for event in events:
        at = _moment(event.get("at"))
        item = event.get("item_id")
        if at is None or not isinstance(item, str):
            continue
        if event.get("event") == "injected":
            if event.get("project") == project_id and event.get("session_id") != SESSION_ID:
                first_injected[item] = min(at, first_injected.get(item, at))
        elif event.get("event") == "fetched":
            fetched.setdefault(item, []).append(at)
    opened = sum(1 for item, at in first_injected.items() if any(moment >= at for moment in fetched.get(item, ())))
    injected = len(first_injected)
    ratio = round(opened / injected, 4) if injected else None
    return {"injected_items": injected, "opened_items": opened, "ratio": ratio}


def proposal_counts(vault_root: Path) -> dict[str, int]:
    """Metric 4 for one Vault: `memory-proposal` review items by status."""
    from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

    counts = dict.fromkeys(PROPOSAL_STATUSES, 0)
    queue = vault_root / "scratch" / "review"
    if not queue.is_dir():
        return counts
    for item in sorted(queue.glob("*.md")):
        block = split_frontmatter(item.read_text(encoding="utf-8", errors="replace"))
        if block is None:
            continue
        fields = parse_vault_frontmatter(block[0])
        status = fields.get("status")
        if fields.get("type") == "memory-proposal" and isinstance(status, str) and status in counts:
            counts[status] += 1
    return counts


def acceptance_rate(per_vault: Iterable[Mapping[str, int]]) -> dict[str, object]:
    totals = dict.fromkeys(PROPOSAL_STATUSES, 0)
    for counts in per_vault:
        for status in PROPOSAL_STATUSES:
            totals[status] += counts.get(status, 0)
    decided = totals["accepted"] + totals["rejected"]
    return {**totals, "rate": round(totals["accepted"] / decided, 4) if decided else None}


def backlog_ages(started: Iterable[datetime | None], *, now: datetime) -> tuple[float, ...]:
    return tuple(round((now - at).total_seconds() / 86400, 1) for at in started if at is not None)


def backlog_age(ages: Sequence[float]) -> dict[str, object]:
    """Metric 5: waiting session exchanges, the oldest and the median age in days."""
    return {
        "exchanges": len(ages),
        "oldest_days": max(ages) if ages else None,
        "median_days": round(statistics.median(ages), 1) if ages else None,
    }


def summarize(
    scores: Sequence[QuestionScore], projects: Sequence[ProjectReport], *, proposals: Iterable[Mapping[str, int]]
) -> dict[str, object]:
    scored = [score for score in scores if score.scored]

    def rate(rows: Sequence[QuestionScore], hit: Callable[[QuestionScore], bool]) -> float | None:
        return round(sum(1 for row in rows if hit(row)) / len(rows), 4) if rows else None

    def recall_hit(row: QuestionScore) -> bool:
        return bool(row.recall_found)

    def context_hit(row: QuestionScore) -> bool:
        return bool(row.context_found)

    by_axis: dict[str, object] = {}
    for axis in AXES:
        rows = [score for score in scores if score.axis == axis and score.error is None]
        if rows:
            axis_scored = [row for row in rows if row.scored]
            by_axis[axis] = {
                "questions": len(rows),
                "recall_hit_rate": rate(axis_scored, recall_hit),
                "context_hit_rate": rate(axis_scored, context_hit),
            }
    injections = [project.injection for project in projects if project.injection is not None]
    pages = sum(injection.pages for injection in injections)
    metric1 = sum(injection.metric1 for injection in injections)
    other = sum(injection.unsharable_other for injection in injections)
    injected = sum(_int(project.usage.get("injected_items")) for project in projects)
    opened = sum(_int(project.usage.get("opened_items")) for project in projects)
    failed_projects = sum(1 for project in projects if project.error is not None)
    metric2 = round(other / pages, 4) if pages else None
    return {
        "questions": len(scores),
        "failed": sum(1 for score in scores if score.error is not None),
        "scored": len(scored),
        "recall_hit_rate": rate(scored, recall_hit),
        "context_hit_rate": rate(scored, context_hit),
        "either_hit_rate": rate(scored, lambda row: recall_hit(row) or context_hit(row)),
        "by_axis": by_axis,
        "projects": len(projects),
        "projects_failed": failed_projects,
        "injected_pages": pages,
        "unresolved_pages": sum(injection.unresolved for injection in injections),
        "metric1_stale_injections": metric1,
        "metric2_unsharable_other_project_share": metric2,
        "metric3_open_ratio": {
            "injected_items": injected,
            "opened_items": opened,
            "ratio": round(opened / injected, 4) if injected else None,
        },
        "metric4_inferred_acceptance": acceptance_rate(proposals),
        "metric5_backlog_age": backlog_age([age for project in projects for age in project.backlog_ages]),
        "metric6_merge_candidates": sum(project.merge_candidates for project in projects),
        "gate_passed": failed_projects == 0 and metric1 == 0 and not metric2,
    }


# Running ---------------------------------------------------------------------------------------


@dataclass
class _ProjectView:
    """The index and map as recall sees them for one project folder. Read only."""

    project_id: str | None
    vault_ids: tuple[str, ...]
    vault_roots: dict[str, Path]
    facts_by_page: dict[PageKey, PageFacts]
    names: dict[str, str] = field(default_factory=dict)

    def resolve(self, label: str | None) -> str | None:
        if label is None:
            return self.vault_ids[0] if len(self.vault_ids) == 1 else None
        if label in self.vault_ids:
            return label
        return next((vault_id for vault_id, name in self.names.items() if name == label), None)

    def facts(self, key: PageKey) -> PageFacts | None:
        return self.facts_by_page.get(key)


def _open_view(graph_home: Path, vault_map: Path, cwd: Path) -> _ProjectView:
    from vault_graph.context.memory.claims import SUPERSEDED_CLAIM_STATUS, read_claim_table
    from vault_graph.context.memory.project_scope import UNMAPPED_VAULT_SCOPE, page_in_project
    from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory
    from vault_graph.operation.scope.catalog_service import CatalogService

    ports = ReadOnlyServiceFactory(graph_home_path=graph_home).open_session_recall(vault_map_path=vault_map)
    scope = ports.scope.resolve(cwd)
    if not scope.vault_ids:
        raise ValueError(scope.reason or "no Vault is linked to the project folder")
    indexed = tuple(vault_id for vault_id in scope.vault_ids if ports.documents.is_indexed(vault_id))
    catalog = CatalogService(graph_home_path=graph_home).load_catalog()
    facts: dict[PageKey, PageFacts] = {}
    for vault_id in indexed:
        vault_scope = scope.vault_scopes.get(vault_id, UNMAPPED_VAULT_SCOPE)
        for document in ports.documents.documents(vault_id):
            if not document.path.startswith("wiki/"):
                continue
            status = document.frontmatter.get("status")
            table = read_claim_table(ports.documents.body_text(vault_id, document.document_id))
            rows = table.rows if table is not None and table.problem is None else ()
            current = {row.claim for row in rows if row.status != SUPERSEDED_CLAIM_STATUS}
            facts[(vault_id, document.path)] = PageFacts(
                status=(status.strip().casefold() or None) if isinstance(status, str) else None,
                in_project=page_in_project(document.frontmatter, scope.project_id, vault_scope=vault_scope),
                sharable=vault_scope.sharable,
                superseded_claims=tuple(
                    row.claim for row in rows if row.status == SUPERSEDED_CLAIM_STATUS and row.claim not in current
                ),
            )
    return _ProjectView(
        project_id=scope.project_id,
        vault_ids=indexed,
        vault_roots={vault_id: catalog.resolve(vault_id).root_path for vault_id in indexed},
        facts_by_page=facts,
        names=dict(scope.vault_names),
    )


def _run(name: str, command: list[str], *, stdin: str | None = None, env: Mapping[str, str] | None = None) -> str:
    completed = subprocess.run(
        command,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=RUN_TIMEOUT_SECONDS,
        check=False,
        cwd=REPO_ROOT,
        env=dict(env) if env is not None else None,
    )
    if completed.returncode != 0:
        raise ValueError(f"{name} exited {completed.returncode}: {completed.stderr.strip()[:200]}")
    return completed.stdout


def _recall_text(cwd: Path, *, graph_home: Path, vault_map: Path) -> str:
    command = [
        sys.executable, "-c", _VG, "hook", "session-start",
        "--graph-home", str(graph_home), "--vault-map", str(vault_map), "--refresh-budget", "0",
    ]  # fmt: skip
    hook_input = json.dumps({"cwd": str(cwd), "session_id": SESSION_ID, "source": "startup"})
    return _run("vg hook session-start", command, stdin=hook_input)


def _context_pack(question: Question, *, graph_home: Path, vault_map: Path) -> tuple[PageKey, ...]:
    command = [sys.executable, "-c", _CONTEXT_PACK, str(graph_home), question.text, str(question.cwd)]
    output = _run("build_context_pack", command, env={**os.environ, VAULT_MAP_ENV: str(vault_map)})
    body = json.loads(output)
    if not isinstance(body, dict):
        raise ValueError("build_context_pack output is not a JSON object")
    return context_pages(body)


@dataclass
class _ProjectRun:
    view: _ProjectView | None
    recall: frozenset[PageKey]
    report: ProjectReport


def _measure_project(
    cwd: Path, *, graph_home: Path, vault_map: Path, events: Sequence[Mapping[str, object]], now: datetime
) -> _ProjectRun:
    from vault_graph.interface.composition.memory_candidate_sources import memory_candidate_package

    label = str(cwd)
    try:
        view = _open_view(graph_home, vault_map, cwd)
        label = view.project_id or label
        text = _recall_text(cwd, graph_home=graph_home, vault_map=vault_map)
    except Exception as exc:  # any failure of one project is reported in its row, the others still run
        report = ProjectReport(label, _one_line(str(exc)), None, {}, (), 0, ())
        return _ProjectRun(None, frozenset(), report)
    injection = score_injection(text, resolve=view.resolve, facts=view.facts)
    recalled = frozenset(
        (vault_id, path) for vault, path in recall_locations(text) if (vault_id := view.resolve(vault)) is not None
    )
    package = memory_candidate_package(
        graph_home,
        cwd,
        kinds=("session_exchange", "merge"),
        vault_map_file=vault_map,
        now=now,
        with_comparison=False,
    )
    exchanges = [candidate.started_at for candidate in package.candidates if candidate.kind == "session_exchange"]
    report = ProjectReport(
        project=label,
        error=None,
        injection=injection,
        usage=open_ratio(events, project_id=view.project_id) if view.project_id else {},
        backlog_ages=backlog_ages(exchanges, now=now),
        merge_candidates=package.count("merge"),
        warnings=package.warnings,
    )
    return _ProjectRun(view, recalled, report)


def _score_question(question: Question, project: _ProjectRun, *, graph_home: Path, vault_map: Path) -> QuestionScore:
    started = time.monotonic()
    name = project.report.project
    try:
        if project.view is None:
            raise ValueError(f"project recall failed: {project.report.error}")
        expected = resolve_expected(question.expected, resolve=project.view.resolve)
        pages = _context_pack(question, graph_home=graph_home, vault_map=vault_map)
    except (ValueError, subprocess.TimeoutExpired) as exc:
        seconds = time.monotonic() - started
        return QuestionScore(question.question_id, question.axis, name, len(question.expected), None, None, None,
                             seconds, _one_line(str(exc)))  # fmt: skip
    return QuestionScore(
        question_id=question.question_id,
        axis=question.axis,
        project=name,
        expected=len(expected),
        recall_found=sum(1 for key in set(expected) if key in project.recall),
        context_found=sum(1 for key in set(expected) if key in pages),
        context_first_rank=first_rank(expected, pages),
        seconds=time.monotonic() - started,
        error=None,
    )


def main(
    questions: Path, *, graph_home: Path, vault_map: Path, out_dir: Path, now: datetime | None = None
) -> dict[str, object]:
    from vault_graph.storage.local.usage_log import JsonlUsageLog

    _require_outside_repository(questions, "questions")
    _require_outside_repository(out_dir, "out_dir")
    loaded = load_questions(questions)
    moment = now or datetime.now(UTC)
    # Read before the recall runs append their own injected events.
    events = JsonlUsageLog(graph_home, max_files=10**6).read_events()
    runs: dict[Path, _ProjectRun] = {}
    for cwd in dict.fromkeys(question.cwd for question in loaded):
        runs[cwd] = _measure_project(cwd, graph_home=graph_home, vault_map=vault_map, events=events, now=moment)
    scores = [_score_question(q, runs[q.cwd], graph_home=graph_home, vault_map=vault_map) for q in loaded]
    projects: dict[str, ProjectReport] = {}
    vault_roots: dict[str, Path] = {}
    for run in runs.values():
        projects.setdefault(run.report.project, run.report)
        if run.view is not None:
            vault_roots.update(run.view.vault_roots)
    reports = list(projects.values())
    summary = summarize(
        scores, reports, proposals=[proposal_counts(vault_roots[vault_id]) for vault_id in sorted(vault_roots)]
    )
    summary["commit"] = _repository_commit()
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_lines(out_dir / "results.jsonl", (score.to_json() for score in scores))
    _write_lines(out_dir / "projects.jsonl", (report.to_json() for report in reports))
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def _write_lines(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), "utf-8")


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _one_line(text: str) -> str:
    return " ".join(text.split())[:300]


def _require_outside_repository(path: Path, label: str) -> None:
    if path.resolve().is_relative_to(REPO_ROOT):
        raise ValueError(f"{label} must be outside the repository: it holds personal memory content")


def _repository_commit() -> str:
    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip() or "unknown"


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--graph-home", type=Path, required=True)
    parser.add_argument("--vault-map", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = _parse_args(sys.argv[1:])
    result = main(
        arguments.questions, graph_home=arguments.graph_home, vault_map=arguments.vault_map, out_dir=arguments.out_dir
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
