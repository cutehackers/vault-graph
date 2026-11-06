"""`vg session export` in temporary folders (spec 2026-11-05 §4.2.4, §6 export 행, A-2).

The Claude Code folder is a synthetic copy of tests/fixtures/session_adapter under tmp_path, found
through CLAUDE_CONFIG_DIR. No real session is read.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.session_export_files import location_warnings

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "session_adapter"
OPEN_ID = "11111111-1111-4111-8111-111111111111"  # with_origin, expected with session_ended=False
ENDED_ID = "33333333-3333-4333-8333-333333333333"  # subagent_compact, expected with session_ended=True
PROJECT_KEY = "-tmp-demo-project"


@pytest.fixture
def claude_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_dir = tmp_path / "claude-config"
    project = config_dir / "projects" / PROJECT_KEY
    project.mkdir(parents=True)
    shutil.copytree(FIXTURES / "subagent_compact" / "raw", project, dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "with_origin" / "raw", project, dirs_exist_ok=True)
    # The open session is the newest file in the project folder.
    os.utime(project / f"{ENDED_ID}.jsonl", (1_700_000_000, 1_700_000_000))
    os.utime(project / f"{OPEN_ID}.jsonl", (1_700_100_000, 1_700_100_000))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(tmp_path / "no-vault-map.json"))
    return project


def _export(tmp_path: Path, *args: str) -> Result:
    return runner.invoke(
        app, ["session", "export", "--graph-home", str(tmp_path / "graph-home"), *args], catch_exceptions=False
    )


def _files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file()) if root.exists() else []


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _warnings(result: Result) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.startswith("warning:")]


def test_export_copies_raw_bytes_and_writes_normalized_with_owner_only_permissions(
    tmp_path: Path, claude_home: Path
) -> None:
    out = tmp_path / "export"

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--all")

    assert result.exit_code == 0, result.output
    assert _warnings(result) == []
    for session_id in (OPEN_ID, ENDED_ID):
        source = claude_home / f"{session_id}.jsonl"
        copy = out / "raw" / "claude-code" / session_id / f"{session_id}.jsonl"
        assert _sha(copy) == _sha(source)
    subagent_source = claude_home / ENDED_ID / "subagents"
    subagent_copy = out / "raw" / "claude-code" / ENDED_ID / "subagents"
    assert sorted(path.name for path in subagent_copy.iterdir()) == ["agent-a7f3.jsonl", "agent-a7f3.meta.json"]
    for path in subagent_copy.iterdir():
        assert _sha(path) == _sha(subagent_source / path.name)
    assert (out / "normalized" / "claude-code" / f"{OPEN_ID}.jsonl").read_bytes() == (
        FIXTURES / "with_origin" / "expected.jsonl"
    ).read_bytes()
    assert (out / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl").read_bytes() == (
        FIXTURES / "subagent_compact" / "expected.jsonl"
    ).read_bytes()
    folders = [path for path in out.rglob("*") if path.is_dir()]
    assert folders
    assert {stat.S_IMODE(path.stat().st_mode) for path in [out, *folders]} == {0o700}
    assert {stat.S_IMODE(path.stat().st_mode) for path in _files(out)} == {0o600}


def test_second_export_of_the_same_sessions_rewrites_nothing(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"
    assert _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--all").exit_code == 0
    before = {path: path.stat().st_mtime_ns for path in _files(out)}
    for path in before:
        os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--all")

    assert result.exit_code == 0, result.output
    assert {path: path.stat().st_mtime_ns for path in _files(out)} == dict.fromkeys(before, 1_600_000_000_000_000_000)
    assert "unchanged" in result.stdout


def test_grown_source_rewrites_normalized_and_raw_copy(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"
    assert _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--session", ENDED_ID).exit_code == 0
    normalized = out / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl"
    old_normalized = normalized.read_bytes()
    source = claude_home / f"{ENDED_ID}.jsonl"
    with source.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"type": "never-seen-type"}) + "\n")

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--session", ENDED_ID)

    assert result.exit_code == 0, result.output
    assert normalized.read_bytes() != old_normalized
    assert _sha(out / "raw" / "claude-code" / ENDED_ID / f"{ENDED_ID}.jsonl") == _sha(source)
    assert "never-seen-type:1" in result.stdout


def test_session_option_exports_one_session_and_no_raw_skips_copies(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--session", OPEN_ID, "--no-raw")

    assert result.exit_code == 0, result.output
    assert [path.relative_to(out).as_posix() for path in _files(out)] == [f"normalized/claude-code/{OPEN_ID}.jsonl"]


def test_since_keeps_sessions_modified_on_or_after_the_date(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"
    os.utime(claude_home / f"{OPEN_ID}.jsonl")  # now

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--since", "2024-01-01")

    assert result.exit_code == 0, result.output
    assert [path.name for path in (out / "normalized" / "claude-code").iterdir()] == [f"{OPEN_ID}.jsonl"]


def test_unknown_session_is_an_error_without_files(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--session", "no-such-session")

    assert result.exit_code != 0
    assert not out.exists()


@pytest.mark.parametrize(
    "selection",
    [[], ["--all", "--session", OPEN_ID], ["--session", "../escape"]],
)
def test_selection_must_be_exactly_one_valid_choice(tmp_path: Path, claude_home: Path, selection: list[str]) -> None:
    out = tmp_path / "export"

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), *selection)

    assert result.exit_code != 0
    assert not out.exists()


def test_out_inside_registered_vault_writes_nothing(tmp_path: Path, claude_home: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    graph_home = tmp_path / "graph-home"
    assert runner.invoke(app, ["init", "--vault", str(vault), "--graph-home", str(graph_home)]).exit_code == 0

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(vault / "exports"), "--all")

    assert result.exit_code != 0
    assert _files(vault) == []
    assert "inside Vault" in result.stderr


def test_out_inside_vault_map_vault_writes_nothing(
    tmp_path: Path, claude_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vault = tmp_path / "map-vault"
    vault.mkdir()
    vault_map = tmp_path / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"main": {"path": str(vault), "role": "personal"}}, "projects": {}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(vault_map))

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(vault), "--all")

    assert result.exit_code != 0
    assert _files(vault) == []


def test_out_inside_git_work_tree_warns_once_and_writes(tmp_path: Path, claude_home: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    out = repository / "exports"

    result = _export(tmp_path, "--agent", "claude-code", "--out", str(out), "--session", OPEN_ID)

    assert result.exit_code == 0, result.output
    warnings = _warnings(result)
    assert len(warnings) == 1
    assert "git" in warnings[0]
    assert (out / "normalized" / "claude-code" / f"{OPEN_ID}.jsonl").is_file()


def test_codex_has_no_adapter(tmp_path: Path, claude_home: Path) -> None:
    out = tmp_path / "export"

    result = _export(tmp_path, "--agent", "codex", "--out", str(out), "--all")

    assert result.exit_code != 0
    assert "adapter 없음" in result.stderr
    assert not out.exists()


def test_sync_folder_warning_names_the_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    out = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "vg-export"

    warnings = location_warnings(out, home=home)

    assert len(warnings) == 1
    assert "sync folder Library/Mobile Documents" in warnings[0]
    assert location_warnings(home / "plain" / "vg-export", home=home) == ()
