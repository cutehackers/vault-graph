"""The LongMemEval runner records distinct sessions in the top 5 and keeps its recall scoring (spec 2026-11-16 D7, A5).

With `--date-rules` it passes a date range only for questions whose date expression resolves (D15, A11, R4).

The Vault tool, `vg index` and `vg search` are replaced by a fake that returns fixed result paths per question,
so no test needs vault-builder, the embedding model or the network.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

import pytest

from tests.benchmarks import longmemeval_convert as convert
from tests.benchmarks import longmemeval_run as run
from vault_graph.retrieval.search.date_expression import DateRange

_TURNS = [
    {"role": "user", "content": "Tell me something.", "has_answer": True},
    {"role": "assistant", "content": "Something."},
]
_HAYSTACK = ["s1", "s2", "s3", "answer_1", "answer_2"]


def _entry(question_id: str, question_type: str, answers: Sequence[str]) -> dict[str, object]:
    return {
        "question_id": question_id,
        "question_type": question_type,
        "question": f"question {question_id}",
        "question_date": "2023/05/30 (Tue) 23:40",
        "answer": "x",
        "answer_session_ids": list(answers),
        "haystack_dates": ["2023/05/21 (Sun) 10:05"] * len(_HAYSTACK),
        "haystack_session_ids": list(_HAYSTACK),
        "haystack_sessions": [list(_TURNS) for _ in _HAYSTACK],
    }


def _path(haystack_id: str, part: int = 1) -> str:
    return f"raw/sessions/claude-code/2023-05-21-{convert.session_uuid(haystack_id)}-part{part}.md"


# Ranked evidence paths per question text. Several results of one session take several of the 5 places.
_RANKED: dict[str, list[list[str]]] = {
    # 3 distinct sessions, both answers in the top 5.
    "question q1": [[_path("answer_1")], [_path("answer_1", 2)], [_path("s1")], [_path("answer_2")], [_path("s1")]],
    # 1 distinct session: one answer session fills all 5 places, the other answer is 6th.
    "question q2": [[_path("answer_1")]] * 5 + [[_path("answer_2")]],
    # 4 distinct sessions, no answer session; a non-session file does not count.
    "question q3": [["wiki/index.md"], [_path("s1")], [_path("s2")], [_path("s3"), _path("s1")], [_path("answer_1")]],
}


class FixedTools:
    def prepare(self, workspace: run.Workspace) -> None:
        workspace.vault.mkdir(parents=True)

    def capture(self, workspace: run.Workspace, normalized: Path) -> str:
        return "written"

    def index(self, workspace: run.Workspace) -> None:
        return None

    def search(self, workspace: run.Workspace, query: str) -> list[list[str]]:
        return _RANKED[query]


def _write(path: Path, entries: Sequence[Mapping[str, object]]) -> Path:
    path.write_text(json.dumps(list(entries)), encoding="utf-8")
    return path


def _run(tmp_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    data = _write(
        tmp_path / "s.json",
        [
            _entry("q1", "multi-session", ["answer_1", "answer_2"]),
            _entry("q2", "multi-session", ["answer_1", "answer_2"]),
            _entry("q3", "single-session-user", ["answer_2"]),
        ],
    )
    summary = run.main(data, work_dir=tmp_path / "work", out_dir=tmp_path / "out", tools=FixedTools(), registered=[])
    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    return summary, rows


def test_results_record_the_distinct_sessions_in_the_top_five_per_question(tmp_path: Path) -> None:
    _, rows = _run(tmp_path)

    assert {row["id"]: row["distinct_sessions_at_5"] for row in rows} == {"q1": 3, "q2": 1, "q3": 4}
    assert all(row["distinct_sessions_at_5"] == len(row["top5_sessions"]) for row in rows)


def test_summary_records_the_mean_distinct_sessions_per_type_and_overall(tmp_path: Path) -> None:
    summary, _ = _run(tmp_path)

    assert summary["distinct_sessions_at_5_by_type"] == {"multi-session": 2.0, "single-session-user": 4.0}
    assert summary["distinct_sessions_at_5"] == round((3 + 1 + 4) / 3, 4)


def test_recall_at_five_is_the_same_as_before_the_session_count(tmp_path: Path) -> None:
    # Values the runner gave for this input before the session count was added.
    summary, rows = _run(tmp_path)

    assert {row["id"]: (row["all_in_top5"], row["any_in_top5"]) for row in rows} == {
        "q1": (True, True),
        "q2": (False, True),
        "q3": (False, False),
    }
    assert summary["recall_all_at_5"] == 0.3333
    assert summary["recall_any_at_5"] == 0.6667
    by_type = summary["by_type"]
    assert isinstance(by_type, dict)
    assert by_type["multi-session"]["recall_all_at_5"] == 0.5
    assert by_type["multi-session"]["recall_any_at_5"] == 1.0
    assert by_type["single-session-user"]["recall_all_at_5"] == 0.0
    assert by_type["single-session-user"]["recall_any_at_5"] == 0.0
    # The per-type block keeps its keys; the session count sits beside it.
    assert all(set(row) == {"questions", "recall_all_at_5", "recall_any_at_5"} for row in by_type.values())


def test_a_failed_question_has_no_session_count_and_is_left_out_of_the_mean() -> None:
    finished = run.QuestionRun("a", "t", ("x",), run.TopScore(("x", "y"), True, True), {"total": 1.0})
    failed = run.QuestionRun("b", "t", ("x",), None, {"total": 1.0}, error="capture skipped")

    summary = run.summarize([finished, failed])

    assert failed.to_json()["distinct_sessions_at_5"] is None
    assert finished.to_json()["distinct_sessions_at_5"] == 2
    assert summary["distinct_sessions_at_5"] == 2.0
    assert summary["distinct_sessions_at_5_by_type"] == {"t": 2.0}
    assert run.summarize([failed])["distinct_sessions_at_5"] is None
    assert run.summarize([failed])["distinct_sessions_at_5_by_type"] == {"t": None}


# Date rules (spec 2026-11-16 D15, A11, R4) ----------------------------------------------------------------

# Synthetic questions asked on Tuesday 2023-05-30, one per expression form of research X15.
_ASKED_ON = date(2023, 5, 30)


@pytest.mark.parametrize(
    ("question", "since", "until"),
    [
        ("What did I bake two weeks ago?", date(2023, 5, 15), date(2023, 5, 21)),
        ("Which book did I finish a week ago?", date(2023, 5, 22), date(2023, 5, 28)),
        ("Which tool did I buy 10 days ago?", date(2023, 5, 20), date(2023, 5, 20)),
        ("What did I join a month ago?", date(2023, 4, 1), date(2023, 4, 30)),
        ("Who did I call a couple of days ago?", date(2023, 5, 26), date(2023, 5, 28)),
        ("Where was I on the Wednesday two months ago?", date(2023, 3, 27), date(2023, 4, 2)),
        ("Who did I meet last Saturday at the market?", date(2023, 5, 27), date(2023, 5, 27)),
        ("What did I fix last week?", date(2023, 5, 22), date(2023, 5, 28)),
        ("Which shoes did I clean last month?", date(2023, 4, 1), date(2023, 4, 30)),
        ("How many trips did I take in the past two months?", date(2023, 3, 30), date(2023, 5, 30)),
        ("Order the events I joined during the past month.", date(2023, 4, 30), date(2023, 5, 30)),
        ("Which games did I watch in February?", date(2023, 2, 1), date(2023, 2, 28)),
        ("Which airline did I use most in March and April?", date(2023, 3, 1), date(2023, 4, 30)),
        ("How many days ago did I read the March 15th newsletter?", date(2023, 3, 15), date(2023, 3, 15)),
    ],
)
def test_date_rules_pick_the_expression_out_of_the_question(question: str, since: date, until: date) -> None:
    assert run.question_date_range(question, _ASKED_ON) == DateRange(since=since, until=until)


@pytest.mark.parametrize(
    "question",
    [
        "How many days ago did I buy a smoker?",
        "Which came first, the bike repair or the car service?",
        "List the trips in order from first to last.",
        "When did I visit the market for the last time?",
        "May I know which degree I graduated with?",
        "How many weeks ago did I start the course?",
    ],
)
def test_a_question_without_a_date_expression_gets_no_range(question: str) -> None:
    assert run.question_date_range(question, _ASKED_ON) is None


class RangeTools(FixedTools):
    """Records the keyword arguments of each search. Without a range the runner calls search as before."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def search(self, workspace: run.Workspace, query: str, **options: object) -> list[list[str]]:
        self.calls.append((query, options))
        return _RANKED["question q1"]


