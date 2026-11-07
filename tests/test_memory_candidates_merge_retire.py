"""Cleanup candidates: merge and retire pairs, comparison material, and the composition entry.

Spec 2026-11-05 §4.4.4 (merge and retire rows), §4.4.12 (composition joins the M11 code signal),
§4.4.13-2 (comparison material includes retired pages, marked "폐기됨: <이유>"), risk D10,
A-22 (merge and retire), A-39 (comparison material), A-25 (no automatic retirement).
"""

from __future__ import annotations

import ast
import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

from vault_graph.context.memory.memory_candidates import (
    COMPARISON_PAGE_LIMIT,
    DEFAULT_MERGE_SIMILARITY,
    RETIRE_UNUSED_WINDOW,
    CandidateKind,
    ComparisonPage,
    MemoryCandidate,
    MemoryPage,
    SessionExchange,
    SimilarPage,
    build_memory_candidates,
)
from vault_graph.context.memory.project_scope import FixedVaultProjectScope
from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.auto_memory_reader import memory_folder_key
from vault_graph.interface.composition.memory_candidate_sources import (
    NO_PROJECT_REASON,
    CodeReference,
    ProjectedCode,
    code_references,
    memory_candidate_package,
    missing_code_references,
)

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
PROJECT_SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"demo"}))
OTHER_SCOPE = FixedVaultProjectScope(linked_projects=frozenset({"other"}))
BACKLOG_KINDS: tuple[CandidateKind, ...] = ("l1_note", "session_exchange")
MERGE_ONLY: tuple[CandidateKind, ...] = ("merge",)
RETIRE_ONLY: tuple[CandidateKind, ...] = ("retire",)


@dataclass
class FakeFinder:
    pages: Sequence[SimilarPage] = ()
    queries: list[str] = field(default_factory=list)

    def find_similar(self, query: str, *, limit: int) -> Sequence[SimilarPage]:
        self.queries.append(query)
        return tuple(self.pages[:limit])


def _page(
    path: str,
    *,
    frontmatter: Mapping[str, object] | None = None,
    scope: FixedVaultProjectScope = PROJECT_SCOPE,
    text: str = "본문",
) -> MemoryPage:
    return MemoryPage(
        vault_id="demo-vault",
        path=path,
        title=path.rsplit("/", 1)[-1].removesuffix(".md"),
        frontmatter=frontmatter if frontmatter is not None else {"type": "decision", "status": "active"},
        vault_scope=scope,
        text=text,
        evidence_date="2026-11-01",
    )


def _similar(path: str, frontmatter: Mapping[str, object] | None = None) -> SimilarPage:
    return SimilarPage(
        vault_id="demo-vault",
        path=path,
        title=path.rsplit("/", 1)[-1],
        frontmatter=frontmatter or {"status": "active"},
        vault_scope=PROJECT_SCOPE,
        evidence_date="2026-11-01",
    )


