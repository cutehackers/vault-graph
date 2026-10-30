from __future__ import annotations

import inspect
import json
import subprocess
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
from pytest import MonkeyPatch

from tests.benchmarks import measure_vault_search_parity as parity

VAULT_TEXT = "\n".join(
    [
        "- wiki/a.md [concept, active, updated 2026-10-01] score=12",
        "  A: summary a",
        "  > snippet with - wiki/fake.md [x, y, updated z] score=1 inside",
        "- wiki/b c.md [decision, active, updated 2026-10-02] score=4",
        "  B: summary b",
    ]
)


def _vg_json(*paths: str) -> str:
    results = [
        {"rank": index, "evidence": [{"path": path, "chunk_id": f"c{index}"}]} for index, path in enumerate(paths)
    ]
    return json.dumps({"results": results})


class FakeProcesses:
    def __init__(self, respond: Callable[[Sequence[str]], tuple[int, str]]) -> None:
        self.respond = respond
        self.calls: list[tuple[list[str], Path | None]] = []

    def __call__(self, argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(argv), kwargs.get("cwd")))
        if list(argv[:2]) == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(list(argv), 0, "abc1234\n", "")
        code, stdout = self.respond(argv)
        return subprocess.CompletedProcess(list(argv), code, stdout, "boom" if code else "")


def _is_vault(argv: Sequence[str]) -> bool:
    return "tools/wiki/cli.py" in argv


