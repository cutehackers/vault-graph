"""`vg hook session-start` with a fixture Vault, map and real index (spec 4.2.3, A-10, A-11).

Fixture pages in tests/fixtures/session_recall use ``{base}`` for the temporary folder and
``{day:N}`` for the date N days before today, so the 14-day rule holds on any run date.
"""

from __future__ import annotations

import json
import re
import shutil
import stat
import subprocess
import sys
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.test_cli_setup import _deterministic_text_embeddings
from vault_graph.context.pack.recall import estimate_recall_tokens, memory_item_id
from vault_graph.interface.cli import hook_commands
from vault_graph.interface.cli.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "session_recall"
runner = CliRunner()
REAL_START_CATCH_UP_INDEX = hook_commands.start_catch_up_index


def day(offset: int) -> str:
    return (date.today() - timedelta(days=offset)).isoformat()


def render(text: str, base: Path) -> str:
    text = text.replace("{base}", str(base))
    return re.sub(r"\{day:(\d+)\}", lambda match: day(int(match.group(1))), text)


def write_page(vault: Path, relative: str, front: str, title: str) -> None:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n{front}---\n# {title}\n\nBody of {title}.\n", encoding="utf-8")


def tree(root: Path, *, skip: str | None = None) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and (skip is None or path.relative_to(root).parts[0] != skip)
    }


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", _deterministic_text_embeddings)


@pytest.fixture(autouse=True)
def catch_up(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, tuple[str, ...]]]:
    """Record the detached catch-up `vg index` instead of starting a real process."""
    started: list[tuple[Path, tuple[str, ...]]] = []

    def record(graph_home: Path, vault_ids: tuple[str, ...]) -> None:
        started.append((graph_home, vault_ids))
        sys.stdout.write("<catch-up started>")

    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.start_catch_up_index", record)
    return started


@pytest.fixture(autouse=True)
def fixture_files_stay_unchanged() -> Iterator[None]:
    before = tree(FIXTURES)
    yield
    assert tree(FIXTURES) == before


@pytest.fixture
def base(tmp_path: Path) -> Path:
    root = tmp_path.resolve()
    for source in sorted((FIXTURES / "vaults").rglob("*.md")):
        target = root / "vaults" / source.relative_to(FIXTURES / "vaults")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(source.read_text(encoding="utf-8"), root), encoding="utf-8")
    (root / "map").mkdir()
    (root / "map" / "vault-map.json").write_text(
        render((FIXTURES / "vault-map.json").read_text(encoding="utf-8"), root), encoding="utf-8"
    )
    for repo in ("alpha", "both", "unregistered", "loose"):
        (root / "repos" / repo).mkdir(parents=True)
        subprocess.run(["git", "-C", str(root / "repos" / repo), "init", "-q"], check=True)
    return root


def invoke(*arguments: str) -> Result:
    result = runner.invoke(app, list(arguments))
    assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def graph_home(base: Path) -> Path:
    home = base / "graph-home"
    invoke("init", "--vault", str(base / "vaults" / "main"), "--vault-id", "main", "--graph-home", str(home))
    invoke("vault", "add", "other", "--path", str(base / "vaults" / "other"), "--graph-home", str(home))
    reindex(home)
    return home


def reindex(home: Path) -> None:
    invoke("index", "--all-vaults", "--graph-home", str(home))


def hook(
    home: Path,
    base: Path,
    *,
    repo: str = "alpha",
    source: str | None = "startup",
    extra: tuple[str, ...] = (),
    vault_map: Path | None = None,
    stdin: str | None = None,
) -> Result:
    payload: dict[str, object] = {"cwd": str(base / "repos" / repo), "session_id": "session-1"}
    if source is not None:
        payload["source"] = source
    map_path = vault_map if vault_map is not None else base / "map" / "vault-map.json"
    return runner.invoke(
        app,
        ["hook", "session-start", "--graph-home", str(home), "--vault-map", str(map_path), *extra],
        input=stdin if stdin is not None else json.dumps(payload),
    )


