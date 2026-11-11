"""The LongMemEval-S converter and runner (spec 2026-11-11 §4.1.4, A-6, 결정10).

Unit tests use a small synthetic file in the LongMemEval-S shape. The Vault tool, `vg index` and
`vg search` are replaced by a fake, so no test needs vault-builder, the embedding model or the network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from tests.benchmarks import longmemeval_convert as convert
from tests.benchmarks import longmemeval_run as run
from vault_graph.operation.sessions.models import NORMALIZED_SESSION_SCHEMA


def _entry(question_id: str, **fields: object) -> dict[str, object]:
    entry: dict[str, object] = {
        "question_id": question_id,
        "question_type": "single-session-user",
        "question": "What degree did I graduate with?",
        "question_date": "2023/05/30 (Tue) 23:40",
        "answer": "Business Administration",
        "answer_session_ids": ["answer_1"],
        "haystack_dates": ["2023/05/20 (Sat) 02:21", "2023/05/21 (Sun) 10:05"],
        "haystack_session_ids": ["sharegpt_x_0", "answer_1"],
        "haystack_sessions": [
            [
                {"role": "assistant", "content": "Hello again."},
                {"role": "user", "content": "Solve the river puzzle."},
                {"role": "assistant", "content": "Take the chicken first."},
            ],
            [
                {
                    "role": "user",
                    "content": "I graduated with a degree in Business Administration.",
                    "has_answer": True,
                },
                {"role": "assistant", "content": "Congratulations!"},
                {"role": "user", "content": "Thanks."},
                {"role": "user", "content": "One more thing."},
            ],
        ],
    }
    entry.update(fields)
    return entry


def _write(path: Path, entries: Sequence[Mapping[str, object]]) -> Path:
    path.write_text(json.dumps(list(entries)), encoding="utf-8")
    return path


# Loading --------------------------------------------------------------------------------------------


def test_load_questions_reads_the_longmemeval_s_shape(tmp_path: Path) -> None:
    [question] = convert.load_questions(_write(tmp_path / "s.json", [_entry("q1")]))

    assert question.question_id == "q1"
    assert question.question_type == "single-session-user"
    assert question.answer_session_ids == ("answer_1",)
    assert [session.haystack_id for session in question.sessions] == ["sharegpt_x_0", "answer_1"]
    assert question.sessions[1].date == "2023/05/21 (Sun) 10:05"
    assert question.sessions[0].turns[0] == ("assistant", "Hello again.")


def test_load_questions_keeps_the_first_of_repeated_session_ids(tmp_path: Path) -> None:
    entry = _entry(
        "q1",
        haystack_dates=["2023/05/20 (Sat) 02:21", "2023/05/21 (Sun) 10:05", "2023/05/22 (Mon) 09:00"],
        haystack_session_ids=["s_0", "answer_1", "s_0"],
        haystack_sessions=[
            [{"role": "user", "content": "first"}],
            [{"role": "user", "content": "answer"}],
            [{"role": "user", "content": "again"}],
        ],
    )

    [question] = convert.load_questions(_write(tmp_path / "s.json", [entry]))

    assert [session.haystack_id for session in question.sessions] == ["s_0", "answer_1"]
    assert question.sessions[0].turns == (("user", "first"),)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"haystack_dates": ["2023/05/20 (Sat) 02:21"]}, "same length"),
        ({"answer_session_ids": "answer_1"}, "answer_session_ids"),
        ({"haystack_sessions": [[{"role": "system", "content": "x"}], []]}, "role"),
        ({"question": 3}, "question"),
    ],
)
def test_load_questions_rejects_a_broken_entry(tmp_path: Path, fields: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        convert.load_questions(_write(tmp_path / "s.json", [_entry("q1", **fields)]))


def test_select_questions_drops_abstention_and_keeps_a_fixed_order(tmp_path: Path) -> None:
    entries = [_entry(f"q{number}") for number in range(10)] + [_entry("q3_abs")]
    questions = convert.load_questions(_write(tmp_path / "s.json", entries))

    everything = convert.select_questions(questions)
    first_four = convert.select_questions(questions, limit=4)
    reversed_input = convert.select_questions(tuple(reversed(questions)), limit=4)

    assert len(everything) == 10
    assert "q3_abs" not in {question.question_id for question in everything}
    assert first_four == everything[:4]
    assert [q.question_id for q in reversed_input] == [q.question_id for q in first_four]
    # The order is by hash, not by file order, so a short run is a spread sample.
    assert [q.question_id for q in everything] != [f"q{number}" for number in range(10)]


# Normalizing ----------------------------------------------------------------------------------------


def test_normalize_session_writes_vg_session_jsonl_lines(tmp_path: Path) -> None:
    [question] = convert.load_questions(_write(tmp_path / "s.json", [_entry("q1")]))

    text = convert.encode_session_file(question.sessions[1], cwd="/tmp/lme/project")
    lines = [json.loads(line) for line in text.splitlines()]

    assert all(line["schema"] == NORMALIZED_SESSION_SCHEMA for line in lines)
    session = lines[0]
    assert session["kind"] == "session"
    assert session["session_id"] == convert.session_uuid("answer_1")
    assert session["agent"] == "claude-code"
    assert session["cwd"] == "/tmp/lme/project"
    assert session["started_at"] == "2023-05-21T10:05:00.000Z"
    kinds = [(line["kind"], line.get("turn_kind")) for line in lines[1:]]
    # Each user turn opens an exchange. Two user turns in a row are two exchanges.
    assert kinds == [
        ("exchange", None),
        ("turn", "human"),
        ("turn", "assistant_text"),
        ("exchange", None),
        ("turn", "human"),
        ("exchange", None),
        ("turn", "human"),
    ]
    exchanges = [line for line in lines if line["kind"] == "exchange"]
    assert all(line["closed"] is True and line["outcome"] == "answered" for line in exchanges)
    assert len({line["exchange_id"] for line in exchanges}) == 3
    turns = [line for line in lines if line["kind"] == "turn"]
    assert turns[0]["text"] == "I graduated with a degree in Business Administration."
    assert turns[0]["at"] == "2023-05-21T10:05:00.000Z"
    assert turns[1]["at"] == "2023-05-21T10:05:01.000Z"
    assert turns[1]["exchange_id"] == exchanges[0]["exchange_id"]


def test_line_separators_in_text_become_newlines_so_every_line_stays_one_json_line(tmp_path: Path) -> None:
    # The Vault tool splits the file with str.splitlines(), which also breaks at U+2028, U+2029 and U+0085.
    session = convert.LmeSession("s_0", "2023/05/20 (Sat) 02:21", (("user", "a b c\x85d"),))

    text = convert.encode_session_file(session, cwd="/p")

    assert len(text.splitlines()) == len(text.split("\n")) - 1 == 3
    assert json.loads(text.splitlines()[2])["text"] == "a\nb\nc\nd"


def test_leading_assistant_turns_form_their_own_exchange(tmp_path: Path) -> None:
    [question] = convert.load_questions(_write(tmp_path / "s.json", [_entry("q1")]))

    lines = [json.loads(line) for line in convert.encode_session_file(question.sessions[0], cwd="/p").splitlines()]

    kinds = [(line["kind"], line.get("turn_kind")) for line in lines[1:]]
    assert kinds == [
        ("exchange", None),
        ("turn", "assistant_text"),
        ("exchange", None),
        ("turn", "human"),
        ("turn", "assistant_text"),
    ]


def test_write_question_sessions_writes_one_file_per_session_and_maps_ids(tmp_path: Path) -> None:
    [question] = convert.load_questions(_write(tmp_path / "s.json", [_entry("q1")]))

    written = convert.write_question_sessions(question, tmp_path / "normalized", cwd="/p")

    assert [path.name for path in written.files] == [
        f"{convert.session_uuid('sharegpt_x_0')}.jsonl",
        f"{convert.session_uuid('answer_1')}.jsonl",
    ]
    assert written.haystack_ids == {
        convert.session_uuid("sharegpt_x_0"): "sharegpt_x_0",
        convert.session_uuid("answer_1"): "answer_1",
    }
    assert written.files[1].read_text(encoding="utf-8") == convert.encode_session_file(question.sessions[1], cwd="/p")


def test_session_uuid_is_stable_and_valid_for_the_vault_tool() -> None:
    first = convert.session_uuid("sharegpt_yywfIrx_0")

    assert first == convert.session_uuid("sharegpt_yywfIrx_0")
    assert first != convert.session_uuid("sharegpt_yywfIrx_1")
    # The Vault tool accepts session ids of letters, digits and "-" only.
    assert all(character.isalnum() or character == "-" for character in first)


# Scoring --------------------------------------------------------------------------------------------


def _path(haystack_id: str, part: int = 1) -> str:
    return f"raw/sessions/claude-code/2023-05-21-{convert.session_uuid(haystack_id)}-part{part}.md"


def test_score_counts_all_answer_sessions_in_the_top_five_results() -> None:
    ids = {convert.session_uuid(name): name for name in ("a", "b", "c", "d", "e", "f", "answer_1", "answer_2")}
    paths = [[_path("a")], [_path("answer_1")], [_path("b")], [_path("answer_2")], [_path("c")], [_path("d")]]

    both = run.score_top5(("answer_1", "answer_2"), paths, ids)
    sixth = run.score_top5(("answer_1", "d"), paths, ids)

    assert both.all_in_top5 is True and both.any_in_top5 is True
    assert both.top5_sessions == ("a", "answer_1", "b", "answer_2", "c")
    assert sixth.all_in_top5 is False and sixth.any_in_top5 is True


def test_score_reads_every_evidence_path_of_a_result_and_ignores_other_files() -> None:
    ids = {convert.session_uuid(name): name for name in ("answer_1", "answer_2")}
    paths = [["wiki/index.md"], [_path("answer_1"), _path("answer_2", part=2)]]

    score = run.score_top5(("answer_1", "answer_2"), paths, ids)

    assert score.all_in_top5 is True
    assert score.top5_sessions == ("answer_1", "answer_2")


def test_result_paths_reads_vg_search_json() -> None:
    payload = {"results": [{"evidence": [{"path": "a.md"}, {"path": "b.md"}]}, {"evidence": []}]}

    assert run.result_paths(payload) == [["a.md", "b.md"], []]
    with pytest.raises(ValueError, match="results"):
        run.result_paths({"no": "results"})


# Target folder refusal ------------------------------------------------------------------------------


def test_check_work_dir_accepts_a_new_temporary_folder(tmp_path: Path) -> None:
    run.check_work_dir(tmp_path / "new", registered=[tmp_path / "vaults" / "real"], default_graph_home=tmp_path / "gh")
    empty = tmp_path / "empty"
    empty.mkdir()
    run.check_work_dir(empty, registered=[], default_graph_home=tmp_path / "gh")


@pytest.mark.parametrize("where", ["same", "inside", "contains"])
def test_check_work_dir_refuses_a_registered_vault(tmp_path: Path, where: str) -> None:
    vault = tmp_path / "vaults" / "real"
    work = {"same": vault, "inside": vault / "lme", "contains": tmp_path / "vaults"}[where]

    with pytest.raises(ValueError, match="registered Vault"):
        run.check_work_dir(work, registered=[vault], default_graph_home=tmp_path / "gh")


def test_check_work_dir_refuses_the_default_graph_home_and_a_folder_with_files(tmp_path: Path) -> None:
    graph_home = tmp_path / ".vault-graph"
    with pytest.raises(ValueError, match="default Graph Home"):
        run.check_work_dir(graph_home / "lme", registered=[], default_graph_home=graph_home)
    used = tmp_path / "used"
    used.mkdir()
    (used / "keep.md").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        run.check_work_dir(used, registered=[], default_graph_home=graph_home)


def test_check_work_dir_refuses_the_repository() -> None:
    with pytest.raises(ValueError, match="repository"):
        run.check_work_dir(run.REPO_ROOT / "tmp-lme", registered=[], default_graph_home=Path("/nowhere/.vault-graph"))


def test_registered_vault_roots_reads_the_vault_map_and_the_default_catalog(tmp_path: Path) -> None:
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"mine": {"path": str(tmp_path / "mine"), "role": "personal"}},
                "projects": {},
            }
        ),
        encoding="utf-8",
    )

    roots = run.registered_vault_roots(vault_map=vault_map, default_graph_home=tmp_path / "no-graph-home")

    assert (tmp_path / "mine").resolve() in roots


# Vault tool commands --------------------------------------------------------------------------------


def test_capture_command_runs_the_vault_tool_with_normalized(tmp_path: Path) -> None:
    command = run.capture_command(tmp_path / "vault", tmp_path / "n" / "s.jsonl")

    assert command[-5:] == ["sessions", "capture", "--normalized", str(tmp_path / "n" / "s.jsonl"), "--json"]
    assert str(tmp_path / "vault" / "tools" / "wiki" / "cli.py") in command
    assert "--rerender" not in command


# Running --------------------------------------------------------------------------------------------


class FakeTools:
    """Records what the runner asks for and answers search with the captured sessions in capture order."""

    def __init__(self, *, fail_capture: bool = False) -> None:
        self.prepared: list[Path] = []
        self.captured: list[Path] = []
        self.indexed: list[Path] = []
        self.searched: list[str] = []
        self.fail_capture = fail_capture

    def prepare(self, workspace: run.Workspace) -> None:
        self.prepared.append(workspace.root)
        workspace.vault.mkdir(parents=True)

    def capture(self, workspace: run.Workspace, normalized: Path) -> str:
        if self.fail_capture:
            raise run.StepError("capture skipped: no vault")
        assert normalized.is_file() and not normalized.is_relative_to(workspace.vault)
        self.captured.append(normalized)
        return "written"

    def index(self, workspace: run.Workspace) -> None:
        self.indexed.append(workspace.graph_home)

    def search(self, workspace: run.Workspace, query: str) -> list[list[str]]:
        self.searched.append(query)
        names = [path.stem for path in self.captured if path.is_relative_to(workspace.root)]
        return [[f"raw/sessions/claude-code/2023-05-21-{name}-part1.md"] for name in names]


def test_main_runs_each_question_in_its_own_workspace_and_writes_results(tmp_path: Path) -> None:
    entries = [
        _entry("hit"),
        _entry("miss", answer_session_ids=["answer_1", "missing_session"]),
        _entry("skip_abs"),
    ]
    data = _write(tmp_path / "s.json", entries)
    tools = FakeTools()
    ticks = iter(float(number) for number in range(1000))

    summary = run.main(
        data,
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=tools,
        registered=[],
        clock=lambda: next(ticks),
    )

    assert summary["questions"] == 2
    assert summary["failed"] == 0
    assert summary["recall_all_at_5"] == 0.5
    assert summary["recall_any_at_5"] == 1.0
    assert summary["by_type"] == {
        "single-session-user": {"questions": 2, "recall_all_at_5": 0.5, "recall_any_at_5": 1.0}
    }
    assert len(set(tools.prepared)) == 2 and len(tools.indexed) == 2
    assert len(tools.captured) == 4
    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert {row["id"] for row in rows} == {"hit", "miss"}
    assert all(set(row["seconds"]) == {"prepare", "convert", "capture", "index", "search", "total"} for row in rows)
    assert all("question" not in row for row in rows)
    assert json.loads((tmp_path / "out" / "summary.json").read_text("utf-8"))["questions"] == 2
    # Workspaces are removed after each question unless asked to keep them.
    assert not any(path.exists() for path in tools.prepared)


def test_main_records_a_failed_step_and_goes_on(tmp_path: Path) -> None:
    data = _write(tmp_path / "s.json", [_entry("q1"), _entry("q2")])

    summary = run.main(
        data, work_dir=tmp_path / "work", out_dir=tmp_path / "out", tools=FakeTools(fail_capture=True), registered=[]
    )

    assert summary["questions"] == 2
    assert summary["failed"] == 2
    assert summary["recall_all_at_5"] is None
    rows = [json.loads(line) for line in (tmp_path / "out" / "results.jsonl").read_text("utf-8").splitlines()]
    assert rows[0]["error"] == "capture skipped: no vault"


def test_main_refuses_a_registered_vault_before_running(tmp_path: Path) -> None:
    data = _write(tmp_path / "s.json", [_entry("q1")])
    tools = FakeTools()

    with pytest.raises(ValueError, match="registered Vault"):
        run.main(
            data,
            work_dir=tmp_path / "vault" / "x",
            out_dir=tmp_path / "out",
            tools=tools,
            registered=[tmp_path / "vault"],
        )

    assert tools.prepared == []


def test_time_per_question_leaves_out_failed_questions() -> None:
    finished = run.QuestionRun("a", "t", ("x",), run.TopScore(("x",), True, True), {"total": 20.0})
    failed = run.QuestionRun("b", "t", ("x",), None, {"total": 1.0}, error="capture skipped")

    summary = run.summarize([finished, failed])

    assert summary["seconds_per_question"] == {"mean": 20.0, "p50": 20.0, "max": 20.0, "total": 21.0}
    assert summary["scope"] == "sample-150"


@pytest.mark.parametrize(("seconds", "scope"), [(15.0, "full-470"), (15.4, "sample-150")])
def test_scope_for_follows_decision_10(seconds: float, scope: str) -> None:
    # 470 questions within two hours means at most about 15.3 seconds per question.
    assert run.scope_for(seconds) == scope


def test_summary_reports_time_per_question_and_the_scope(tmp_path: Path) -> None:
    data = _write(tmp_path / "s.json", [_entry("q1"), _entry("q2")])
    ticks = iter(float(number) * 10 for number in range(1000))

    summary = run.main(
        data,
        work_dir=tmp_path / "work",
        out_dir=tmp_path / "out",
        tools=FakeTools(),
        registered=[],
        clock=lambda: next(ticks),
    )

    seconds = summary["seconds_per_question"]
    assert isinstance(seconds, dict)
    assert set(seconds) == {"mean", "p50", "max", "total"}
    assert summary["scope"] == run.scope_for(float(seconds["mean"]))
    assert summary["estimated_hours_470"] == round(float(seconds["mean"]) * 470 / 3600, 2)
