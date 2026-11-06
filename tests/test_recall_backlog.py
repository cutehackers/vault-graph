"""Cleanup backlog line in recall block D (spec 2026-11-05 §4.4.6, §4.4.4, A-26)."""

from __future__ import annotations

import shutil
import time
from dataclasses import replace
from pathlib import Path

from pytest import MonkeyPatch

from tests.test_memory_candidates_merge_retire import (  # noqa: F401  (pytest fixture)
    BACKLOG_KINDS,
    _Project,
    _tree_hashes,
    project,
)
from tests.test_recall_budget import blocks, check_limits, crowded
from tests.test_session_recall import CWD, doc, ports, run
from vault_graph.context.pack.recall import recall
from vault_graph.context.pack.recall_backlog import MemoryBacklog, backlog_line
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.interface.composition.memory_candidate_sources import (
    CandidateBacklogCounter,
    memory_candidate_package,
)
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory

LINE = '- 정리 대기: L1 노트 3개, 근거로 쓰이지 않은 세션 교환 5개. 정리하려면 "기억 정리해"라고 말하세요.'


class FakeCounter:
    def __init__(self, backlog: MemoryBacklog | None = None, *, delay_s: float = 0.0, error: Exception | None = None):
        self.backlog = backlog or MemoryBacklog(l1_notes=0, session_exchanges=0)
        self.delay_s = delay_s
        self.error = error
        self.calls: list[Path] = []

    def count(self, cwd: Path) -> MemoryBacklog:
        self.calls.append(cwd)
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return self.backlog


def _documents() -> tuple[DocumentSnapshot, ...]:
    return (doc("wiki/decisions/a.md", title="A", type="decision"),)


def test_line_text_matches_the_spec() -> None:
    assert backlog_line(MemoryBacklog(l1_notes=3, session_exchanges=5)) == LINE


def test_no_line_when_both_counts_are_zero() -> None:
    assert backlog_line(MemoryBacklog(l1_notes=0, session_exchanges=0)) is None


def test_unreadable_l1_folder_leaves_the_l1_part_out() -> None:
    line = backlog_line(MemoryBacklog(l1_notes=None, session_exchanges=4))
    assert line == '- 정리 대기: 근거로 쓰이지 않은 세션 교환 4개. 정리하려면 "기억 정리해"라고 말하세요.'
    assert backlog_line(MemoryBacklog(l1_notes=None, session_exchanges=0)) is None


def test_one_nonzero_count_still_gives_the_line_with_both_numbers() -> None:
    line = backlog_line(MemoryBacklog(l1_notes=0, session_exchanges=2))
    assert line is not None
    assert "L1 노트 0개" in line and "세션 교환 2개" in line


def test_recall_puts_the_line_in_block_d() -> None:
    counter = FakeCounter(MemoryBacklog(l1_notes=3, session_exchanges=5))

    bundle = run(replace(ports(_documents()), backlog=counter))

    assert LINE in blocks(bundle.text)["## 가져오는 방법"].splitlines()
    assert counter.calls == [CWD]
    assert bundle.warnings == ()


def test_recall_has_no_line_when_nothing_waits() -> None:
    bundle = run(replace(ports(_documents()), backlog=FakeCounter()))

    assert "정리 대기" not in bundle.text
    assert bundle.warnings == ()


def test_count_over_the_time_limit_drops_the_line_with_one_warning() -> None:
    counter = FakeCounter(MemoryBacklog(l1_notes=3, session_exchanges=5), delay_s=1.0)

    started = time.monotonic()
    bundle = run(replace(ports(_documents()), backlog=counter, backlog_budget_s=0.05))

    assert time.monotonic() - started < 0.9
    assert "정리 대기" not in bundle.text
    assert len(bundle.warnings) == 1
    assert "time limit" in bundle.warnings[0]


def test_count_error_drops_the_line_with_one_warning() -> None:
    counter = FakeCounter(error=OSError("disk gone"))

    bundle = run(replace(ports(_documents()), backlog=counter))

    assert "정리 대기" not in bundle.text
    assert len(bundle.warnings) == 1
    assert "disk gone" in bundle.warnings[0]


def test_counter_warnings_are_passed_on() -> None:
    counter = FakeCounter(MemoryBacklog(l1_notes=1, session_exchanges=0, warnings=("reviewed log broken",)))

    bundle = run(replace(ports(_documents()), backlog=counter))

    assert "정리 대기" in bundle.text
    assert any("reviewed log broken" in warning for warning in bundle.warnings)


def test_resume_does_not_count_the_backlog() -> None:
    counter = FakeCounter(MemoryBacklog(l1_notes=3, session_exchanges=5))

    run(replace(ports(_documents()), backlog=counter), source="resume")

    assert counter.calls == []