def section(text: str, title: str) -> list[str]:
    lines = text.splitlines()
    if title not in lines:
        return []
    start = lines.index(title)
    end = next((index for index in range(start + 1, len(lines)) if lines[index].startswith("## ")), len(lines))
    return [line for line in lines[start + 1 : end] if line]


def usage_events(home: Path) -> list[dict[str, object]]:
    usage = home / "usage"
    if not usage.exists():
        return []
    return [json.loads(line) for path in sorted(usage.glob("*.jsonl")) for line in path.read_text().splitlines()]


def test_startup_prints_blocks_b_and_d_in_order_within_both_limits(base: Path, graph_home: Path) -> None:
    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert [line for line in result.stdout.splitlines() if line.startswith("## ")] == [
        "## 기억 목록",
        "## 가져오는 방법",
    ]
    assert estimate_recall_tokens(result.stdout) <= 1500
    assert len(result.stdout) <= 9000


def test_block_b_lines_follow_the_contract(base: Path, graph_home: Path) -> None:
    lines = section(hook(graph_home, base).stdout, "## 기억 목록")

    pattern = re.compile(r"^- \[m:[0-9a-f]{8}\] \S+ · \d{4}-\d{2}-\d{2} · .+ · .+ \(wiki/\S+\.md, ~\d+t\)$")
    assert lines and all(pattern.match(line) for line in lines), lines
    text = "\n".join(lines)
    for absent in ("Old choice", "Stale choice", "Dropped choice", "Beta flow", "Raw source", "Other vault decision"):
        assert absent not in text
    assert lines[0].startswith(f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] decision · {day(1)} · ")
    assert any("inferred(추정)" in line for line in lines)
    assert any("contested(논쟁 중)" in line for line in lines)
    assert any("] 기타 · " in line and "Untyped note" in line for line in lines)
    assert any("Alpha flow" in line for line in lines)


def test_run_appends_one_injected_event_per_item_and_changes_nothing_else(base: Path, graph_home: Path) -> None:
    vault_before = tree(base / "vaults")
    home_before = tree(graph_home)

    result = hook(graph_home, base)

    printed = re.findall(r"\[(m:[0-9a-f]{8})\]", result.stdout)
    events = usage_events(graph_home)
    assert [event["item_id"] for event in events] == printed
    assert {event["event"] for event in events} == {"injected"}
    assert tree(base / "vaults") == vault_before
    assert tree(graph_home, skip="usage") == home_before


def supersede_use_sqlite(base: Path) -> None:
    vault = base / "vaults" / "main"
    write_page(
        vault,
        "wiki/decisions/use-sqlite.md",
        f'type: decision\nstatus: superseded\nupdated: "{day(0)}"\nsuperseded_by:\n  - decisions/use-duckdb\n',
        "Use SQLite",
    )
    write_page(
        vault, "wiki/decisions/use-duckdb.md", f'type: decision\nstatus: active\nupdated: "{day(0)}"\n', "Use DuckDB"
    )


def test_block_c_reports_the_superseded_injected_item_then_falls_back_without_usage(
    base: Path, graph_home: Path
) -> None:
    hook(graph_home, base)
    supersede_use_sqlite(base)
    reindex(graph_home)

    after_change = hook(graph_home, base)
    shutil.rmtree(graph_home / "usage")
    without_usage = hook(graph_home, base)

    expected = f"- [{memory_item_id('main', 'wiki/decisions/use-sqlite.md')}] Use SQLite → Use DuckDB ({day(0)})"
    assert section(after_change.stdout, "## 변경 알림") == [expected]
    assert [line for line in after_change.stdout.splitlines() if line.startswith("## ")] == [
        "## 기억 목록",
        "## 변경 알림",
        "## 가져오는 방법",
    ]
    assert section(without_usage.stdout, "## 변경 알림") == [expected]


@pytest.mark.parametrize("source", ["resume", "fork"])
def test_resume_prints_nothing_without_changes_and_only_block_c_with_one(
    base: Path, graph_home: Path, source: str
) -> None:
    hook(graph_home, base)
    unchanged = hook(graph_home, base, source=source)
    supersede_use_sqlite(base)
    reindex(graph_home)
    changed = hook(graph_home, base, source=source)

    assert (unchanged.exit_code, unchanged.stdout) == (0, "")
    assert changed.exit_code == 0
    assert [line for line in changed.stdout.splitlines() if line.startswith("## ")] == ["## 변경 알림"]