def _injected(path: str, *, days_ago: float) -> dict[str, object]:
    return {
        "event": "injected",
        "vault_id": "demo-vault",
        "path": path,
        "at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def _fetched(path: str, *, days_ago: float) -> dict[str, object]:
    return {
        "event": "fetched",
        "vault_id": "demo-vault",
        "path": path,
        "at": (NOW - timedelta(days=days_ago)).isoformat(),
    }


def _build(
    *,
    pages: Sequence[MemoryPage] = (),
    vectors: Mapping[tuple[str, str], Sequence[float]] | None = None,
    missing_code: Mapping[tuple[str, str], Sequence[str]] | None = None,
    usage: Sequence[Mapping[str, object]] = (),
    reviewed: frozenset[str] = frozenset(),
    finder: FakeFinder | None = None,
    kinds: Sequence[CandidateKind] | None = None,
    threshold: float = DEFAULT_MERGE_SIMILARITY,
    limit: int | None = None,
) -> tuple[MemoryCandidate, ...]:
    return build_memory_candidates(
        project_id="demo",
        l1_notes=(),
        imported_raw_sha256=frozenset(),
        exchanges=(),
        wiki_pages=(),
        reviewed_keys=reviewed,
        similar_pages=finder or FakeFinder(),
        now=NOW,
        limit=limit,
        memory_pages=pages,
        page_vectors=vectors,
        missing_code=missing_code,
        usage_events=usage,
        kinds=kinds,
        merge_threshold=threshold,
    )


# Merge candidates -------------------------------------------------------------------------------


def test_merge_candidate_is_a_pair_of_current_project_pages_above_the_threshold() -> None:
    a, b, c = _page("wiki/decisions/a.md"), _page("wiki/decisions/b.md"), _page("wiki/decisions/c.md")
    vectors = {
        ("demo-vault", a.path): (1.0, 0.0, 0.0),
        ("demo-vault", b.path): (0.99, 0.1, 0.0),
        ("demo-vault", c.path): (0.0, 1.0, 0.0),
    }

    candidates = _build(pages=(c, b, a), vectors=vectors, kinds=("merge",))

    assert [candidate.key for candidate in candidates] == ["merge:wiki/decisions/a.md|wiki/decisions/b.md"]
    merge = candidates[0]
    assert merge.kind == "merge"
    assert merge.location == "wiki/decisions/a.md | wiki/decisions/b.md"
    assert [page.path for page in merge.targets] == ["wiki/decisions/a.md", "wiki/decisions/b.md"]
    assert merge.similarity is not None and merge.similarity >= DEFAULT_MERGE_SIMILARITY


def test_merge_pairs_need_the_same_page_type() -> None:
    # A-23 (2026-11-07): the agent skipped every pair of a concept, decision or workflow page with another
    # kind. Pages of different kinds describe one topic from different sides and are not merged.
    concept = _page("wiki/concepts/a.md", frontmatter={"type": "concept", "status": "active"})
    decision = _page("wiki/decisions/a.md", frontmatter={"type": "decision", "status": "active"})
    other = _page("wiki/decisions/b.md", frontmatter={"type": "decision", "status": "active"})
    vectors = {("demo-vault", page.path): (1.0, 0.0) for page in (concept, decision, other)}

    candidates = _build(pages=(concept, decision, other), vectors=vectors, kinds=("merge",))

    assert [candidate.key for candidate in candidates] == ["merge:wiki/decisions/a.md|wiki/decisions/b.md"]


def test_merge_threshold_is_conservative_and_configurable() -> None:
    assert 0.9 <= DEFAULT_MERGE_SIMILARITY < 1.0
    a, b = _page("wiki/a.md"), _page("wiki/b.md")
    vectors = {("demo-vault", a.path): (1.0, 0.0), ("demo-vault", b.path): (0.8, 0.6)}

    assert _build(pages=(a, b), vectors=vectors, kinds=("merge",)) == ()
    lowered = _build(pages=(a, b), vectors=vectors, kinds=("merge",), threshold=0.75)
    assert [candidate.key for candidate in lowered] == ["merge:wiki/a.md|wiki/b.md"]


def test_merge_skips_retired_pages_other_projects_navigation_pages_and_pages_without_vectors() -> None:
    current = _page("wiki/a.md")
    retired = _page("wiki/retired.md", frontmatter={"status": "retired"})
    other = _page("wiki/other.md", scope=OTHER_SCOPE)
    index = _page("wiki/index.md", frontmatter={"type": "index"})
    no_vector = _page("wiki/novector.md")
    same = (1.0, 0.0)
    vectors = {("demo-vault", page.path): same for page in (current, retired, other, index)}

    assert _build(pages=(current, retired, other, index, no_vector), vectors=vectors, kinds=("merge",)) == ()


def test_merge_pairs_are_ordered_by_similarity_then_key() -> None:
    a, b, c = _page("wiki/a.md"), _page("wiki/b.md"), _page("wiki/c.md")
    vectors = {
        ("demo-vault", a.path): (1.0, 0.0),
        ("demo-vault", b.path): (0.96, 0.28),
        ("demo-vault", c.path): (1.0, 0.0),
    }

    keys = [candidate.key for candidate in _build(pages=(a, b, c), vectors=vectors, kinds=("merge",))]

    assert keys == ["merge:wiki/a.md|wiki/c.md", "merge:wiki/a.md|wiki/b.md", "merge:wiki/b.md|wiki/c.md"]


# Retire candidates ------------------------------------------------------------------------------


def test_retire_candidate_when_cited_code_is_gone() -> None:
    page = _page("wiki/concepts/parser.md")

    candidates = _build(
        pages=(page,),
        missing_code={("demo-vault", page.path): ("src/app/gone.py",)},
        kinds=("retire",),
    )

    assert [candidate.key for candidate in candidates] == ["retire:wiki/concepts/parser.md"]
    retire = candidates[0]
    assert retire.kind == "retire"
    assert retire.location == "wiki/concepts/parser.md"
    assert retire.retire_signals == ("code_gone",)
    assert retire.reasons == ("근거 코드가 등록 저장소에서 사라짐: src/app/gone.py",)


def test_retire_candidate_when_only_injected_and_never_opened_for_90_days() -> None:
    unused, opened = _page("wiki/unused.md"), _page("wiki/opened.md")
    usage = [
        _injected("wiki/other.md", days_ago=100),  # the log reaches back past the window
        _injected(unused.path, days_ago=30),
        _injected(unused.path, days_ago=2),
        _injected(opened.path, days_ago=30),
        _fetched(opened.path, days_ago=29),
    ]

    candidates = _build(pages=(unused, opened), usage=usage, kinds=("retire",))

    assert [candidate.key for candidate in candidates] == ["retire:wiki/unused.md"]
    assert candidates[0].retire_signals == ("unused",)
    assert candidates[0].reasons == ("최근 90일 회상 주입 2회, 열람 0회",)
    assert RETIRE_UNUSED_WINDOW == timedelta(days=90)


def test_unused_signal_needs_a_usage_log_that_covers_the_whole_window() -> None:
    page = _page("wiki/unused.md")
    young_log = [_injected(page.path, days_ago=30)]

    assert _build(pages=(page,), usage=young_log, kinds=("retire",)) == ()


def test_deleting_the_usage_log_removes_only_the_unused_signal() -> None:
    gone, unused = _page("wiki/gone.md"), _page("wiki/unused.md")
    missing = {("demo-vault", gone.path): ("src/gone.py",)}
    usage = [_injected("wiki/x.md", days_ago=95), _injected(unused.path, days_ago=10)]

    with_log = _build(pages=(gone, unused), missing_code=missing, usage=usage, kinds=("retire",))
    without_log = _build(pages=(gone, unused), missing_code=missing, usage=(), kinds=("retire",))

    assert [candidate.key for candidate in with_log] == ["retire:wiki/gone.md", "retire:wiki/unused.md"]
    assert [candidate.key for candidate in without_log] == ["retire:wiki/gone.md"]


def test_retire_skips_pinned_retired_and_other_project_pages() -> None:
    pinned = _page("wiki/pinned.md", frontmatter={"status": "active", "pin": True})
    retired = _page("wiki/retired.md", frontmatter={"status": "retired"})
    other = _page("wiki/other.md", scope=OTHER_SCOPE)
    missing = {("demo-vault", page.path): ("src/gone.py",) for page in (pinned, retired, other)}

    assert _build(pages=(pinned, retired, other), missing_code=missing, kinds=("retire",)) == ()


def test_page_with_both_retire_signals_is_one_candidate_with_both_reasons() -> None:
    page = _page("wiki/both.md")
    usage = [_injected("wiki/x.md", days_ago=95), _injected(page.path, days_ago=10)]

    candidates = _build(
        pages=(page,), missing_code={("demo-vault", page.path): ("src/gone.py",)}, usage=usage, kinds=("retire",)
    )

    assert len(candidates) == 1
    assert candidates[0].retire_signals == ("code_gone", "unused")


# Order, kinds, review records ---------------------------------------------------------------------


def test_kinds_come_in_table_order_and_reviewed_keys_are_left_out() -> None:
    a, b = _page("wiki/a.md"), _page("wiki/b.md")
    vectors = {("demo-vault", a.path): (1.0,), ("demo-vault", b.path): (1.0,)}
    missing = {("demo-vault", a.path): ("src/gone.py",)}

    candidates = _build(pages=(a, b), vectors=vectors, missing_code=missing)
    assert [candidate.kind for candidate in candidates] == ["merge", "retire"]

    reviewed = frozenset({"retire:wiki/a.md"})
    assert [
        candidate.kind for candidate in _build(pages=(a, b), vectors=vectors, missing_code=missing, reviewed=reviewed)
    ] == ["merge"]
    assert [
        candidate.kind for candidate in _build(pages=(a, b), vectors=vectors, missing_code=missing, kinds=("retire",))
    ] == ["retire"]


def test_session_exchanges_without_a_signal_come_after_every_other_kind() -> None:
    # A-23 (2026-11-07): about 1,000 plain exchanges filled the default 20 and hid every merge and retire
    # candidate. Plain exchanges go last, so a backlog of them never hides the other kinds.
    a, b = _page("wiki/a.md"), _page("wiki/b.md")
    vectors = {("demo-vault", a.path): (1.0,), ("demo-vault", b.path): (1.0,)}
    missing = {("demo-vault", a.path): ("src/gone.py",)}

    def exchange(name: str, human: str) -> SessionExchange:
        return SessionExchange(
            parent_key=f"s:{name}",
            path=f"raw/sessions/claude-code/2026-11-0{len(name)}-{name}-part1.md",
            line_start=1,
            line_end=5,
            started_at=NOW - timedelta(days=1),
            human_text=human,
        )

    candidates = build_memory_candidates(
        project_id="demo",
        l1_notes=(),
        imported_raw_sha256=frozenset(),
        exchanges=(exchange("plain", "테스트 돌려 줘"), exchange("fix", "아니야, 그건 틀렸어")),
        wiki_pages=(),
        reviewed_keys=frozenset(),
        similar_pages=FakeFinder(),
        now=NOW,
        memory_pages=(a, b),
        page_vectors=vectors,
        missing_code=missing,
        limit=3,
    )

    assert [candidate.key for candidate in candidates] == [
        "session:s:fix",
        "merge:wiki/a.md|wiki/b.md",
        "retire:wiki/a.md",
    ]


# Comparison material ----------------------------------------------------------------------------


def test_comparison_material_is_at_most_5_pages_and_marks_retired_pages() -> None:
    page = _page("wiki/gone.md", text="파서 결정")
    finder = FakeFinder(
        pages=(
            _similar("wiki/gone.md"),  # the candidate page itself is not material
            _similar("wiki/old.md", {"status": "retired", "retired_reason": "파서를 바꿈"}),
            _similar("wiki/older.md", {"status": "deprecated"}),
            *(_similar(f"wiki/p{index}.md") for index in range(6)),
        )
    )

    candidates = _build(pages=(page,), missing_code={("demo-vault", page.path): ("src/x.py",)}, finder=finder)

    material = candidates[0].comparison
    assert len(material) == COMPARISON_PAGE_LIMIT
    assert [item.path for item in material][:2] == ["wiki/old.md", "wiki/older.md"]
    assert material[0].label == "폐기됨: 파서를 바꿈"
    assert material[1].label == "폐기됨: deprecated"
    assert material[2].label is None
    assert finder.queries == ["gone\n\n파서 결정"]


def test_comparison_label_is_only_for_retired_like_statuses() -> None:
    def label(status: str | None, reason: str | None = None) -> str | None:
        return ComparisonPage("v", "wiki/x.md", "x", status, None, reason, None).label

    assert label("retired", "틀렸음") == "폐기됨: 틀렸음"
    assert label("superseded") == "폐기됨: superseded"
    assert label("active") is None
    assert label(None) is None


# Boundaries -------------------------------------------------------------------------------------


def test_m10_candidates_module_does_not_import_code_projection() -> None:
    source = Path(__file__).parents[1] / "src" / "vault_graph" / "context" / "memory" / "memory_candidates.py"
    imported: list[str] = []
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    assert not [name for name in imported if name.startswith("vault_graph.project.")]


# Composition: code references ------------------------------------------------------------------


def test_code_references_are_backticked_repository_paths_with_an_optional_symbol() -> None:
    text = (
        "| 파서 | stated | `src/app/x.py`, `src/app/y.py::run`, `./lib/a.dart#Widget`, "
        "`src/app/z.py:12-40@abc1234`, `src/app/w.py:helper` |\n"
        "`/abs/path.py` `../up/x.py` `README` `vg index` plain src/app/no_ticks.py"
    )

    assert code_references(text) == (
        CodeReference("src/app/x.py"),
        CodeReference("src/app/y.py", "run"),
        CodeReference("lib/a.dart", "Widget"),
        CodeReference("src/app/z.py"),
        CodeReference("src/app/w.py", "helper"),
    )


def test_missing_code_counts_only_paths_that_look_like_projected_code() -> None:
    projected = ProjectedCode({"src/app/kept.py": frozenset({"run", "app.kept.Parser.parse"})})
    references = (
        CodeReference("src/app/kept.py", "run"),
        CodeReference("src/app/kept.py", "Parser.parse"),
        CodeReference("src/app/kept.py", "gone_fn"),
        CodeReference("src/app/gone.py"),
        CodeReference("tools/wiki/cli.py"),  # first folder not in the projection
        CodeReference("src/app/notes.md"),  # suffix not in the projection
    )

    assert missing_code_references(references, projected) == ("src/app/gone.py", "src/app/kept.py::gone_fn")


# Composition: one entry over a real Graph Home --------------------------------------------------

runner = CliRunner()
V2_FIXTURE = (
    Path(__file__).parent
    / "fixtures/session_v2/raw/sessions/claude-code/2026-11-01-11111111-1111-4111-8111-111111111111-part1.md"
)
SAME_BODY = "파서 선택\n\ntree-sitter 파서를 쓴다.\n"


def _write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _tree_hashes(*roots: Path) -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    }


