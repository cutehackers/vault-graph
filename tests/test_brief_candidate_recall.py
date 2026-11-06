"""Brief update line in recall block D and the ``brief`` cleanup candidate (spec 2026-11-05 §4.4.7, A-35)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from pytest import MonkeyPatch
from typer.testing import CliRunner

from tests.test_memory_candidates_merge_retire import (  # noqa: F401  (pytest fixture)
    NOW,
    FakeFinder,
    _Project,
    _tree_hashes,
    _write,
    project,
)
from tests.test_recall_backlog import FakeCounter
from tests.test_recall_budget import blocks, check_limits, crowded
from tests.test_session_recall import doc, ports, run
from vault_graph.context.memory.brief import BriefStaleness, project_brief_staleness
from vault_graph.context.memory.memory_candidates import CandidateKind, MemoryCandidate, build_memory_candidates
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.context.pack.recall import recall
from vault_graph.context.pack.recall_backlog import MemoryBacklog, brief_staleness_line
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.memory_candidate_sources import memory_candidate_package
from vault_graph.interface.composition.read_only_service_factory import ReadOnlyServiceFactory

BRIEF = "wiki/projects/alpha.md"
D_TITLE = "## 가져오는 방법"
BRIEF_KINDS: tuple[CandidateKind, ...] = ("brief",)
SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"alpha"}))


def _line(count: int) -> str:
    return f'- brief 갱신 필요: brief 이후 새 결정 {count}개. "기억 정리해"로 갱신하세요.'


def _decisions(count: int, *, prefix: str = "d", day: str = "2026-10-20") -> tuple[DocumentSnapshot, ...]:
    return tuple(
        doc(f"wiki/decisions/{prefix}{index}.md", title=f"결정 {index}", type="decision", updated=day)
        for index in range(count)
    )


def _brief(updated: str = "2026-10-10", **frontmatter: Any) -> DocumentSnapshot:
    return doc(BRIEF, title="alpha brief", type="project", project="alpha", updated=updated, **frontmatter)


# Block D line ---------------------------------------------------------------------------------


def test_line_text_matches_the_spec() -> None:
    assert brief_staleness_line(BriefStaleness(brief=None, new_decisions=_decisions(5), threshold=5)) == _line(5)
    assert brief_staleness_line(BriefStaleness(brief=None, new_decisions=_decisions(4), threshold=5)) is None


def test_recall_puts_the_line_once_in_block_d_after_the_brief() -> None:
    bundle = run(ports((_brief(), *_decisions(6))))

    block_d = blocks(bundle.text)[D_TITLE].splitlines()
    assert block_d.count(_line(6)) == 1
    assert bundle.text.count("brief 갱신 필요") == 1
    assert bundle.warnings == ()


def test_recall_puts_the_line_without_a_brief() -> None:
    bundle = run(ports(_decisions(5)))

    assert _line(5) in blocks(bundle.text)[D_TITLE].splitlines()


def test_no_line_under_the_threshold_or_after_the_brief_update() -> None:
    assert "brief 갱신 필요" not in run(ports(_decisions(4))).text
    assert "brief 갱신 필요" not in run(ports((_brief("2026-10-25"), *_decisions(6)))).text


def test_resume_has_no_brief_line() -> None:
    assert "brief 갱신 필요" not in run(ports(_decisions(6)), source="resume").text


def test_recall_without_a_project_has_no_brief_line() -> None:
    bundle = run(ports(_decisions(6), project_id=None))

    assert "brief 갱신 필요" not in bundle.text


def test_line_follows_the_cleanup_line_and_blocks_c_and_d_stay_inside_180_tokens() -> None:
    documents, bodies = crowded()
    counter = FakeCounter(MemoryBacklog(l1_notes=12, session_exchanges=40))

    bundle = run(replace(ports(documents, bodies=bodies, proposals={"main": 3}), backlog=counter))

    found = check_limits(bundle)
    block_d = found[D_TITLE].splitlines()
    cleanup = next(index for index, line in enumerate(block_d) if line.startswith("- 정리 대기"))
    brief = next(index for index, line in enumerate(block_d) if line.startswith("- brief 갱신 필요"))
    assert cleanup < brief


def test_recall_reads_no_brief_body() -> None:
    bundle = run(ports((_brief(), *_decisions(6)), bodies={f"main:{BRIEF}": "# alpha\n\n목표는 그대로다.\n"}))

    assert _line(6) in bundle.text


# Cleanup candidate ----------------------------------------------------------------------------


def _candidates(
    documents: tuple[DocumentSnapshot, ...], *, reviewed: frozenset[str] = frozenset(), with_comparison: bool = True
) -> tuple[MemoryCandidate, ...]:
    finder = FakeFinder()
    candidates = build_memory_candidates(
        project_id="alpha",
        l1_notes=(),
        imported_raw_sha256=frozenset(),
        exchanges=(),
        wiki_pages=(),
        reviewed_keys=reviewed,
        similar_pages=finder,
        now=NOW,
        brief=project_brief_staleness({"main": documents}, project_id="alpha", vault_scopes={"main": SCOPE}),
        with_comparison=with_comparison,
    )
    assert finder.queries == []
    return candidates


def test_candidate_key_location_and_new_decisions_as_comparison_material() -> None:
    documents = (_brief(), *_decisions(5), *_decisions(2, prefix="old", day="2026-10-01"))

    (candidate,) = _candidates(documents)

    assert candidate.kind == "brief"
    assert candidate.key.startswith("brief:alpha:")
    assert len(candidate.key.removeprefix("brief:alpha:")) == 12
    assert candidate.location == BRIEF
    assert [page.path for page in candidate.targets] == [BRIEF]
    assert [page.path for page in candidate.comparison] == [f"wiki/decisions/d{index}.md" for index in range(5)]
    assert all(page.evidence_date == "2026-10-20" for page in candidate.comparison)
    assert candidate.reasons == ("brief 이후 새 결정 5개",)


def test_candidate_without_a_brief_has_no_target() -> None:
    (candidate,) = _candidates(_decisions(5))

    assert candidate.location == BRIEF
    assert candidate.targets == ()
    assert len(candidate.comparison) == 5


def test_no_candidate_under_the_threshold() -> None:
    assert _candidates((_brief(), *_decisions(4))) == ()


def test_new_decision_changes_the_key_so_a_skipped_candidate_comes_back() -> None:
    documents = (_brief(), *_decisions(5))
    (first,) = _candidates(documents)

    assert _candidates(documents, reviewed=frozenset({first.key})) == ()
    (again,) = _candidates((*documents, *_decisions(1, prefix="same-day")), reviewed=frozenset({first.key}))
    assert again.key != first.key


def test_candidate_without_comparison_keeps_its_key() -> None:
    documents = (_brief(), *_decisions(5))
    (full,) = _candidates(documents)
    (bare,) = _candidates(documents, with_comparison=False)

    assert (bare.key, bare.location) == (full.key, full.location)
    assert bare.comparison == ()


def test_brief_comes_last_in_table_order() -> None:
    from vault_graph.context.memory.memory_candidates import CANDIDATE_KINDS

    assert CANDIDATE_KINDS[-1] == "brief"


# Real Vault and index -------------------------------------------------------------------------


runner = CliRunner()


def _index(graph_home: Path) -> None:
    result = runner.invoke(app, ["index", "--graph-home", str(graph_home)])
    assert result.exit_code == 0, result.output


def test_package_and_recall_on_a_real_index_and_vg_writes_no_vault_file(
    project: _Project,  # noqa: F811
    monkeypatch: MonkeyPatch,
) -> None:
    for name, value in project.environ.items():
        monkeypatch.setenv(name, value)
    # The fixture has two decisions. Three more reach the threshold without a brief.
    for index in range(3):
        _write(
            project.vault,
            f"wiki/decisions/more-{index}.md",
            f"---\ntitle: 결정 {index}\ntype: decision\nstatus: active\nupdated: 2026-11-0{index + 2}\n---\n# 결정\n",
        )
    _index(project.graph_home)
    map_file = Path(project.environ["VAULT_GRAPH_VAULT_MAP"])
    before = _tree_hashes(project.vault, project.memory)

    package = memory_candidate_package(project.graph_home, project.repo, environ=project.environ, kinds=BRIEF_KINDS)
    recall_ports = ReadOnlyServiceFactory(graph_home_path=project.graph_home).open_session_recall(
        vault_map_path=map_file
    )
    bundle = recall(project.repo, source="startup", session_id="s-1", ports=recall_ports, now=NOW)

    (candidate,) = package.candidates
    assert candidate.key.startswith("brief:demo:")
    assert candidate.location == "wiki/projects/demo.md"
    assert len(candidate.comparison) == 5
    assert blocks(bundle.text)[D_TITLE].count("brief 갱신 필요: brief 이후 새 결정 5개") == 1
    assert _tree_hashes(project.vault, project.memory) == before

    # The agent writes the brief through the Vault tools (simulated here), then the index catches up.
    _write(
        project.vault,
        "wiki/projects/demo.md",
        "---\ntitle: demo\ntype: project\nproject: demo\nupdated: 2026-11-06\n---\n# demo\n\n목표.\n",
    )
    _index(project.graph_home)

    after = memory_candidate_package(project.graph_home, project.repo, environ=project.environ, kinds=BRIEF_KINDS)
    # Each session start opens its own ports (a new hook process).
    recall_ports = ReadOnlyServiceFactory(graph_home_path=project.graph_home).open_session_recall(
        vault_map_path=map_file
    )
    bundle = recall(project.repo, source="startup", session_id="s-2", ports=recall_ports, now=NOW)
    assert after.candidates == ()
    assert "brief 갱신 필요" not in bundle.text
