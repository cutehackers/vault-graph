"""`vg session export --recapture` (spec 2026-11-05 §4.2.4, §4.2.12-4·5, A-37 vg side).

A fake ``vault_hooks.py`` next to the vault-map file records its arguments and stdin. The Claude
Code folder is a copy of tests/fixtures/session_adapter found through CLAUDE_CONFIG_DIR.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "session_adapter"
OPEN_ID = "11111111-1111-4111-8111-111111111111"
ENDED_ID = "33333333-3333-4333-8333-333333333333"
PROJECT_KEY = "-tmp-demo-project"

FAKE_LAUNCHER = """\
import json, os, sys
data = sys.stdin.buffer.read()
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": data.decode("utf-8")}) + "\\n")
if os.environ.get("FAKE_NORMALIZED_MODE") == "unknown":
    sys.exit(2)
print(json.dumps({"status": "written", "vault": "proj-vault", "path": "raw/sessions/s-p3.md"}))
"""


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config_dir = tmp_path / "claude-config"
    project = config_dir / "projects" / PROJECT_KEY
    project.mkdir(parents=True)
    shutil.copytree(FIXTURES / "subagent_compact" / "raw", project, dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "with_origin" / "raw", project, dirs_exist_ok=True)
    os.utime(project / f"{ENDED_ID}.jsonl", (1_700_000_000, 1_700_000_000))
    os.utime(project / f"{OPEN_ID}.jsonl", (1_700_100_000, 1_700_100_000))
    builder = tmp_path / "claude" / "vault-builder"
    builder.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    vault.mkdir(parents=True)
    vault_map = builder / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"proj-vault": {"path": str(vault), "role": "project"}}, "projects": {}}),
        encoding="utf-8",
    )
    (builder / "vault_hooks.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(vault_map))
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(tmp_path / "launcher.log"))
    monkeypatch.delenv("FAKE_NORMALIZED_MODE", raising=False)
    return {"project": project, "map": vault_map, "builder": builder, "log": tmp_path / "launcher.log", "tmp": tmp_path}


def export(world: dict[str, Path], *args: str) -> Result:
    return runner.invoke(
        app,
        ["session", "export", "--graph-home", str(world["tmp"] / "graph-home"), "--agent", "claude-code", *args],
        catch_exceptions=False,
    )


def calls(world: dict[str, Path]) -> list[dict[str, object]]:
    if not world["log"].exists():
        return []
    return [json.loads(line) for line in world["log"].read_text(encoding="utf-8").splitlines()]


def test_recapture_runs_the_launcher_with_normalized_and_rerender_per_session(world: dict[str, Path]) -> None:
    out = world["tmp"] / "export"

    result = export(world, "--out", str(out), "--all", "--recapture")

    assert result.exit_code == 0, result.output
    found = calls(world)
    assert len(found) == 2
    for call, session_id, event in zip(found, sorted((OPEN_ID, ENDED_ID)), ("PreCompact", "SessionEnd"), strict=True):
        normalized = out / "normalized" / "claude-code" / f"{session_id}.jsonl"
        assert call["argv"] == ["capture", "--direct", "--normalized", str(normalized), "--rerender"]
        hook = json.loads(str(call["stdin"]))
        assert hook["session_id"] == session_id
        assert hook["transcript_path"] == str(world["project"] / f"{session_id}.jsonl")
        assert hook["cwd"] == "/work/demo-app"
        assert hook["hook_event_name"] == event
    lines = [line for line in result.stdout.splitlines() if "recapture=" in line]
    assert len(lines) == 2
    assert all("recapture=written" in line and "vault=proj-vault" in line for line in lines)


def test_export_without_recapture_never_runs_the_launcher(world: dict[str, Path]) -> None:
    result = export(world, "--out", str(world["tmp"] / "export"), "--all")

    assert result.exit_code == 0, result.output
    assert calls(world) == []


def test_recapture_with_a_launcher_that_lacks_normalized_fails_without_v1_fallback(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "unknown")

    result = export(world, "--out", str(world["tmp"] / "export"), "--session", ENDED_ID, "--recapture")

    assert result.exit_code == 1
    assert len(calls(world)) == 1
    assert "--normalized" in result.stderr


def test_recapture_without_launcher_fails(world: dict[str, Path]) -> None:
    (world["builder"] / "vault_hooks.py").unlink()

    result = export(world, "--out", str(world["tmp"] / "export"), "--session", ENDED_ID, "--recapture")

    assert result.exit_code == 1
    assert "vault_hooks.py" in result.stderr
    assert (world["tmp"] / "export" / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl").is_file()