@dataclass(frozen=True)
class _Project:
    graph_home: Path
    repo: Path
    vault: Path
    memory: Path
    environ: dict[str, str]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: MonkeyPatch) -> _Project:
    from tests.test_cli_vector_indexing import _ConfiguredDeterministicTextEmbeddings
    from tests.test_vector_indexer import SPEC

    def embeddings(*_: object, **__: object) -> _ConfiguredDeterministicTextEmbeddings:
        return _ConfiguredDeterministicTextEmbeddings(SPEC)

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", embeddings)
    monkeypatch.setattr("vault_graph.interface.cli.main._search_text_embeddings", embeddings)
    monkeypatch.setattr("vault_graph.interface.composition.adapters.text_embeddings.text_embeddings_for", embeddings)

    repo = tmp_path / "repo"
    _write(repo, "src/app/kept.py", "def run() -> None:\n    pass\n")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)

    claude = tmp_path / "claude"
    memory = claude / "projects" / memory_folder_key(str(repo)) / "memory"
    _write(memory, "MEMORY.md", "- [a](feedback_a.md)\n")
    _write(memory, "feedback_a.md", "pytest는 -q로 돌린다\n")
    _write(memory, "feedback_b.md", "커밋 전에 ruff를 돌린다\n")
    kept_sha = hashlib.sha256((memory / "feedback_b.md").read_bytes()).hexdigest()

    vault = tmp_path / "vault"
    _write(vault, "wiki/sources/feedback-b.md", f"---\ntype: source\nraw_sha256: {kept_sha}\n---\n# b\n")
    page = "---\ntitle: 파서 선택\ntype: decision\nstatus: active\n---\n" + SAME_BODY
    _write(vault, "wiki/decisions/parser-a.md", page)
    _write(vault, "wiki/decisions/parser-b.md", page)
    _write(
        vault,
        "wiki/concepts/parser-code.md",
        "---\ntitle: 파서 코드\ntype: concept\nstatus: active\n---\n# 파서 코드\n\n"
        "tree-sitter 파서는 `src/app/gone.py`와 `src/app/kept.py::run`에 있다.\n",
    )
    _write(vault, "wiki/concepts/quiet.md", "---\ntitle: 조용한 페이지\ntype: concept\n---\n# 조용한\n\n회상만 된다.\n")
    _write(
        vault,
        "wiki/concepts/old-parser.md",
        "---\ntitle: 옛 파서\ntype: concept\nstatus: retired\nretired_reason: 파서를 바꿈\n---\n"
        "# 옛 파서\n\ntree-sitter 파서 이전에는 정규식 파서를 썼다.\n",
    )
    _write(
        vault,
        "wiki/sources/parser-notes.md",
        "---\ntitle: 파서 메모\ntype: source\n---\n# 파서 메모\n\ntree-sitter 파서는 정규식 파서를 바꿨다.\n",
    )
    session_path = "raw/sessions/claude-code/" + V2_FIXTURE.name
    (vault / session_path).parent.mkdir(parents=True)
    shutil.copyfile(V2_FIXTURE, vault / session_path)

    map_file = tmp_path / "vault-map.json"
    map_file.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"demo-vault": {"path": str(vault), "role": "project"}},
                "projects": {"demo": {"root": str(repo), "vaults": ["demo-vault"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(map_file))

    graph_home = tmp_path / "state"
    home = str(graph_home)
    for command in (
        ["init", "--vault-id", "demo-vault", "--vault", str(vault), "--graph-home", home],
        ["index", "--graph-home", home],
        ["code", "repository", "add", "demo", "--path", str(repo), "--language", "python", "--graph-home", home],
        ["code", "index", "--graph-home", home],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 0, (command, result.output)

    usage = graph_home / "usage"
    usage.mkdir()
    old = {"event": "injected", "vault_id": "demo-vault", "path": "wiki/x.md", "at": "2026-07-20T00:00:00+00:00"}
    quiet = {
        "event": "injected",
        "vault_id": "demo-vault",
        "path": "wiki/concepts/quiet.md",
        "at": "2026-10-27T00:00:00+00:00",
    }
    (usage / "2026-07.jsonl").write_text(json.dumps(old) + "\n", encoding="utf-8")
    (usage / "2026-10.jsonl").write_text(json.dumps(quiet) + "\n", encoding="utf-8")
    return _Project(
        graph_home,
        repo,
        vault,
        memory,
        {"CLAUDE_CONFIG_DIR": str(claude), "HOME": str(tmp_path), "VAULT_GRAPH_VAULT_MAP": str(map_file)},
    )


def test_package_has_all_four_kinds_in_table_order_with_at_most_5_comparison_pages(project: _Project) -> None:
    package = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)

    assert package.project_id == "demo"
    assert package.reason is None
    assert package.warnings == ()
    keys = [candidate.key for candidate in package.candidates]
    # The session exchange has no signal, so it comes after the other kinds.
    assert [candidate.kind for candidate in package.candidates] == [
        "l1_note",
        "merge",
        "retire",
        "retire",
        "session_exchange",
    ], keys
    l1 = package.candidates[0]
    assert l1.location.endswith("feedback_a.md")
    session = package.candidates[4]
    assert session.key == "session:11111111-1111-4111-8111-111111111111:u-001"
    assert session.signal == "none"
    assert session.started_at == datetime(2026, 11, 1, 10, 0, tzinfo=UTC)
    assert session.location.startswith("raw/sessions/claude-code/2026-11-01-")
    assert keys[1] == "merge:wiki/decisions/parser-a.md|wiki/decisions/parser-b.md"
    assert keys[2:4] == ["retire:wiki/concepts/parser-code.md", "retire:wiki/concepts/quiet.md"]
    assert package.candidates[2].reasons == ("근거 코드가 등록 저장소에서 사라짐: src/app/gone.py",)
    assert package.candidates[3].retire_signals == ("unused",)
    assert all(len(candidate.comparison) <= COMPARISON_PAGE_LIMIT for candidate in package.candidates)


def test_comparison_material_includes_retired_pages_with_the_retired_label(project: _Project) -> None:
    package = memory_candidate_package(
        project.graph_home, project.repo, now=NOW, environ=project.environ, kinds=RETIRE_ONLY
    )

    parser = next(candidate for candidate in package.candidates if candidate.location == "wiki/concepts/parser-code.md")
    labels = {page.path: page.label for page in parser.comparison}
    assert labels.get("wiki/concepts/old-parser.md") == "폐기됨: 파서를 바꿈"
    assert "wiki/concepts/parser-code.md" not in labels


def test_comparison_material_leaves_out_source_registration_pages(project: _Project) -> None:
    """Comparison material is existing knowledge pages (spec 2026-11-05 §4.4.4), not `wiki/sources/` records,
    even though knowledge-mode search now returns source pages (§10.2 원인1)."""
    package = memory_candidate_package(
        project.graph_home, project.repo, now=NOW, environ=project.environ, kinds=RETIRE_ONLY
    )

    parser = next(candidate for candidate in package.candidates if candidate.location == "wiki/concepts/parser-code.md")
    assert parser.comparison
    assert [page.path for page in parser.comparison if page.path.startswith("wiki/sources/")] == []


def test_same_state_gives_the_same_package_and_no_vault_or_l1_file_changes(project: _Project) -> None:
    before = _tree_hashes(project.vault, project.memory)

    first = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)
    second = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)

    assert first == second
    assert _tree_hashes(project.vault, project.memory) == before