@pytest.mark.parametrize("source", ["clear", "compact", "something-new", None])
def test_other_sources_are_handled_like_startup(base: Path, graph_home: Path, source: str | None) -> None:
    result = hook(graph_home, base, source=source)

    assert result.exit_code == 0
    assert "## 기억 목록" in result.stdout


def add_pages(base: Path, count: int, *, kind: str = "decision", status: str = "active", title_length: int = 0) -> None:
    for index in range(count):
        title = ("가" * title_length + str(index)) if title_length else f"Extra {kind} number {index}"
        write_page(
            base / "vaults" / "main",
            f"wiki/{kind}s/extra-{index:02d}.md",
            f'type: {kind}\nstatus: {status}\nupdated: "{day(index % 20)}"\n',
            title,
        )


def test_small_token_limit_shortens_block_b_and_keeps_c_and_d(base: Path, graph_home: Path) -> None:
    hook(graph_home, base)
    supersede_use_sqlite(base)
    add_pages(base, 12)
    add_pages(base, 8, kind="issue", status="open")
    add_pages(base, 8, kind="concept")
    reindex(graph_home)

    result = hook(graph_home, base, extra=("--max-tokens", "300"))

    assert result.exit_code == 0
    assert estimate_recall_tokens(result.stdout) <= 300
    assert re.fullmatch(r"- \d+개 생략", section(result.stdout, "## 기억 목록")[-1])
    assert section(result.stdout, "## 변경 알림")
    assert section(result.stdout, "## 가져오는 방법")


def test_character_limit_stops_output_inside_the_token_limit(base: Path, graph_home: Path) -> None:
    add_pages(base, 12, title_length=900)
    reindex(graph_home)

    result = hook(graph_home, base, extra=("--max-tokens", "100000"))

    assert result.exit_code == 0
    assert len(result.stdout) <= 9000
    assert re.fullmatch(r"- \d+개 생략", section(result.stdout, "## 기억 목록")[-1])


