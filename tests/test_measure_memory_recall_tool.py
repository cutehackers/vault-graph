"""The memory quality measurement tool (spec 2026-11-05 §4.4.10, A-28 tool part)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tests.benchmarks import measure_memory_recall as tool
from tests.test_cli_hook_session_start import FIXTURES, l1_folder, render
from vault_graph.context.memory.memory_candidates import CandidateKind
from vault_graph.context.pack.recall import memory_item_id
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.memory_candidate_sources import memory_candidate_package

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def question_line(**overrides: object) -> str:
    row: dict[str, object] = {
        "id": "q1",
        "question": "which database",
        "cwd": "/work/alpha",
        "expected_pages": ["main:wiki/decisions/use-sqlite.md"],
        "axis": "정보 추출",
    }
    row.update(overrides)
    return json.dumps(row, ensure_ascii=False) + "\n"


# Parsing ---------------------------------------------------------------------------------------


def test_page_reference_is_vault_colon_path() -> None:
    assert tool.parse_page_ref("main:wiki/a.md") == tool.PageRef("main", "wiki/a.md")
    for bad in ("wiki/a.md", ":wiki/a.md", "main:", "main: wiki/a.md"):
        with pytest.raises(ValueError):
            tool.parse_page_ref(bad)


def test_questions_need_id_question_cwd_pages_and_a_known_axis(tmp_path: Path) -> None:
    path = tmp_path / "q.jsonl"
    path.write_text(question_line() + "\n" + question_line(id="q2", axis="답하지 않기", expected_pages=[]))

    loaded = tool.load_questions(path)

    expected = (tool.PageRef("main", "wiki/decisions/use-sqlite.md"),)
    assert loaded[0] == tool.Question("q1", "which database", Path("/work/alpha"), expected, "정보 추출")
    assert loaded[1].expected == ()
    for broken in (
        question_line(axis="unknown"),
        question_line(cwd="relative/path"),
        question_line(expected_pages=[]),  # only 답하지 않기 may have no answer page
        question_line(expected_pages=["wiki/a.md"]),
        question_line(question=" "),
        question_line() + question_line(),  # duplicate id
    ):
        path.write_text(broken, encoding="utf-8")
        with pytest.raises(ValueError):
            tool.load_questions(path)


def test_every_axis_of_the_spec_is_accepted() -> None:
    assert tool.AXES == (
        "정보 추출",
        "여러 세션 추론",
        "시간 추론",
        "지식 갱신",
        "답하지 않기",
        "프로젝트 섞임",
        "대체된 결정 사용",
    )


RECALL_TEXT = """## 고정 기억
- [m:00000001] rule · Team rule (other:wiki/rules/team-rule.md)
  Summary of Team rule
## 프로젝트 요약
Brief start (main:wiki/projects/alpha.md)
### 현재 결정
- Use (SQLite) now (main:wiki/decisions/use-sqlite.md, 2026-11-05)
  - Keep one file
