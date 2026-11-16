"""The LongMemEval runner records distinct sessions in the top 5 and keeps its recall scoring (spec 2026-11-16 D7, A5).

The Vault tool, `vg index` and `vg search` are replaced by a fake that returns fixed result paths per question,
so no test needs vault-builder, the embedding model or the network.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from tests.benchmarks import longmemeval_convert as convert
from tests.benchmarks import longmemeval_run as run

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