def _date_entries(tmp_path: Path) -> Path:
    return _write(
        tmp_path / "s.json",
        [
            {**_entry("q1", "temporal-reasoning", ["answer_1"]), "question": "What did I bake two weeks ago?"},
            {**_entry("q2", "temporal-reasoning", ["answer_1"]), "question": "How many days ago did I bake?"},
            {**_entry("q3", "multi-session", ["answer_1"]), "question": "What did I fix last week?"},
        ],
    )


def test_date_rules_pass_a_range_only_for_questions_that_resolve(tmp_path: Path) -> None:
    tools = RangeTools()

    summary = run.main(
        _date_entries(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=tools,
        registered=[],
        date_rules=True,
    )

    ranges = {query: options.get("date_range") for query, options in tools.calls}
    assert ranges == {
        "What did I bake two weeks ago?": DateRange(since=date(2023, 5, 15), until=date(2023, 5, 21)),
        "How many days ago did I bake?": None,
        "What did I fix last week?": DateRange(since=date(2023, 5, 22), until=date(2023, 5, 28)),
    }
    # A question with no range calls search exactly as without --date-rules.
    assert [options for query, options in tools.calls if query.startswith("How many")] == [{}]
    rows = {row["id"]: row for row in map(json.loads, (tmp_path / "out" / "results.jsonl").read_text().splitlines())}
    assert rows["q1"]["date_range"] == {"since": "2023-05-15", "until": "2023-05-21"}
    assert rows["q2"]["date_range"] is None
    assert summary["date_rules"] is True
    assert summary["date_strict"] is False
    assert summary["date_range_questions_by_type"] == {"multi-session": 1, "temporal-reasoning": 1}


def test_without_date_rules_search_calls_and_output_are_as_before(tmp_path: Path) -> None:
    tools = RangeTools()

    summary = run.main(
        _date_entries(tmp_path), work_dir=tmp_path / "work", out_dir=tmp_path / "out", tools=tools, registered=[]
    )

    assert all(options == {} for _, options in tools.calls)
    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text().splitlines()]
    assert all("date_range" not in row for row in rows)
    assert "date_rules" not in summary and "date_range_questions_by_type" not in summary


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> list[tuple[list[str], dict[str, str]]]:
    """Replace the subprocess runner so `search` runs no real vg and records each command and environment."""
    seen: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        command: Sequence[str], *, label: str, env: Mapping[str, str], cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        seen.append((list(command), dict(env)))
        return subprocess.CompletedProcess(list(command), 0, json.dumps({"results": []}), "")

    monkeypatch.setattr(run, "_run", fake_run)
    return seen