## 기억 목록
- [m:00000002] decision · 2026-11-05 · active · Use SQLite (main:wiki/decisions/use-sqlite.md, ~9t)
- [m:00000003] workflow · 2026-11-01 · active · Alpha flow (wiki/workflows/alpha-flow.md, ~9t)
- 2개 생략
## 변경 알림
- [m:00000004] Old choice → Use SQLite (2026-11-05) (main:wiki/decisions/old-choice.md)
## 가져오는 방법
- 본문은 MCP 리소스 `vault://{vault_id}/pages/{path}`로 연다.
"""


def test_recall_locations_skip_the_change_notice_block_and_repeat_nothing() -> None:
    assert tool.recall_locations(RECALL_TEXT) == (
        ("other", "wiki/rules/team-rule.md"),
        ("main", "wiki/projects/alpha.md"),
        ("main", "wiki/decisions/use-sqlite.md"),
        (None, "wiki/workflows/alpha-flow.md"),
    )
    assert "Old choice" not in tool.injected_text(RECALL_TEXT)
    assert "Keep one file" in tool.injected_text(RECALL_TEXT)


def test_context_pack_pages_come_from_evidence_in_order() -> None:
    body = {
        "payload": {
            "evidence": [
                {"ref": {"vault_id": "main", "document_id": "d1", "chunk_id": "c1"}, "path": "wiki/b.md"},
                {"ref": {"vault_id": "main", "document_id": "d2", "chunk_id": "c2"}, "path": "wiki/a.md"},
                {"ref": {"vault_id": "main", "document_id": "d1", "chunk_id": "c3"}, "path": "wiki/b.md"},
            ]
        }
    }
    assert tool.context_pages(body) == (("main", "wiki/b.md"), ("main", "wiki/a.md"))
    with pytest.raises(ValueError):
        tool.context_pages({"payload": {"error": "no project"}})


# Scoring ---------------------------------------------------------------------------------------


def facts(
    status: str | None = "active", *, in_project: bool = True, sharable: bool = True, superseded: tuple[str, ...] = ()
) -> tool.PageFacts:
    return tool.PageFacts(status=status, in_project=in_project, sharable=sharable, superseded_claims=superseded)


def by_label(label: str | None) -> str:
    return label or "main"


def test_metric_1_counts_retired_pages_and_shown_superseded_claims() -> None:
    table = {
        ("other", "wiki/rules/team-rule.md"): facts("retired"),
        ("main", "wiki/projects/alpha.md"): facts(superseded=("Keep one file", "Never shown claim")),
        ("main", "wiki/decisions/use-sqlite.md"): facts("superseded"),
        ("main", "wiki/workflows/alpha-flow.md"): facts("contested"),
    }

    score = tool.score_injection(RECALL_TEXT, resolve=by_label, facts=table.get)

    assert score == tool.InjectionScore(pages=4, unresolved=0, stale_pages=2, superseded_claims=1, unsharable_other=0)
    assert score.metric1 == 3


def test_metric_2_counts_pages_of_other_projects_from_unsharable_vaults_only() -> None:
    table = {
        ("other", "wiki/rules/team-rule.md"): facts(in_project=False, sharable=False),
        ("main", "wiki/projects/alpha.md"): facts(in_project=False, sharable=True),
        ("main", "wiki/decisions/use-sqlite.md"): facts(),
    }

    score = tool.score_injection(RECALL_TEXT, resolve=by_label, facts=table.get)

    assert score.pages == 4 and score.unresolved == 1  # alpha-flow is not in the table
    assert score.unsharable_other == 1
    assert score.metric2 == 0.25


def test_expected_pages_are_found_by_vault_id_after_name_resolution() -> None:
    expected = (tool.PageRef("main", "wiki/a.md"), tool.PageRef("personal", "wiki/b.md"))
    names = {"main": "main", "personal": "p1"}
    resolved = tool.resolve_expected(expected, resolve=lambda label: names.get(label or ""))
    assert resolved == (("main", "wiki/a.md"), ("p1", "wiki/b.md"))
    with pytest.raises(ValueError, match="unknown Vault"):
        tool.resolve_expected((tool.PageRef("ghost", "wiki/a.md"),), resolve=lambda label: None)
    assert tool.first_rank(resolved, (("main", "wiki/z.md"), ("p1", "wiki/b.md"))) == 2
    assert tool.first_rank(resolved, ()) is None


def test_metric_3_counts_injected_items_later_opened_and_skips_the_tool_runs() -> None:
    def event(kind: str, item: str, at: datetime, **extra: object) -> dict[str, object]:
        return {"event": kind, "item_id": item, "at": at.isoformat(), **extra}

    events = [
        event("injected", "m:a", NOW, project="alpha", session_id="s1"),
        event("injected", "m:b", NOW, project="alpha", session_id="s1"),
        event("injected", "m:c", NOW, project="beta", session_id="s1"),
        event("injected", "m:d", NOW, project="alpha", session_id=tool.SESSION_ID),
        event("fetched", "m:a", NOW + timedelta(minutes=1)),
        event("fetched", "m:b", NOW - timedelta(minutes=1)),  # opened before it was injected
        event("fetched", "m:d", NOW + timedelta(minutes=1)),
    ]

    assert tool.open_ratio(events, project_id="alpha") == {"injected_items": 2, "opened_items": 1, "ratio": 0.5}
    assert tool.open_ratio([], project_id="alpha") == {"injected_items": 0, "opened_items": 0, "ratio": None}


def test_metric_4_reads_memory_proposals_of_the_review_queue(tmp_path: Path) -> None:
    queue = tmp_path / "scratch" / "review"
    queue.mkdir(parents=True)
    for name, kind, status in (
        ("a", "memory-proposal", "accepted"),
        ("b", "memory-proposal", "accepted"),
        ("c", "memory-proposal", "rejected"),
        ("d", "memory-proposal", "pending"),
        ("e", "contradiction", "accepted"),
    ):
        (queue / f"{name}.md").write_text(f"---\nreview_id: {name}\ntype: {kind}\nstatus: {status}\n---\n# {name}\n")

    counts = tool.proposal_counts(tmp_path)

    assert counts == {"accepted": 2, "rejected": 1, "pending": 1, "resolved": 0}
    assert tool.acceptance_rate([counts, {"accepted": 0, "rejected": 1, "pending": 0, "resolved": 0}]) == {
        "accepted": 2,
        "rejected": 2,
        "pending": 1,
        "resolved": 0,
        "rate": 0.5,
    }
    assert tool.proposal_counts(tmp_path / "missing") == {"accepted": 0, "rejected": 0, "pending": 0, "resolved": 0}


def test_metric_5_is_the_age_of_waiting_session_exchanges_in_days() -> None:
    started = (NOW - timedelta(days=10), NOW - timedelta(days=2), NOW - timedelta(days=4), None)
    ages = tool.backlog_ages(started, now=NOW)
    assert ages == (10.0, 2.0, 4.0)
    assert tool.backlog_age(ages) == {"exchanges": 3, "oldest_days": 10.0, "median_days": 4.0}
    assert tool.backlog_age(()) == {"exchanges": 0, "oldest_days": None, "median_days": None}


def test_summary_holds_totals_and_the_gate_without_question_text() -> None:
    scores = [
        tool.QuestionScore("q1", "정보 추출", "alpha", 1, 1, 1, 1, 0.5, None),
        tool.QuestionScore("q2", "정보 추출", "alpha", 1, 0, 1, 3, 0.5, None),
        tool.QuestionScore("q3", "시간 추론", "alpha", 2, 0, 0, None, 0.5, None),
        tool.QuestionScore("q4", "답하지 않기", "alpha", 0, 0, 0, None, 0.5, None),
        tool.QuestionScore("q5", "지식 갱신", "alpha", 1, None, None, None, 0.1, "vg exited 1"),
    ]
    project = tool.ProjectReport(
        project="alpha",
        error=None,
        injection=tool.InjectionScore(pages=8, unresolved=0, stale_pages=0, superseded_claims=0, unsharable_other=0),
        usage={"injected_items": 4, "opened_items": 1, "ratio": 0.25},
        backlog_ages=(5.0, 1.0),
        merge_candidates=1,
        warnings=(),
    )

    summary = tool.summarize(scores, [project], proposals=[{"accepted": 1, "rejected": 1, "pending": 0, "resolved": 0}])

    assert summary["questions"] == 5 and summary["failed"] == 1 and summary["scored"] == 3
    assert summary["recall_hit_rate"] == round(1 / 3, 4)
    assert summary["context_hit_rate"] == round(2 / 3, 4)
    assert summary["either_hit_rate"] == round(2 / 3, 4)
    assert summary["by_axis"] == {
        "정보 추출": {"questions": 2, "recall_hit_rate": 0.5, "context_hit_rate": 1.0},
        "시간 추론": {"questions": 1, "recall_hit_rate": 0.0, "context_hit_rate": 0.0},
        "답하지 않기": {"questions": 1, "recall_hit_rate": None, "context_hit_rate": None},
    }
    assert summary["metric1_stale_injections"] == 0
    assert summary["metric2_unsharable_other_project_share"] == 0.0
    assert summary["metric3_open_ratio"] == {"injected_items": 4, "opened_items": 1, "ratio": 0.25}
    assert summary["metric4_inferred_acceptance"] == {
        "accepted": 1,
        "rejected": 1,
        "pending": 0,
        "resolved": 0,
        "rate": 0.5,
    }
    assert summary["metric5_backlog_age"] == {"exchanges": 2, "oldest_days": 5.0, "median_days": 3.0}
    assert summary["metric6_merge_candidates"] == 1
    assert summary["gate_passed"] is True
    assert "which" not in json.dumps(summary, ensure_ascii=False)


def test_gate_fails_on_a_stale_injection_or_a_failed_project() -> None:
    stale = tool.ProjectReport(
        "alpha",
        None,
        tool.InjectionScore(pages=2, unresolved=0, stale_pages=1, superseded_claims=0, unsharable_other=0),
        {},
        (),
        0,
        (),
    )
    failed = tool.ProjectReport("beta", "hook exited 3", None, {}, (), 0, ())
    assert tool.summarize([], [stale], proposals=[])["gate_passed"] is False
    assert tool.summarize([], [failed], proposals=[])["gate_passed"] is False


def test_question_file_and_output_must_be_outside_the_repository(tmp_path: Path) -> None:
    inside = tool.REPO_ROOT / "tests" / "fixtures"
    with pytest.raises(ValueError, match="outside"):
        tool.main(inside / "q.jsonl", graph_home=tmp_path, vault_map=tmp_path / "m.json", out_dir=tmp_path / "out")
    with pytest.raises(ValueError, match="outside"):
        tool.main(tmp_path / "q.jsonl", graph_home=tmp_path, vault_map=tmp_path / "m.json", out_dir=inside / "out")


# End to end ------------------------------------------------------------------------------------


@pytest.fixture
def fixture_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The session recall fixture Vaults and map, indexed without vectors (the subprocesses use keywords).

    The in-process merge rule embeds with deterministic vectors, so metric 6 does not need a model.
    """
    from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
    from tests.test_vector_indexer import SPEC

    def embeddings(*_: object, **__: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _ConfiguredDeterministicTextEmbeddings(SPEC)

    monkeypatch.setattr("vault_graph.interface.composition.adapters.text_embeddings.text_embeddings_for", embeddings)
    root = tmp_path.resolve()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(root / "claude"))
    for source in sorted((FIXTURES / "vaults").rglob("*.md")):
        target = root / "vaults" / source.relative_to(FIXTURES / "vaults")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(source.read_text(encoding="utf-8"), root), encoding="utf-8")
    (root / "map").mkdir()
    (root / "map" / "vault-map.json").write_text(
        render((FIXTURES / "vault-map.json").read_text(encoding="utf-8"), root), encoding="utf-8"
    )
    for repo in ("alpha", "both"):
        (root / "repos" / repo).mkdir(parents=True)
        subprocess.run(["git", "-C", str(root / "repos" / repo), "init", "-q"], check=True)
        l1_folder(root, repo).mkdir(parents=True)
    # A copy of "Use SQLite" with the same title and body: one merge candidate for metric 6.
    sqlite = root / "vaults" / "main" / "wiki" / "decisions" / "use-sqlite.md"
    (sqlite.parent / "use-sqlite-copy.md").write_text(sqlite.read_text(encoding="utf-8"), encoding="utf-8")
    runner = CliRunner()
    home = root / "graph-home"
    for arguments in (
        ["init", "--vault", str(root / "vaults" / "main"), "--vault-id", "main", "--graph-home", str(home)],
        ["vault", "add", "other", "--path", str(root / "vaults" / "other"), "--graph-home", str(home)],
        ["index", "--all-vaults", "--graph-home", str(home), "--no-vector"],
    ):
        result = runner.invoke(app, arguments)
        assert result.exit_code == 0, result.output
    return root