def _write_questions(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n\n", encoding="utf-8")
    return path


def _clock(step: float = 1.0) -> Iterator[float]:
    value = 0.0
    while True:
        yield value
        value += step


@pytest.fixture()
def dirs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    questions = tmp_path / "questions.jsonl"
    vault = tmp_path / "vault"
    graph_home = tmp_path / "graph-home"
    out_dir = tmp_path / "out"
    return questions, vault, graph_home, out_dir


def test_main_has_the_spec_signature() -> None:
    signature = inspect.signature(parity.main)
    assert list(signature.parameters) == ["questions", "vault", "graph_home", "out_dir"]
    assert all(parameter.annotation in {Path, "Path"} for parameter in signature.parameters.values())
    assert signature.return_annotation in {None, "None"}


def test_parse_vault_hits_reads_paths_from_render_hits_text() -> None:
    assert parity.parse_vault_hits(VAULT_TEXT) == ["wiki/a.md", "wiki/b c.md"]
    assert parity.parse_vault_hits("No matching wiki pages.\n") == []


def test_parse_vault_hits_rejects_unrecognized_output() -> None:
    with pytest.raises(ValueError):
        parity.parse_vault_hits("Traceback (most recent call last):\n")


def test_parse_vg_hits_uses_document_path_of_each_result() -> None:
    assert parity.parse_vg_hits(_vg_json("wiki/a.md", "./raw/s.md")) == ["wiki/a.md", "raw/s.md"]
    with pytest.raises(ValueError):
        parity.parse_vg_hits("not json")


def test_main_runs_each_system_three_times_and_records_hits_and_times(
    dirs: tuple[Path, Path, Path, Path], monkeypatch: MonkeyPatch
) -> None:
    questions, vault, graph_home, out_dir = dirs
    _write_questions(
        questions,
        [
            {"id": "q1", "question": "첫 질문", "expected": ["wiki/b c.md"]},
            {"id": "q2", "question": "둘째 질문", "expected": ["wiki/z.md"]},
        ],
    )

    def respond(argv: Sequence[str]) -> tuple[int, str]:
        if _is_vault(argv):
            return 0, VAULT_TEXT
        return 0, _vg_json("wiki/x.md", "wiki/z.md")

    fake = FakeProcesses(respond)
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(time, "perf_counter", _clock().__next__)

    parity.main(questions, vault, graph_home, out_dir)

    search_calls = [call for call in fake.calls if call[0][0] != "git"]
    assert len(search_calls) == 2 * 2 * 3
    vault_argv, vault_cwd = next(call for call in search_calls if _is_vault(call[0]))
    assert vault_argv[1:] == ["-I", "-B", "tools/wiki/cli.py", "search", "첫 질문", "--limit", "5"]
    assert vault_cwd == vault
    vg_argv = next(call[0] for call in search_calls if not _is_vault(call[0]))
    assert vg_argv[:2] == ["vg", "search"]
    assert "첫 질문" in vg_argv
    for option, value in (("--graph-home", str(graph_home)), ("--limit", "5"), ("--format", "json")):
        assert vg_argv[vg_argv.index(option) + 1] == value

    rows = [json.loads(line) for line in (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["id"] for row in rows] == ["q1", "q2"]
    assert rows[0]["vault"]["outcome"] == "hit"
    assert rows[0]["vg"]["outcome"] == "miss"
    assert rows[1]["vault"]["outcome"] == "miss"
    assert rows[1]["vg"]["outcome"] == "hit"
    assert rows[0]["vault"]["seconds"] == [1.0, 1.0, 1.0]
    assert rows[0]["vault"]["first_seconds"] == 1.0
    assert rows[0]["vault"]["median_seconds"] == 1.0

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["question_count"] == 2
    assert summary["commit"] == "abc1234"
    assert summary["runs_per_question"] == 3
    assert summary["systems"]["vault"]["hits"] == 1
    assert summary["systems"]["vault"]["hit_rate"] == 0.5
    assert summary["systems"]["vg"]["hit_rate"] == 0.5
    assert summary["systems"]["vault"]["first_seconds_median"] == 1.0
    assert summary["systems"]["vault"]["median_seconds_median"] == 1.0
    assert "첫 질문" not in json.dumps(summary, ensure_ascii=False)


def test_first_run_time_and_median_differ_when_first_run_is_slow(
    dirs: tuple[Path, Path, Path, Path], monkeypatch: MonkeyPatch
) -> None:
    questions, vault, graph_home, out_dir = dirs
    _write_questions(questions, [{"id": "q1", "question": "q", "expected": ["wiki/a.md"]}])
    # Vault runs: 5s, 1s, 2s. vg runs: 1s each.
    ticks = iter([0.0, 5.0, 5.0, 6.0, 6.0, 8.0, 10.0, 11.0, 11.0, 12.0, 12.0, 13.0])
    monkeypatch.setattr(
        subprocess, "run", FakeProcesses(lambda argv: (0, VAULT_TEXT if _is_vault(argv) else _vg_json()))
    )
    monkeypatch.setattr(time, "perf_counter", ticks.__next__)

    parity.main(questions, vault, graph_home, out_dir)

    row = json.loads((out_dir / "results.jsonl").read_text(encoding="utf-8"))
    assert row["vault"]["seconds"] == [5.0, 1.0, 2.0]
    assert row["vault"]["first_seconds"] == 5.0
    assert row["vault"]["median_seconds"] == 2.0


def test_vault_execution_failure_is_counted_separately_from_misses(
    dirs: tuple[Path, Path, Path, Path], monkeypatch: MonkeyPatch
) -> None:
    questions, vault, graph_home, out_dir = dirs
    _write_questions(
        questions,
        [
            {"id": "q1", "question": "fails", "expected": ["wiki/a.md"]},
            {"id": "q2", "question": "garbled", "expected": ["wiki/a.md"]},
            {"id": "q3", "question": "timeout", "expected": ["wiki/a.md"]},
            {"id": "q4", "question": "misses", "expected": ["wiki/none.md"]},
        ],
    )

    def respond(argv: Sequence[str]) -> tuple[int, str]:
        if not _is_vault(argv):
            return 0, _vg_json("wiki/a.md")
        if "fails" in argv:
            return 1, ""
        if "garbled" in argv:
            return 0, "Traceback\n"
        if "timeout" in argv:
            raise subprocess.TimeoutExpired(list(argv), 1)
        return 0, VAULT_TEXT

    monkeypatch.setattr(subprocess, "run", FakeProcesses(respond))

    parity.main(questions, vault, graph_home, out_dir)

    rows = [json.loads(line) for line in (out_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [row["vault"]["outcome"] for row in rows] == ["failed", "failed", "failed", "miss"]
    assert all(row["vault"]["error"] for row in rows[:3])
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["systems"]["vault"]["hits"] == 0
    assert summary["systems"]["vault"]["misses"] == 1
    assert summary["systems"]["vault"]["failures"] == 3
    assert summary["systems"]["vault"]["hit_rate"] == 0.0
    assert summary["systems"]["vg"]["hits"] == 3
    assert summary["systems"]["vg"]["misses"] == 1
    assert summary["systems"]["vg"]["failures"] == 0
    assert summary["judgment_blocked"] is True


def test_failure_in_a_later_run_marks_the_question_failed(
    dirs: tuple[Path, Path, Path, Path], monkeypatch: MonkeyPatch
) -> None:
    questions, vault, graph_home, out_dir = dirs
    _write_questions(questions, [{"id": "q1", "question": "q", "expected": ["wiki/a.md"]}])
    vault_runs = iter([0, 0, 2])

    def respond(argv: Sequence[str]) -> tuple[int, str]:
        if _is_vault(argv):
            return next(vault_runs), VAULT_TEXT
        return 0, _vg_json("wiki/a.md")

    monkeypatch.setattr(subprocess, "run", FakeProcesses(respond))

    parity.main(questions, vault, graph_home, out_dir)

    row = json.loads((out_dir / "results.jsonl").read_text(encoding="utf-8"))
    assert row["vault"]["outcome"] == "failed"
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["judgment_blocked"] is True
    assert summary["systems"]["vg"]["hit_rate"] == 1.0


@pytest.mark.parametrize(
    "line",
    [
        "not json",
        json.dumps({"id": "q1", "question": "q"}),
        json.dumps({"id": "q1", "question": "", "expected": ["wiki/a.md"]}),
        json.dumps({"id": "q1", "question": "q", "expected": "wiki/a.md"}),
        json.dumps({"id": "q1", "question": "q", "expected": []}),
    ],
)
def test_invalid_question_file_is_rejected(line: str, dirs: tuple[Path, Path, Path, Path]) -> None:
    questions, vault, graph_home, out_dir = dirs
    questions.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        parity.main(questions, vault, graph_home, out_dir)
    assert not out_dir.exists()


def test_duplicate_question_ids_are_rejected(dirs: tuple[Path, Path, Path, Path]) -> None:
    questions, vault, graph_home, out_dir = dirs
    row = {"id": "q1", "question": "q", "expected": ["wiki/a.md"]}
    _write_questions(questions, [row, row])
    with pytest.raises(ValueError):
        parity.main(questions, vault, graph_home, out_dir)


def test_out_dir_and_questions_inside_the_repository_are_rejected(dirs: tuple[Path, Path, Path, Path]) -> None:
    questions, vault, graph_home, _ = dirs
    _write_questions(questions, [{"id": "q1", "question": "q", "expected": ["wiki/a.md"]}])
    repo_root = Path(parity.__file__).resolve().parents[2]
    with pytest.raises(ValueError):
        parity.main(questions, vault, graph_home, repo_root / "measure-out")
    assert not (repo_root / "measure-out").exists()
    inside_questions = repo_root / "tests" / "fixtures" / "questions.jsonl"
    with pytest.raises(ValueError):
        parity.main(inside_questions, vault, graph_home, questions.parent / "out")