def _expected_search(workspace: run.Workspace, *dates: str) -> list[str]:
    # The vg search command before the date rules, with the range options placed before ``--``.
    return [
        *run._VG,
        "search",
        "--graph-home",
        str(workspace.graph_home),
        "--format",
        "json",
        "--limit",
        "5",
        "--mode",
        "evidence",
        *dates,
        "--",
        "what did I bake",
    ]


def test_local_search_without_a_range_runs_the_same_command(
    tmp_path: Path, searches: list[tuple[list[str], dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TZ", "Asia/Seoul")
    workspace = run.Workspace(tmp_path / "q0001")

    run.LocalTools(vault_builder=tmp_path / "builder").search(workspace, "what did I bake")

    [(command, env)] = searches
    assert command == _expected_search(workspace)
    assert env["TZ"] == "Asia/Seoul"


def test_local_search_with_a_range_adds_since_until_and_runs_in_utc(
    tmp_path: Path, searches: list[tuple[list[str], dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    # R4: LongMemEval times have no time zone and are written as UTC, so a range search runs with TZ=UTC.
    monkeypatch.setenv("TZ", "Asia/Seoul")
    workspace = run.Workspace(tmp_path / "q0001")
    window = DateRange(since=date(2023, 5, 15), until=date(2023, 5, 21))

    run.LocalTools(vault_builder=tmp_path / "builder").search(workspace, "what did I bake", date_range=window)

    [(command, env)] = searches
    assert command == _expected_search(workspace, "--since", "2023-05-15", "--until", "2023-05-21")
    assert env["TZ"] == "UTC"


def test_local_search_in_strict_mode_adds_date_strict_only_with_a_range(
    tmp_path: Path, searches: list[tuple[list[str], dict[str, str]]]
) -> None:
    # Spec 2026-11-16 D31: strict mode keeps only in-range results, for comparison with the default fill.
    workspace = run.Workspace(tmp_path / "q0001")
    window = DateRange(since=date(2023, 5, 15), until=date(2023, 5, 21))
    tools = run.LocalTools(vault_builder=tmp_path / "builder", date_strict=True)

    tools.search(workspace, "what did I bake", date_range=window)
    tools.search(workspace, "what did I bake")

    [(ranged, _), (unranged, _)] = searches
    assert ranged == _expected_search(workspace, "--since", "2023-05-15", "--until", "2023-05-21", "--date-strict")
    assert unranged == _expected_search(workspace)


def test_strict_date_rules_are_recorded_in_the_summary(tmp_path: Path) -> None:
    summary = run.main(
        _date_entries(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=RangeTools(),
        registered=[],
        date_rules=True,
        date_strict=True,
    )

    assert summary["date_strict"] is True


def test_the_date_strict_argument_goes_with_date_rules() -> None:
    base = ["--data", "d.json", "--vault-builder", "b", "--work-dir", "w", "--out-dir", "o"]

    assert run._parse_args([*base, "--date-rules"]).date_strict is False
    assert run._parse_args([*base, "--date-rules", "--date-strict"]).date_strict is True
    with pytest.raises(SystemExit):
        run._parse_args([*base, "--date-strict"])


def test_the_date_rules_argument_is_off_by_default_and_the_runner_documents_tz_utc() -> None:
    base = ["--data", "d.json", "--vault-builder", "b", "--work-dir", "w", "--out-dir", "o"]

    assert run._parse_args(base).date_rules is False
    assert run._parse_args([*base, "--date-rules"]).date_rules is True
    assert "TZ=UTC" in (run.__doc__ or "")


# Session facts (spec 2026-11-16 D19, D20, D23, A25) ---------------------------------------------------------


class FakeVaultAndVg:
    """Stands in for `_run`: the Vault tool, vg and git. Records each command by label in order.

    `sessions capture` answers `written` with a new part path. `vg facts worker` acts like the worker: it removes
    each queued job, puts one cache entry per new exchange into `--cache-dir`, and prints one line per job.
    `vg search` answers the ranked paths of the first question. Nothing here starts a process.
    """

    def __init__(self, *, worker_status: str = "written", leave_jobs: bool = False) -> None:
        self.calls: list[tuple[str, list[str]]] = []
        self.captured = 0
        self.worker_status = worker_status
        self.leave_jobs = leave_jobs

    def __call__(
        self, command: Sequence[str], *, label: str, env: Mapping[str, str], cwd: Path | None = None, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        command = list(command)
        self.calls.append((label, command))
        stdout = ""
        if label == "sessions capture":
            self.captured += 1
            part = f"raw/sessions/claude-code/2023-05-21-{self.captured:036d}-part1.md"
            stdout = json.dumps({"status": "written", "vault": "lme", "path": part})
        elif label == "vg facts worker":
            stdout = self._work(command)
        elif label == "vg search":
            stdout = json.dumps(
                {"results": [{"evidence": [{"path": p} for p in paths]} for paths in _RANKED["question q1"]]}
            )
        return subprocess.CompletedProcess(command, 0, stdout, "")

    def _work(self, command: list[str]) -> str:
        from vault_graph.interface.composition.adapters.fact_queue import list_fact_jobs, read_fact_job

        graph_home = Path(command[command.index("--graph-home") + 1])
        cache = Path(command[command.index("--cache-dir") + 1])
        lines = []
        for job_path in list_fact_jobs(graph_home):
            job = read_fact_job(job_path)
            # One cached exchange per part; parts 1 and 2 share content, so the second is a cache hit.
            entry = cache / "ab" / f"{job.part.split('-')[-2][-1]}.json"
            entry.parent.mkdir(parents=True, exist_ok=True)
            entry.write_text("{}", encoding="utf-8")
            lines.append(f"facts worker: {job_path.name} {self.worker_status}")
            if not self.leave_jobs:
                job_path.unlink()
        return "\n".join(lines) + "\n"

    def labels(self) -> list[str]:
        return [label for label, _ in self.calls]


def _one_question(tmp_path: Path, question_type: str = "multi-session") -> Path:
    return _write(tmp_path / "s.json", [_entry("q1", question_type, ["answer_1", "answer_2"])])


def _facts_json(workspace: run.Workspace) -> dict[str, object]:
    payload: dict[str, object] = json.loads((workspace.graph_home / "configs" / "facts.json").read_text("utf-8"))
    return payload


def test_a_normal_run_turns_facts_off_in_each_graph_home_and_calls_no_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A25: without the B measurement arguments every workspace Graph Home gets `enabled: false` and nothing runs
    # `claude`, `llama-server` or the fact worker.
    fake = FakeVaultAndVg()
    monkeypatch.setattr(run, "_run", fake)
    seen_settings: list[dict[str, object]] = []
    real_index = run.LocalTools.index

    def index(self: run.LocalTools, workspace: run.Workspace) -> None:
        seen_settings.append(_facts_json(workspace))
        real_index(self, workspace)

    monkeypatch.setattr(run.LocalTools, "index", index)

    summary = run.main(
        _one_question(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=run.LocalTools(vault_builder=tmp_path / "builder"),
        registered=[],
    )

    assert [settings["enabled"] for settings in seen_settings] == [False]
    executables = {Path(command[0]).name for _, command in fake.calls}
    assert not executables & {"claude", "llama-server"}
    assert not any("facts" in command for _, command in fake.calls)
    assert "vg facts worker" not in fake.labels()
    assert "facts" not in summary
    [row] = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert "facts" not in row and row["error"] is None


def test_facts_off_by_default_also_holds_for_the_cli_arguments() -> None:
    base = ["--data", "d.json", "--vault-builder", "b", "--work-dir", "w", "--out-dir", "o"]

    arguments = run._parse_args(base)

    assert arguments.facts is None and arguments.facts_cache is None
    with pytest.raises(SystemExit):
        run._parse_args([*base, "--facts", "claude"])  # B measurement needs the shared cache folder
    with pytest.raises(SystemExit):
        run._parse_args([*base, "--facts-cache", "c"])
    with pytest.raises(SystemExit):
        run._parse_args([*base, "--facts", "gpt", "--facts-cache", "c"])
    measured = run._parse_args([*base, "--facts", "llama-server", "--facts-cache", "c"])
    assert (measured.facts, measured.facts_cache) == ("llama-server", Path("c"))


def test_b_measurement_runs_the_fact_worker_between_capture_and_index_with_the_shared_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeVaultAndVg()
    monkeypatch.setattr(run, "_run", fake)
    cache = tmp_path / "cache"
    tools = run.LocalTools(vault_builder=tmp_path / "builder", facts="llama-server", facts_cache=cache)
    settings_at_worker: list[dict[str, object]] = []
    jobs_at_worker: list[int] = []

    def worker_spy(command: Sequence[str], **options: object) -> subprocess.CompletedProcess[str]:
        if options["label"] == "vg facts worker":
            from vault_graph.interface.composition.adapters.fact_queue import list_fact_jobs

            graph_home = Path(list(command)[list(command).index("--graph-home") + 1])
            settings_at_worker.append(json.loads((graph_home / "configs" / "facts.json").read_text("utf-8")))
            jobs_at_worker.append(len(list_fact_jobs(graph_home)))
        return fake(command, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(run, "_run", worker_spy)

    summary = run.main(
        _one_question(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=tools,
        registered=[],
        facts="llama-server",
    )

    labels = fake.labels()
    captures = labels.count("sessions capture")
    assert captures == len(_HAYSTACK)
    # Capture all parts, then one foreground worker run, then index.
    assert labels.index("vg facts worker") > max(i for i, name in enumerate(labels) if name == "sessions capture")
    assert labels.index("vg facts worker") < labels.index("vg index")
    assert labels.count("vg facts worker") == 1
    [(_, worker)] = [(label, command) for label, command in fake.calls if label == "vg facts worker"]
    workspace = run.Workspace(tmp_path / "work" / "q0001")
    assert worker[len(run._VG) :] == [
        "facts",
        "worker",
        "--graph-home",
        str(workspace.graph_home),
        "--cache-dir",
        str(cache),
    ]
    assert jobs_at_worker == [captures]  # one job per captured part
    [settings] = settings_at_worker
    assert (settings["enabled"], settings["extractor"]) == (True, "llama-server")
    [row] = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert row["error"] is None
    assert row["facts"] == {"cache_misses": captures, "attachments_written": captures}
    assert row["seconds"]["facts"] >= 0
    assert summary["facts"] == {
        "extractor": "llama-server",
        "cache_misses": captures,
        "attachments_written": captures,
    }


def test_the_shared_cache_counts_only_new_entries_per_question(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Both questions capture the same parts, so the second finds every exchange in the shared cache.
    fake = FakeVaultAndVg()
    monkeypatch.setattr(run, "_run", fake)
    data = _write(
        tmp_path / "s.json",
        [_entry("q1", "multi-session", ["answer_1"]), _entry("q2", "multi-session", ["answer_1"])],
    )
    tools = run.LocalTools(vault_builder=tmp_path / "builder", facts="claude", facts_cache=tmp_path / "cache")

    original = fake.__call__

    def same_parts(command: Sequence[str], **options: object) -> subprocess.CompletedProcess[str]:
        if options["label"] == "sessions capture" and fake.captured == len(_HAYSTACK):
            fake.captured = 0  # the second question captures the same part names
        return original(command, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(run, "_run", same_parts)

    summary = run.main(
        data, work_dir=tmp_path / "work", out_dir=tmp_path / "out", tools=tools, registered=[], facts="claude"
    )

    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert [row["facts"]["cache_misses"] for row in rows] == [len(_HAYSTACK), 0]
    assert summary["facts"] == {
        "extractor": "claude",
        "cache_misses": len(_HAYSTACK),
        "attachments_written": 2 * len(_HAYSTACK),
    }


@pytest.mark.parametrize(("status", "leave_jobs"), [("waiting", True), ("closed", False)])
def test_a_worker_that_does_not_finish_every_job_fails_the_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str, leave_jobs: bool
) -> None:
    # An extractor that is down or a rejected attachment would otherwise score as a run without facts.
    monkeypatch.setattr(run, "_run", FakeVaultAndVg(worker_status=status, leave_jobs=leave_jobs))
    tools = run.LocalTools(vault_builder=tmp_path / "builder", facts="claude", facts_cache=tmp_path / "cache")

    run.main(
        _one_question(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=tools,
        registered=[],
        facts="claude",
    )

    [row] = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert row["error"] is not None and "facts worker" in row["error"]


def test_local_tools_need_a_known_extractor_and_a_cache_together(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        run.LocalTools(vault_builder=tmp_path, facts="claude")
    with pytest.raises(ValueError):
        run.LocalTools(vault_builder=tmp_path, facts_cache=tmp_path / "cache")
    with pytest.raises(ValueError):
        run.LocalTools(vault_builder=tmp_path, facts="gpt", facts_cache=tmp_path / "cache")


# Question selection (spec 2026-11-16 D23) ------------------------------------------------------------------


def _typed_entries(tmp_path: Path, count: int) -> Path:
    types = ["multi-session", "temporal-reasoning", "single-session-user"]
    return _write(tmp_path / "s.json", [_entry(f"q{n}", types[n % 3], ["answer_1"]) for n in range(count)])


def test_types_pick_the_first_questions_of_those_types_within_the_sample(tmp_path: Path) -> None:
    data = _typed_entries(tmp_path, 200)
    sample = convert.select_questions(convert.load_questions(data), limit=run.SAMPLE_QUESTIONS)
    wanted = [q.question_id for q in sample if q.question_type in ("multi-session", "temporal-reasoning")][:20]

    summary = run.main(
        data,
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=RangeTools(),
        registered=[],
        limit=20,
        types=("multi-session", "temporal-reasoning"),
    )

    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert [row["id"] for row in rows] == wanted
    assert summary["types"] == ["multi-session", "temporal-reasoning"]


def test_ids_pick_those_questions_in_the_fixed_order(tmp_path: Path) -> None:
    data = _typed_entries(tmp_path, 10)
    order = [q.question_id for q in convert.select_questions(convert.load_questions(data))]

    summary = run.main(
        data, work_dir=tmp_path / "work", out_dir=tmp_path / "out", tools=RangeTools(), registered=[], ids=("q3", "q7")
    )

    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert [row["id"] for row in rows] == [qid for qid in order if qid in ("q3", "q7")]
    assert summary["ids"] == ["q3", "q7"]


def test_type_and_id_arguments_are_comma_lists() -> None:
    base = ["--data", "d.json", "--vault-builder", "b", "--work-dir", "w", "--out-dir", "o"]

    assert (run._parse_args(base).types, run._parse_args(base).ids) == (None, None)
    arguments = run._parse_args([*base, "--types", "multi-session,temporal-reasoning", "--ids", "a,b"])
    assert arguments.types == ("multi-session", "temporal-reasoning")
    assert arguments.ids == ("a", "b")


def test_the_fact_worker_keeps_the_persons_claude_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`claude -p` in the worker needs the person's Claude Code login, not the workspace config folder."""
    fake = FakeVaultAndVg()
    envs: dict[str, Mapping[str, str]] = {}

    def spy(command: Sequence[str], **options: object) -> subprocess.CompletedProcess[str]:
        envs.setdefault(str(options["label"]), options["env"])  # type: ignore[arg-type]
        return fake(command, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(run, "_run", spy)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/person/claude")
    tools = run.LocalTools(vault_builder=tmp_path / "builder", facts="claude", facts_cache=tmp_path / "cache")

    run.main(
        _one_question(tmp_path),
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=tools,
        registered=[],
        facts="claude",
    )

    workspace = run.Workspace(tmp_path / "work" / "q0001")
    assert envs["vg facts worker"]["CLAUDE_CONFIG_DIR"] == "/person/claude"
    assert envs["vg facts worker"]["VAULT_GRAPH_VAULT_MAP"] == str(workspace.vault_map)
    assert envs["vg index"]["CLAUDE_CONFIG_DIR"] == str(workspace.config_dir)