def test_blocks_c_and_d_stay_inside_180_tokens_with_the_line() -> None:
    documents, bodies = crowded()
    counter = FakeCounter(MemoryBacklog(l1_notes=12, session_exchanges=40))

    bundle = run(replace(ports(documents, bodies=bodies, proposals={"main": 3}), backlog=counter))

    found = check_limits(bundle)
    assert "정리 대기" in found["## 가져오는 방법"]
    assert found["## 변경 알림"].count("\n- ") >= 1


def test_line_counts_match_the_full_cleanup_package_and_recall_writes_no_vault_or_l1_file(
    project: _Project,  # noqa: F811
    monkeypatch: MonkeyPatch,
) -> None:
    for name, value in project.environ.items():
        monkeypatch.setenv(name, value)
    map_file = Path(project.environ["VAULT_GRAPH_VAULT_MAP"])
    full = memory_candidate_package(project.graph_home, project.repo)
    expected = MemoryBacklog(l1_notes=full.count("l1_note"), session_exchanges=full.count("session_exchange"))
    assert expected.l1_notes and expected.session_exchanges
    before = _tree_hashes(project.vault, project.memory)

    recall_ports = ReadOnlyServiceFactory(graph_home_path=project.graph_home).open_session_recall(
        vault_map_path=map_file
    )
    counter = CandidateBacklogCounter(graph_home=project.graph_home, vault_map_path=map_file)
    bundle = recall(project.repo, source="startup", session_id="s-1", ports=replace(recall_ports, backlog=counter))

    line = backlog_line(expected)
    assert line is not None
    assert line in blocks(bundle.text)["## 가져오는 방법"].splitlines()
    assert _tree_hashes(project.vault, project.memory) == before


def _no_search_or_embeddings(monkeypatch: MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> object:
        raise AssertionError("search or embeddings were opened")

    monkeypatch.setattr(ReadOnlyServiceFactory, "open_retrieval_service", refuse)
    monkeypatch.setattr("vault_graph.interface.composition.adapters.text_embeddings.text_embeddings_for", refuse)


def test_package_without_comparison_has_the_same_candidates_and_opens_no_search(
    project: _Project,  # noqa: F811
    monkeypatch: MonkeyPatch,
) -> None:
    kinds = (*BACKLOG_KINDS, "retire")
    with_material = memory_candidate_package(project.graph_home, project.repo, environ=project.environ, kinds=kinds)
    assert any(candidate.comparison for candidate in with_material.candidates)
    _no_search_or_embeddings(monkeypatch)

    without = memory_candidate_package(
        project.graph_home, project.repo, environ=project.environ, kinds=kinds, with_comparison=False
    )

    assert [(c.key, c.kind, c.location) for c in without.candidates] == [
        (c.key, c.kind, c.location) for c in with_material.candidates
    ]
    assert all(candidate.comparison == () for candidate in without.candidates)


def test_backlog_counter_counts_like_the_full_package_without_search_or_embeddings(
    project: _Project,  # noqa: F811
    monkeypatch: MonkeyPatch,
) -> None:
    full = memory_candidate_package(project.graph_home, project.repo, environ=project.environ)
    _no_search_or_embeddings(monkeypatch)
    map_file = Path(project.environ["VAULT_GRAPH_VAULT_MAP"])

    counted = CandidateBacklogCounter(
        graph_home=project.graph_home, vault_map_path=map_file, environ=project.environ
    ).count(project.repo)

    assert (counted.l1_notes, counted.session_exchanges) == (full.count("l1_note"), full.count("session_exchange"))
    assert counted.warnings == ()


def test_backlog_counter_reports_a_missing_l1_folder(
    project: _Project,  # noqa: F811
) -> None:
    shutil.rmtree(project.memory)
    map_file = Path(project.environ["VAULT_GRAPH_VAULT_MAP"])

    counted = CandidateBacklogCounter(
        graph_home=project.graph_home, vault_map_path=map_file, environ=project.environ
    ).count(project.repo)

    assert counted.l1_notes is None
    assert counted.session_exchanges == 1
    assert len(counted.warnings) == 1
    assert "L1 memory folder" in counted.warnings[0]


def test_l1_folder_problem_names_a_missing_and_an_unreadable_folder(tmp_path: Path) -> None:
    from vault_graph.interface.composition.adapters.auto_memory_reader import memory_folder_problem

    folder = tmp_path / "memory"
    assert "does not exist" in (memory_folder_problem(folder) or "")
    folder.mkdir()
    assert memory_folder_problem(folder) is None
    folder.chmod(0)
    try:
        assert "cannot be read" in (memory_folder_problem(folder) or "")
    finally:
        folder.chmod(0o755)