def test_recall_never_builds_embeddings_or_a_vector_store(
    base: Path, graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("session start must not open embeddings or a vector store")

    monkeypatch.setattr("vault_graph.storage.local.chroma_vector_store.ChromaVectorStore.__init__", fail)
    monkeypatch.setattr(
        "vault_graph.interface.composition.adapters.text_embeddings.FastEmbedTextEmbeddings.__init__", fail
    )
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", fail)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "## 기억 목록" in result.stdout


@pytest.fixture
def read_only_usage(graph_home: Path) -> Iterator[Path]:
    usage = graph_home / "usage"
    usage.mkdir()
    usage.chmod(stat.S_IRUSR | stat.S_IXUSR)
    yield usage
    usage.chmod(stat.S_IRWXU)


def test_read_only_usage_keeps_output_and_warns_once(base: Path, graph_home: Path, read_only_usage: Path) -> None:
    result = hook(graph_home, base)
    read_only_usage.chmod(stat.S_IRWXU)
    shutil.rmtree(read_only_usage)
    writable = hook(graph_home, base)

    assert result.exit_code == 0
    assert result.stdout == writable.stdout
    assert len(result.stderr.splitlines()) == 1
    assert "warning" in result.stderr


def test_several_vaults_prefix_paths_with_vault_ids(base: Path, graph_home: Path) -> None:
    result = hook(graph_home, base, repo="both")

    assert result.exit_code == 0
    assert "(other:wiki/decisions/other-decision.md, ~" in result.stdout
    assert "(main:wiki/decisions/use-sqlite.md, ~" in result.stdout


def test_project_binding_is_used_when_the_map_has_no_project(base: Path, graph_home: Path) -> None:
    invoke(
        "code", "repository", "add", "loose", "--path", str(base / "repos" / "loose"), "--graph-home", str(graph_home)
    )
    invoke("project", "bind", "loose", "--vault-id", "main", "--graph-home", str(graph_home))

    result = hook(graph_home, base, repo="loose", vault_map=base / "map" / "missing.json")

    assert result.exit_code == 0, result.output
    assert "Use SQLite" in result.stdout


def assert_handoff(result: Result, home: Path) -> None:
    assert result.exit_code == 3, result.output
    assert result.stdout == ""
    assert result.stderr.strip()
    assert not (home / "usage").exists()


def test_no_map_and_no_binding_hands_off(base: Path, graph_home: Path) -> None:
    assert_handoff(hook(graph_home, base, vault_map=base / "map" / "missing.json"), graph_home)


def test_folder_outside_every_project_hands_off(base: Path, graph_home: Path) -> None:
    assert_handoff(hook(graph_home, base, repo="loose"), graph_home)


def test_unregistered_vault_hands_off_with_setup_hint(base: Path, graph_home: Path) -> None:
    result = hook(graph_home, base, repo="unregistered")

    assert_handoff(result, graph_home)
    assert "vg setup" in result.stderr


def test_missing_graph_home_hands_off_and_is_not_created(base: Path) -> None:
    home = base / "no-graph-home"

    assert_handoff(hook(home, base), home)
    assert not home.exists()


def test_registered_but_unindexed_vault_hands_off(base: Path) -> None:
    home = base / "graph-home"
    invoke("init", "--vault", str(base / "vaults" / "main"), "--vault-id", "main", "--graph-home", str(home))

    result = hook(home, base)

    assert_handoff(result, home)
    assert "vg index" in result.stderr


def test_startup_with_nothing_to_recall_hands_off(base: Path, graph_home: Path) -> None:
    for page in (base / "vaults" / "main" / "wiki").rglob("*.md"):
        page.write_text(page.read_text(encoding="utf-8").replace("status: active", "status: stale"), encoding="utf-8")
    for relative in (
        "concepts/guessed-rule.md",
        "concepts/argued-rule.md",
        "issues/open-budget.md",
        "notes/untyped-note.md",
    ):
        (base / "vaults" / "main" / "wiki" / relative).unlink()
    reindex(graph_home)

    assert_handoff(hook(graph_home, base), graph_home)


def test_unreadable_hook_input_hands_off(base: Path, graph_home: Path) -> None:
    assert_handoff(hook(graph_home, base, stdin="not json"), graph_home)


def test_unexpected_error_exits_with_another_code_and_empty_stdout(
    base: Path, graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("vault_graph.interface.cli.hook_commands.recall", explode)

    result = hook(graph_home, base)

    assert result.exit_code not in (0, 3)
    assert result.stdout == ""


def pin_page(vault: Path, relative: str, title: str, *, pin: str = "true", schema: str = "vault-memory/v1") -> None:
    write_page(
        vault,
        relative,
        f'type: concept\nstatus: active\nupdated: "{day(90)}"\npin: {pin}\nmemory_schema: {schema}\n'
        f"memory_kind: rule\nsummary: Summary of {title}\n",
        title,
    )


def test_yaml_true_pin_in_another_vault_is_printed_first_and_not_repeated(base: Path, graph_home: Path) -> None:
    """A-1 at unit level: the pinned page of the second Vault opens the bundle (위험6 through a real index)."""
    pin_page(base / "vaults" / "other", "wiki/rules/team-rule.md", "Team rule")
    pin_page(base / "vaults" / "main", "wiki/rules/quoted.md", "Quoted rule", pin='"true"')
    reindex(graph_home)

    result = hook(graph_home, base, repo="both")

    assert result.exit_code == 0, result.output
    assert [line for line in result.stdout.splitlines() if line.startswith("## ")][0] == "## 고정 기억"
    assert section(result.stdout, "## 고정 기억") == [
        f"- [{memory_item_id('other', 'wiki/rules/team-rule.md')}] rule · Team rule (other:wiki/rules/team-rule.md)",
        "  Summary of Team rule",
    ]
    block_b = "\n".join(section(result.stdout, "## 기억 목록"))
    assert "Team rule" not in block_b
    assert "Quoted rule" in block_b
    assert estimate_recall_tokens(result.stdout) <= 1500
    assert len(result.stdout) <= 9000


def test_unknown_memory_schema_warns_once_on_stderr(base: Path, graph_home: Path) -> None:
    pin_page(base / "vaults" / "main", "wiki/rules/future.md", "Future rule", schema="vault-memory/v9")
    reindex(graph_home)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "## 고정 기억" not in result.stdout
    assert "Future rule" in "\n".join(section(result.stdout, "## 기억 목록"))
    assert len(result.stderr.splitlines()) == 1
    assert "vault-memory/v9" in result.stderr


def test_several_vaults_use_map_names_in_locations(base: Path, graph_home: Path) -> None:
    named_map = base / "map" / "named-vault-map.json"
    named_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "personal-notes": {"path": str(base / "vaults" / "main"), "role": "personal"},
                    "team-wiki": {"path": str(base / "vaults" / "other"), "role": "team"},
                },
                "projects": {
                    "both": {"root": str(base / "repos" / "both"), "vaults": ["personal-notes", "team-wiki"]},
                },
            }
        ),
        encoding="utf-8",
    )
    pin_page(base / "vaults" / "other", "wiki/rules/team-rule.md", "Team rule")
    reindex(graph_home)

    result = hook(graph_home, base, repo="both", vault_map=named_map)

    assert result.exit_code == 0, result.output
    assert "(team-wiki:wiki/rules/team-rule.md)" in section(result.stdout, "## 고정 기억")[0]
    assert "(team-wiki:wiki/decisions/other-decision.md, ~" in result.stdout
    assert "(personal-notes:wiki/decisions/use-sqlite.md, ~" in result.stdout