def test_end_to_end_run_on_the_fixture_vaults(fixture_base: Path, tmp_path: Path) -> None:
    home, vault_map = fixture_base / "graph-home", fixture_base / "map" / "vault-map.json"
    queue = fixture_base / "vaults" / "main" / "scratch" / "review"
    queue.mkdir(parents=True)
    for name, status in (("a", "accepted"), ("b", "rejected"), ("c", "accepted")):
        (queue / f"{name}.md").write_text(f"---\nreview_id: {name}\ntype: memory-proposal\nstatus: {status}\n---\n")
    usage = home / "usage"
    usage.mkdir()
    sqlite_item = memory_item_id("main", "wiki/decisions/use-sqlite.md")
    earlier = datetime.now(UTC) - timedelta(days=1)
    (usage / f"{earlier:%Y-%m}.jsonl").write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {"event": "injected", "item_id": sqlite_item, "project": "alpha", "at": earlier.isoformat()},
                {"event": "injected", "item_id": "m:00000000", "project": "alpha", "at": earlier.isoformat()},
                {"event": "fetched", "item_id": sqlite_item, "at": (earlier + timedelta(minutes=1)).isoformat()},
            )
        ),
        encoding="utf-8",
    )
    questions = tmp_path / "questions.jsonl"
    alpha, both = str(fixture_base / "repos" / "alpha"), str(fixture_base / "repos" / "both")
    questions.write_text(
        question_line(id="sqlite", question="Use SQLite", cwd=alpha)
        + question_line(
            id="team",
            question="Other vault decision",
            cwd=both,
            expected_pages=["other:wiki/decisions/other-decision.md"],
        )
        + question_line(id="beta", question="Beta flow", cwd=alpha, expected_pages=["main:wiki/workflows/beta-flow.md"])
        + question_line(id="none", question="Kubernetes cluster", cwd=alpha, axis="답하지 않기", expected_pages=[]),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    summary = tool.main(questions, graph_home=home, vault_map=vault_map, out_dir=out)

    rows = {row["id"]: row for row in map(json.loads, (out / "results.jsonl").read_text().splitlines())}
    assert all(row["error"] is None for row in rows.values()), rows
    assert (rows["sqlite"]["recall_found"], rows["sqlite"]["context_found"]) == (1, 1)
    assert (rows["team"]["recall_found"], rows["team"]["context_found"]) == (1, 1)
    # Beta flow belongs to project beta: never recalled for alpha, still searchable.
    assert (rows["beta"]["recall_found"], rows["beta"]["context_found"]) == (0, 1)
    assert summary["failed"] == 0 and summary["projects"] == 2
    assert summary["metric1_stale_injections"] == 0
    assert summary["metric2_unsharable_other_project_share"] == 0.0
    assert summary["metric3_open_ratio"] == {"injected_items": 2, "opened_items": 1, "ratio": 0.5}
    assert summary["metric4_inferred_acceptance"] == {
        "accepted": 2,
        "rejected": 1,
        "pending": 0,
        "resolved": 0,
        "rate": round(2 / 3, 4),
    }
    assert summary["metric5_backlog_age"] == {"exchanges": 0, "oldest_days": None, "median_days": None}
    merge_kind: tuple[CandidateKind, ...] = ("merge",)
    merges = sum(
        memory_candidate_package(
            home, Path(cwd), kinds=merge_kind, vault_map_file=vault_map, with_comparison=False
        ).count("merge")
        for cwd in (alpha, both)
    )
    assert merges >= 1
    assert summary["metric6_merge_candidates"] == merges
    assert summary["gate_passed"] is True
    projects = [json.loads(line) for line in (out / "projects.jsonl").read_text().splitlines()]
    assert sorted(project["project"] for project in projects) == ["alpha", "both"]
    written = (out / "summary.json").read_text(encoding="utf-8") + (out / "results.jsonl").read_text(encoding="utf-8")
    assert "Kubernetes" not in written and "Use SQLite" not in written
