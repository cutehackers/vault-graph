"""`vg hook capture` normalizes the transcript and passes ``--normalized`` (spec 2026-11-05 §4.2.5, §6, A-3).

A fake ``vault_hooks.py`` records its arguments, stdin and the normalized file bytes to a log
outside every Vault. It exits 2 for ``--normalized`` when asked, like a launcher or Vault tool
without 요청S10. The Claude Code transcripts are copies of tests/fixtures/session_adapter.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "session_adapter"
OPEN_ID = "11111111-1111-4111-8111-111111111111"  # with_origin, expected with session_ended=False
ENDED_ID = "33333333-3333-4333-8333-333333333333"  # subagent_compact, expected with session_ended=True

FAKE_LAUNCHER = """\
import json, os, sys, time
data = sys.stdin.buffer.read()
argv = sys.argv[1:]
entry = {"argv": argv, "stdin": data.decode("utf-8")}
if "--normalized" in argv:
    path = argv[argv.index("--normalized") + 1]
    with open(path, encoding="utf-8") as stream:
        entry["normalized"] = stream.read()
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(entry) + "\\n")
normalized_mode = os.environ.get("FAKE_NORMALIZED_MODE", "ok")
if "--normalized" in argv:
    if normalized_mode == "unknown":
        sys.stderr.write("unrecognized arguments: --normalized\\n")
        sys.exit(2)
    if normalized_mode == "crash":
        sys.exit(1)
    if normalized_mode == "sleep":
        time.sleep(30)
else:
    direct_mode = os.environ.get("FAKE_DIRECT_MODE", "ok")
    if direct_mode == "crash":
        sys.stderr.write("direct broke\\n")
        sys.exit(1)
    if direct_mode == "sleep":
        time.sleep(30)