# Index refresh before recall (F1) -------------------------------------------------------------


def active_generation(home: Path) -> str:
    return str(json.loads((home / "projections" / "active.json").read_text(encoding="utf-8"))["generation_id"])


def generations(home: Path) -> set[str]:
    return {path.name for path in (home / "projections" / "generations").iterdir()}


def test_page_written_after_the_last_index_is_recalled_without_vg_index(base: Path, graph_home: Path) -> None:
    write_page(
        base / "vaults" / "main",
        "wiki/decisions/use-uv.md",
        f'type: decision\nstatus: active\nupdated: "{day(0)}"\n',
        "Use uv run",
    )
    vaults_before = tree(base / "vaults")
    before = active_generation(graph_home)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert section(result.stdout, "## 기억 목록")[0].startswith(
        f"- [{memory_item_id('main', 'wiki/decisions/use-uv.md')}] decision · {day(0)} · active · Use uv run"
    )
    assert active_generation(graph_home) != before
    assert tree(base / "vaults") == vaults_before


def test_refresh_reads_metadata_only_and_never_embeds(
    base: Path, graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("the session start refresh must not embed")

    monkeypatch.setattr(
        "vault_graph.interface.composition.adapters.text_embeddings.FastEmbedTextEmbeddings.__init__", fail
    )
    monkeypatch.setattr("vault_graph.indexing.vector_index_adapter.VectorIndexer._embed_chunks", fail)
    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", fail)
    write_page(
        base / "vaults" / "main", "wiki/notes/fresh.md", f'type: note\nstatus: active\nupdated: "{day(0)}"\n', "Fresh"
    )

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "Fresh" in "\n".join(section(result.stdout, "## 기억 목록"))
    assert result.stderr == ""


def test_deleted_page_leaves_recall_and_a_later_vg_index_still_works(base: Path, graph_home: Path) -> None:
    (base / "vaults" / "main" / "wiki" / "decisions" / "use-sqlite.md").unlink()

    result = hook(graph_home, base)
    reindex(graph_home)
    after_index = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "Use SQLite" not in result.stdout
    assert result.stderr == ""
    assert section(after_index.stdout, "## 기억 목록") == section(result.stdout, "## 기억 목록")


def test_only_vaults_linked_to_the_folder_are_refreshed(base: Path, graph_home: Path) -> None:
    write_page(
        base / "vaults" / "other",
        "wiki/decisions/team-choice.md",
        f'type: decision\nstatus: active\nupdated: "{day(0)}"\n',
        "Team choice",
    )
    before = active_generation(graph_home)

    alpha = hook(graph_home, base)
    unchanged = active_generation(graph_home)
    both = hook(graph_home, base, repo="both")

    assert unchanged == before
    assert "Team choice" not in alpha.stdout
    assert "Team choice" in both.stdout


def test_failed_refresh_warns_and_recalls_from_the_existing_index(
    base: Path, graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr("vault_graph.indexing.metadata_indexer.MetadataIndexer.apply", explode)
    write_page(
        base / "vaults" / "main", "wiki/notes/fresh.md", f'type: note\nstatus: active\nupdated: "{day(0)}"\n', "Fresh"
    )
    before = active_generation(graph_home)
    staged_before = generations(graph_home)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "Use SQLite" in result.stdout
    assert "Fresh" not in result.stdout
    assert "disk full" in result.stderr
    assert len(result.stderr.splitlines()) == 1
    assert active_generation(graph_home) == before
    assert generations(graph_home) == staged_before


def test_zero_refresh_budget_skips_the_refresh(base: Path, graph_home: Path) -> None:
    write_page(
        base / "vaults" / "main", "wiki/notes/fresh.md", f'type: note\nstatus: active\nupdated: "{day(0)}"\n', "Fresh"
    )
    before = active_generation(graph_home)

    result = hook(graph_home, base, extra=("--refresh-budget", "0"))

    assert result.exit_code == 0, result.output
    assert "Fresh" not in result.stdout
    assert active_generation(graph_home) == before


def test_refresh_past_its_time_limit_publishes_nothing(
    base: Path, graph_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ticks = iter(range(0, 1000, 10))
    monkeypatch.setattr("vault_graph.interface.composition.recall_index_refresh.monotonic", lambda: float(next(ticks)))
    write_page(
        base / "vaults" / "main", "wiki/notes/fresh.md", f'type: note\nstatus: active\nupdated: "{day(0)}"\n', "Fresh"
    )
    before = active_generation(graph_home)
    staged_before = generations(graph_home)

    result = hook(graph_home, base, extra=("--refresh-budget", "15"))

    assert result.exit_code == 0, result.output
    assert "Fresh" not in result.stdout
    assert "time limit" in result.stderr
    assert active_generation(graph_home) == before
    assert generations(graph_home) == staged_before


# Vector catch-up after session start and bounded refresh (re-audit 발견1, 발견3) ----------------


def fresh_note(base: Path, name: str = "fresh", vault: str = "main") -> None:
    write_page(
        base / "vaults" / vault,
        f"wiki/notes/{name}.md",
        f'type: note\nstatus: active\nupdated: "{day(0)}"\n',
        name.title(),
    )


def test_changed_vault_gets_a_catch_up_index_after_recall_is_printed(
    base: Path, graph_home: Path, catch_up: list[tuple[Path, tuple[str, ...]]]
) -> None:
    fresh_note(base)
    fresh_note(base, "team-fresh", vault="other")

    result = hook(graph_home, base, repo="both")

    assert result.exit_code == 0, result.output
    assert catch_up == [(graph_home, ("main", "other"))]
    assert result.stdout.endswith("<catch-up started>")
    assert "Fresh" in result.stdout


def test_only_changed_linked_vaults_get_a_catch_up_index(
    base: Path, graph_home: Path, catch_up: list[tuple[Path, tuple[str, ...]]]
) -> None:
    fresh_note(base, "team-fresh", vault="other")

    hook(graph_home, base, repo="both")

    assert catch_up == [(graph_home, ("other",))]


def test_no_change_starts_no_catch_up_index(
    base: Path, graph_home: Path, catch_up: list[tuple[Path, tuple[str, ...]]]
) -> None:
    result = hook(graph_home, base, repo="both")

    assert result.exit_code == 0, result.output
    assert catch_up == []


def test_too_many_changed_files_skip_the_quick_refresh_and_leave_no_staged_folder(
    base: Path,
    graph_home: Path,
    catch_up: list[tuple[Path, tuple[str, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vault_graph.interface.composition.recall_index_refresh.MAX_QUICK_REFRESH_FILES", 2)
    for name in ("one", "two", "three"):
        fresh_note(base, name)
    before = active_generation(graph_home)
    staged_before = generations(graph_home)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "Three" not in result.stdout
    assert len(result.stderr.splitlines()) == 1
    assert "3 changed files" in result.stderr
    assert active_generation(graph_home) == before
    assert generations(graph_home) == staged_before
    assert catch_up == [(graph_home, ("main",))]


def test_time_limit_inside_the_change_scan_stops_before_staging(
    base: Path,
    graph_home: Path,
    catch_up: list[tuple[Path, tuple[str, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_staging(*args: object, **kwargs: object) -> None:
        raise AssertionError("a refresh past its time limit must not stage a generation")

    clock = iter(range(0, 100000))
    monkeypatch.setattr("vault_graph.interface.composition.recall_index_refresh.monotonic", lambda: float(next(clock)))
    monkeypatch.setattr(
        "vault_graph.indexing.publication.projection_generation.ProjectionBundlePublisher.stage_from_active",
        no_staging,
    )
    fresh_note(base)
    before = active_generation(graph_home)
    staged_before = generations(graph_home)

    result = hook(graph_home, base, repo="both", extra=("--refresh-budget", "3"))

    assert result.exit_code == 0, result.output
    assert "time limit" in result.stderr
    assert active_generation(graph_home) == before
    assert generations(graph_home) == staged_before
    # The scan did not finish, so every linked Vault gets the catch-up index.
    assert catch_up == [(graph_home, ("main", "other"))]


def test_zero_refresh_budget_starts_no_catch_up_index(
    base: Path, graph_home: Path, catch_up: list[tuple[Path, tuple[str, ...]]]
) -> None:
    fresh_note(base)

    hook(graph_home, base, extra=("--refresh-budget", "0"))

    assert catch_up == []


def test_catch_up_index_runs_detached_with_the_same_graph_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[list[str], dict[str, object]]] = []

    class FakePopen:
        def __init__(self, command: list[str], **kwargs: object) -> None:
            started.append((command, kwargs))

    monkeypatch.setattr(hook_commands.subprocess, "Popen", FakePopen)
    home = tmp_path / "graph-home"
    home.mkdir()

    REAL_START_CATCH_UP_INDEX(home, ("main", "other"))

    assert len(started) == 1
    command, kwargs = started[0]
    assert command[0] == sys.executable
    assert command[-3:] == [str(home), "main", "other"]
    assert kwargs["start_new_session"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["close_fds"] is True
    assert (home / "logs" / "session-start-index.log").exists()


def test_catch_up_script_indexes_each_vault_in_turn(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(hook_commands.subprocess, "run", lambda command, **kwargs: ran.append(command))
    monkeypatch.setattr(sys, "argv", ["-c", str(tmp_path), "main", "other"])

    hook_commands.run_catch_up_index()

    assert [command[-5:] for command in ran] == [
        ["index", "--graph-home", str(tmp_path), "--vault-id", "main"],
        ["index", "--graph-home", str(tmp_path), "--vault-id", "other"],
    ]


def test_busy_projection_lock_skips_the_quick_refresh_after_a_short_wait(
    base: Path,
    graph_home: Path,
    catch_up: list[tuple[Path, tuple[str, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vault_graph.indexing.publication.projection_generation import ProjectionPublishBusyError

    waits: list[float | None] = []

    def busy(self: object, *, full: bool = False, lock_timeout: float | None = None) -> None:
        waits.append(lock_timeout)
        raise ProjectionPublishBusyError("another vg index is publishing")

    monkeypatch.setattr(
        "vault_graph.indexing.publication.projection_generation.ProjectionBundlePublisher.stage_from_active", busy
    )
    fresh_note(base)
    before = active_generation(graph_home)

    result = hook(graph_home, base)

    assert result.exit_code == 0, result.output
    assert "Use SQLite" in result.stdout
    assert len(result.stderr.splitlines()) == 1
    assert "Index refresh skipped" in result.stderr
    assert "another vg index" in result.stderr
    assert waits and waits[0] is not None and 0 < waits[0] <= 1.0
    assert active_generation(graph_home) == before
    assert catch_up == [(graph_home, ("main",))]