def test_deleting_the_usage_log_removes_only_the_unused_candidate(project: _Project) -> None:
    with_log = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)
    shutil.rmtree(project.graph_home / "usage")
    without_log = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)

    removed = {c.key for c in with_log.candidates} - {c.key for c in without_log.candidates}
    assert removed == {"retire:wiki/concepts/quiet.md"}
    assert {c.key for c in without_log.candidates} < {c.key for c in with_log.candidates}


def test_backlog_kinds_count_the_same_as_the_full_package(project: _Project) -> None:
    full = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)
    backlog = memory_candidate_package(
        project.graph_home, project.repo, now=NOW, environ=project.environ, kinds=BACKLOG_KINDS
    )

    for kind in BACKLOG_KINDS:
        assert backlog.count(kind) == full.count(kind)
    assert backlog.count("merge") == backlog.count("retire") == 0


def test_merge_threshold_can_be_raised_above_any_pair(project: _Project) -> None:
    package = memory_candidate_package(
        project.graph_home, project.repo, now=NOW, environ=project.environ, kinds=MERGE_ONLY, merge_threshold=1.01
    )

    assert package.candidates == ()


def test_reviewed_candidate_does_not_come_back_until_the_log_is_deleted(project: _Project) -> None:
    from vault_graph.storage.local.reviewed_log import JsonlReviewedLog

    JsonlReviewedLog(project.graph_home).append(["retire:wiki/concepts/quiet.md"], outcome="skipped")
    hidden = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)
    (project.graph_home / "memory" / "reviewed.jsonl").unlink()
    shown = memory_candidate_package(project.graph_home, project.repo, now=NOW, environ=project.environ)

    assert "retire:wiki/concepts/quiet.md" not in {c.key for c in hidden.candidates}
    assert "retire:wiki/concepts/quiet.md" in {c.key for c in shown.candidates}


def test_folder_outside_a_map_project_gives_an_empty_package_with_a_reason(project: _Project, tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    package = memory_candidate_package(project.graph_home, elsewhere, now=NOW, environ=project.environ)

    assert package.candidates == ()
    assert package.reason is not None and package.reason.startswith(NO_PROJECT_REASON)