print(json.dumps({"status": "written", "vault": "proj-vault", "path": "raw/sessions/s.md"}))
"""


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config = tmp_path / "claude" / "vault-builder"
    config.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    (vault / "raw" / "sessions").mkdir(parents=True)
    vault_map = config / "vault-map.json"
    vault_map.write_text(
        json.dumps({"version": 2, "vaults": {"proj-vault": {"path": str(vault), "role": "project"}}, "projects": {}}),
        encoding="utf-8",
    )
    (config / "vault_hooks.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    project = tmp_path / "claude-config" / "projects" / "-work-demo-app"
    project.mkdir(parents=True)
    shutil.copytree(FIXTURES / "subagent_compact" / "raw", project, dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "with_origin" / "raw", project, dirs_exist_ok=True)
    home = tmp_path / "home"
    home.mkdir()
    temp = tmp_path / "os-temp"
    temp.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("TMPDIR", str(temp))
    monkeypatch.setattr("tempfile.tempdir", None)
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(tmp_path / "launcher.log"))
    for name in ("FAKE_NORMALIZED_MODE", "FAKE_DIRECT_MODE", "VAULT_GRAPH_VAULT_MAP"):
        monkeypatch.delenv(name, raising=False)
    return {
        "map": vault_map,
        "vault": vault,
        "project": project,
        "home": home,
        "temp": temp,
        "log": tmp_path / "launcher.log",
        "tmp": tmp_path,
    }


def hook_json(world: dict[str, Path], event: str, session_id: str, *, transcript: Path | None = None) -> bytes:
    path = transcript if transcript is not None else world["project"] / f"{session_id}.jsonl"
    payload = {
        "session_id": session_id,
        "transcript_path": str(path),
        "cwd": "/work/demo-app",
        "hook_event_name": event,
        "reason": "exit",
    }
    return json.dumps(payload).encode("utf-8")


def capture(world: dict[str, Path], payload: bytes, *args: str) -> Result:
    return runner.invoke(app, ["hook", "capture", "--vault-map", str(world["map"]), *args], input=payload)


def calls(world: dict[str, Path]) -> list[dict[str, str | list[str]]]:
    log = world["log"]
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def summary(result: Result) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.startswith("vg hook capture: status=")]


def warnings(result: Result) -> list[str]:
    return [line for line in result.stderr.splitlines() if line.startswith("vg hook capture: warning:")]


def expected(name: str) -> str:
    return (FIXTURES / name / "expected.jsonl").read_text(encoding="utf-8")


def write_settings(world: dict[str, Path], payload: object) -> None:
    configs = world["home"] / ".vault-graph" / "configs"
    configs.mkdir(parents=True, exist_ok=True)
    (configs / "session-export.json").write_text(json.dumps(payload), encoding="utf-8")


# Normalized path


def test_session_end_passes_normalized_file_with_every_exchange_closed(world: dict[str, Path]) -> None:
    payload = hook_json(world, "SessionEnd", ENDED_ID)

    result = capture(world, payload)

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    [call] = calls(world)
    argv = call["argv"]
    assert isinstance(argv, list)
    assert argv[:3] == ["capture", "--direct", "--normalized"]
    assert len(argv) == 4
    assert "--rerender" not in argv
    assert call["stdin"] == payload.decode("utf-8")
    assert call["normalized"] == expected("subagent_compact")
    assert len(summary(result)) == 1
    assert "input=normalized" in summary(result)[0]
    assert warnings(result) == []


def test_pre_compact_keeps_the_last_exchange_open(world: dict[str, Path]) -> None:
    result = capture(world, hook_json(world, "PreCompact", OPEN_ID))

    assert result.exit_code == 0, result.output
    [call] = calls(world)
    assert call["normalized"] == expected("with_origin")


def test_temporary_normalized_file_is_removed_after_the_run(world: dict[str, Path]) -> None:
    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    [call] = calls(world)
    argv = call["argv"]
    assert isinstance(argv, list)
    normalized = Path(argv[3])
    assert world["temp"].resolve() in normalized.resolve().parents
    assert not normalized.exists()
    assert list(world["temp"].iterdir()) == []
    assert list(world["home"].iterdir()) == []


# Fallback to capture --direct


def test_exit_code_2_reruns_capture_direct_with_the_same_hook_json(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "unknown")
    payload = hook_json(world, "SessionEnd", ENDED_ID)

    result = capture(world, payload)

    assert result.exit_code == 0, result.output
    first, second = calls(world)
    assert first["argv"][:3] == ["capture", "--direct", "--normalized"]
    assert second == {"argv": ["capture", "--direct"], "stdin": payload.decode("utf-8")}
    assert len(summary(result)) == 1
    assert "status=written" in summary(result)[0]
    assert "input=transcript" in summary(result)[0]
    assert list(world["temp"].iterdir()) == []


def test_exit_code_2_then_failed_direct_run_hands_off_with_3(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "unknown")
    monkeypatch.setenv("FAKE_DIRECT_MODE", "crash")

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 3
    assert len(calls(world)) == 2
    assert "direct broke" in result.stderr


def test_other_launcher_failure_with_normalized_hands_off_without_rerun(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "crash")

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 3
    assert len(calls(world)) == 1


def test_missing_transcript_runs_capture_direct_only(world: dict[str, Path]) -> None:
    payload = hook_json(world, "SessionEnd", ENDED_ID, transcript=world["tmp"] / "gone" / f"{ENDED_ID}.jsonl")

    result = capture(world, payload)

    assert result.exit_code == 0, result.output
    assert calls(world) == [{"argv": ["capture", "--direct"], "stdin": payload.decode("utf-8")}]
    assert "input=transcript" in summary(result)[0]


def test_hook_json_that_is_not_json_runs_capture_direct_only(world: dict[str, Path]) -> None:
    result = capture(world, b"not json")

    assert result.exit_code == 0, result.output
    assert calls(world) == [{"argv": ["capture", "--direct"], "stdin": "not json"}]


def test_normalization_error_falls_back_to_capture_direct(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_args: object, **_kwargs: object) -> object:
        raise ValueError("adapter broke")

    monkeypatch.setattr(
        "vault_graph.interface.composition.adapters.session_capture_runner.export_claude_code_session", broken
    )
    payload = hook_json(world, "SessionEnd", ENDED_ID)

    result = capture(world, payload)

    assert result.exit_code == 0, result.output
    assert calls(world) == [{"argv": ["capture", "--direct"], "stdin": payload.decode("utf-8")}]
    assert len(warnings(result)) == 1
    assert "adapter broke" in warnings(result)[0]


def test_timeout_budget_covers_both_runs(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "sleep")
    started = time.monotonic()

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID), "--timeout", "0.5")

    assert time.monotonic() - started < 10
    assert result.exit_code == 3
    assert "0.5 seconds" in result.stderr
    assert len(calls(world)) == 1


# Export settings


def test_export_settings_write_the_export_in_the_same_run(world: dict[str, Path]) -> None:
    out = world["tmp"] / "export"
    out.mkdir()
    write_settings(world, {"path": str(out), "agents": ["claude-code"], "raw": True})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    normalized = out / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl"
    assert normalized.read_text(encoding="utf-8") == expected("subagent_compact")
    raw_copy = out / "raw" / "claude-code" / ENDED_ID / f"{ENDED_ID}.jsonl"
    assert raw_copy.read_bytes() == (world["project"] / f"{ENDED_ID}.jsonl").read_bytes()
    [call] = calls(world)
    assert call["argv"] == ["capture", "--direct", "--normalized", str(normalized)]
    assert warnings(result) == []
    assert list(world["temp"].iterdir()) == []


def test_export_settings_without_raw_write_only_the_normalized_file(world: dict[str, Path]) -> None:
    out = world["tmp"] / "export"
    out.mkdir()
    write_settings(world, {"path": str(out), "agents": ["claude-code"], "raw": False})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert not (out / "raw").exists()
    assert (out / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl").is_file()


def test_missing_export_folder_skips_only_the_export_with_one_warning(world: dict[str, Path]) -> None:
    out = world["tmp"] / "unplugged-disk" / "export"
    write_settings(world, {"path": str(out), "agents": ["claude-code"]})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert len(warnings(result)) == 1
    assert str(out) in warnings(result)[0]
    assert not out.exists()
    [call] = calls(world)
    assert call["normalized"] == expected("subagent_compact")
    assert "input=normalized" in summary(result)[0]


def test_export_settings_for_other_agents_do_not_export(world: dict[str, Path]) -> None:
    out = world["tmp"] / "export"
    out.mkdir()
    write_settings(world, {"path": str(out), "agents": ["codex"]})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert list(out.iterdir()) == []
    assert warnings(result) == []


def test_export_folder_inside_a_vault_is_skipped_with_one_warning(world: dict[str, Path]) -> None:
    out = world["vault"] / "exports"
    out.mkdir()
    write_settings(world, {"path": str(out), "agents": ["claude-code"]})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert list(out.iterdir()) == []
    assert len(warnings(result)) == 1
    [call] = calls(world)
    assert call["normalized"] == expected("subagent_compact")


def test_broken_export_settings_warn_and_capture_goes_on(world: dict[str, Path]) -> None:
    configs = world["home"] / ".vault-graph" / "configs"
    configs.mkdir(parents=True)
    (configs / "session-export.json").write_text("{broken", encoding="utf-8")

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert len(warnings(result)) == 1
    assert len(calls(world)) == 1


def test_export_folder_files_stay_after_the_run(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_NORMALIZED_MODE", "unknown")
    out = world["tmp"] / "export"
    out.mkdir()
    write_settings(world, {"path": str(out), "agents": ["claude-code"], "raw": False})

    result = capture(world, hook_json(world, "SessionEnd", ENDED_ID))

    assert result.exit_code == 0, result.output
    assert (out / "normalized" / "claude-code" / f"{ENDED_ID}.jsonl").is_file()
    assert [call["argv"] for call in calls(world)][-1] == ["capture", "--direct"]
    assert os.listdir(world["temp"]) == []
