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
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from tests.test_cli_setup import _deterministic_text_embeddings
from vault_graph.context.pack.recall import estimate_recall_tokens, memory_item_id
from vault_graph.interface.cli.main import app

FIXTURES = Path(__file__).parent / "fixtures" / "session_recall"
runner = CliRunner()


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
