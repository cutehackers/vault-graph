"""`vg session migrate` (spec 2026-11-25-v1-session-recapture A2-A8).

A fake ``vault_hooks.py`` next to the vault-map file records its arguments, stdin and the normalized file,
and writes a v2 part into the temporary Vault the way the Vault tool does with ``--rerender``: the next
part number, ``first_exchange_id``/``last_exchange_id``, and one ``vg:exchange`` meta line per exchange
with turns. ``FAKE_MODE`` makes it misbehave. The Claude Code folder is a copy of
tests/fixtures/session_adapter found through CLAUDE_CONFIG_DIR.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app
from vault_graph.operation.scope.facts_settings import facts_queue_dir

runner = CliRunner()

FIXTURES = Path(__file__).parent / "fixtures" / "session_adapter"
COMPACT_ID = "33333333-3333-4333-8333-333333333333"  # 2026-11-03T14:00:00Z..14:06:01Z, cwd /work/demo-app
ORIGIN_ID = "11111111-1111-4111-8111-111111111111"  # 2026-11-01T10:00:00Z..10:01:01Z, two exchanges
MISSING_ID = "55555555-5555-4555-8555-555555555555"
OLD = 1_700_000_000

FAKE_LAUNCHER = """\
import json, os, re, sys
argv = sys.argv[1:]
data = sys.stdin.buffer.read().decode("utf-8")
normalized = argv[argv.index("--normalized") + 1]
lines = [json.loads(line) for line in open(normalized, encoding="utf-8")]
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": argv, "stdin": data, "lines": lines}) + "\\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "fail_exit":
    sys.stderr.write("boom\\n")
    sys.exit(1)
if mode == "skipped":
    print(json.dumps({"status": "skipped", "message": "not inside a git repository", "vault": None, "path": None}))
    sys.exit(0)
session = lines[0]
with_turns = {line["exchange_id"] for line in lines if line["kind"] == "turn"}
exchanges = [line for line in lines if line["kind"] == "exchange" and line["exchange_id"] in with_turns]
folder = os.path.join(os.environ["FAKE_VAULT_ROOT"], "raw", "sessions", "claude-code")
os.makedirs(folder, exist_ok=True)
sid = session["session_id"]
parts = [int(m.group(1)) for name in os.listdir(folder) for m in [re.search(sid + r"-part(\\d+)\\.md$", name)] if m]
part = max(parts, default=0) + 1
meta = []
for item in exchanges:
    started, ended = item["started_at"], item["ended_at"]
    if mode == "no_cover":
        started = ended = exchanges[0]["started_at"]
    meta.append(f"<!-- vg:exchange id={item['exchange_id']} scope=main started={started} ended={ended} -->")
path = f"raw/sessions/claude-code/2026-11-01-{sid}-part{part}.md"
text = (
    "---\\nschema: vault-session/v2\\nagent: claude-code\\n"
    f"session_id: {sid}\\npart: {part}\\n"
    f'first_exchange_id: "{exchanges[0]["exchange_id"]}"\\nlast_exchange_id: "{exchanges[-1]["exchange_id"]}"\\n'
    f'first_turn_at: "{exchanges[0]["started_at"]}"\\nlast_turn_at: "{exchanges[0]["started_at"]}"\\n'
    "---\\n\\n" + "\\n".join(meta) + "\\n"
)
with open(os.path.join(os.environ["FAKE_VAULT_ROOT"], path), "w", encoding="utf-8") as out:
    out.write(text)
count = len(exchanges) - 1 if mode == "bad_count" else len(exchanges)
vault = "other-vault" if mode == "wrong_vault" else "proj-vault"
print(json.dumps({"status": "written", "vault": vault, "path": path, "exchange_count": count}))
"""


def v1_part(session_id: str, part: int, first: str, last: str) -> str:
    return (
        "---\nschema: vault-session/v1\nagent: claude-code\n"
        f'session_id: "{session_id}"\npart: {part}\n'
        f'first_turn_at: "{first}"\nlast_turn_at: "{last}"\n---\n\n## {first} user\n\nhello\n'
    )


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config_dir = tmp_path / "claude-config"
    project = config_dir / "projects" / "-work-demo-app"
    project.mkdir(parents=True)
    shutil.copytree(FIXTURES / "subagent_compact" / "raw", project, dirs_exist_ok=True)
    shutil.copytree(FIXTURES / "with_origin" / "raw", project, dirs_exist_ok=True)
    _age(project)
    builder = tmp_path / "claude" / "vault-builder"
    builder.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    sessions = vault / "raw" / "sessions" / "claude-code"
    sessions.mkdir(parents=True)
    (sessions / f"2026-11-03-{COMPACT_ID}-part1.md").write_text(
        v1_part(COMPACT_ID, 1, "2026-11-03T14:00:00.000Z", "2026-11-03T14:06:00.000Z"), encoding="utf-8"
    )
    (sessions / f"2026-11-01-{ORIGIN_ID}-part1.md").write_text(
        v1_part(ORIGIN_ID, 1, "2026-11-01T10:00:00.000Z", "2026-11-01T10:01:00.000Z"), encoding="utf-8"
    )
    (sessions / f"2026-11-02-{MISSING_ID}-part1.md").write_text(
        v1_part(MISSING_ID, 1, "2026-11-02T10:00:00.000Z", "2026-11-02T10:01:00.000Z"), encoding="utf-8"
    )
    empty = tmp_path / "vaults" / "personal"
    empty.mkdir(parents=True)
    vault_map = builder / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {
                    "proj-vault": {"path": str(vault), "role": "project"},
                    "personal": {"path": str(empty), "role": "personal"},
                },
                "projects": {},
            }
        ),
        encoding="utf-8",
    )
    (builder / "vault_hooks.py").write_text(FAKE_LAUNCHER, encoding="utf-8")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(vault_map))
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(tmp_path / "launcher.log"))
    monkeypatch.setenv("FAKE_VAULT_ROOT", str(vault))
    monkeypatch.delenv("FAKE_MODE", raising=False)
    return {
        "project": project,
        "map": vault_map,
        "builder": builder,
        "vault": vault,
        "sessions": sessions,
        "log": tmp_path / "launcher.log",
        "home": tmp_path / "graph-home",
    }


def _age(folder: Path) -> None:
    for path in folder.rglob("*"):
        if path.is_file():
            os.utime(path, (OLD, OLD))


def migrate(world: dict[str, Path], *args: str) -> Result:
    return runner.invoke(app, ["session", "migrate", "--graph-home", str(world["home"]), *args], catch_exceptions=False)


def calls(world: dict[str, Path]) -> list[dict[str, object]]:
    if not world["log"].exists():
        return []
    return [json.loads(line) for line in world["log"].read_text(encoding="utf-8").splitlines()]


def snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def line_for(result: Result, session_id: str) -> str:
    return next(line for line in result.output.splitlines() if f" {session_id} " in line)


def summary(result: Result, vault: str) -> str:
    return next(line for line in result.output.splitlines() if line.startswith(f"vault={vault} "))


def test_dry_run_lists_targets_and_writes_and_runs_nothing(world: dict[str, Path]) -> None:
    before = snapshot(world["vault"])
    temp_before = set(os.listdir(tempfile.gettempdir()))

    result = migrate(world, "--dry-run")

    assert result.exit_code == 0, result.output
    assert "proj-vault " + COMPACT_ID + " target v1_parts=1" in result.output
    assert "proj-vault " + ORIGIN_ID + " target v1_parts=1" in result.output
    assert line_for(result, MISSING_ID).startswith(f"proj-vault {MISSING_ID} source_missing")
    assert summary(result, "proj-vault") == (
        "vault=proj-vault v1_parts=3 covered=0 uncovered=3 source_missing=1 unreadable=0"
    )
    assert summary(result, "personal").startswith("vault=personal v1_parts=0 ")
    assert calls(world) == []
    assert snapshot(world["vault"]) == before
    created = set(os.listdir(tempfile.gettempdir())) - temp_before
    assert not any(name.startswith("vg-migrate-") for name in created)


def test_run_recaptures_through_the_launcher_as_ended_sessions(world: dict[str, Path]) -> None:
    before = snapshot(world["vault"])

    result = migrate(world)

    assert result.exit_code == 0, result.output
    assert line_for(result, ORIGIN_ID).startswith(f"proj-vault {ORIGIN_ID} written v1_parts=1 exchanges=2")
    assert line_for(result, COMPACT_ID).startswith(f"proj-vault {COMPACT_ID} written v1_parts=1 exchanges=2")
    assert summary(result, "proj-vault") == (
        "vault=proj-vault v1_parts=3 covered=2 uncovered=1 source_missing=1 unreadable=0"
    )
    recorded = calls(world)
    assert len(recorded) == 2
    for call in recorded:
        argv = call["argv"]
        assert isinstance(argv, list)
        assert argv[:2] == ["capture", "--direct"]
        assert argv[argv.index("--normalized") + 2] == "--rerender"
        assert not Path(argv[argv.index("--normalized") + 1]).exists()
        assert not str(argv[argv.index("--normalized") + 1]).startswith(str(world["vault"]))
        hook = json.loads(str(call["stdin"]))
        assert hook["hook_event_name"] == "SessionEnd"
        lines = call["lines"]
        assert isinstance(lines, list)
        assert all(line["closed"] for line in lines if line["kind"] == "exchange")
    after = snapshot(world["vault"])
    assert {key: after[key] for key in before} == before
    assert len(after) == len(before) + 2
    assert not facts_queue_dir(world["home"]).exists() or not any(facts_queue_dir(world["home"]).iterdir())


def test_missing_cwd_falls_back_to_the_nearest_existing_parent(world: dict[str, Path]) -> None:
    result = migrate(world, "--vault", "proj-vault")

    assert result.exit_code == 0, result.output
    hook = json.loads(str(calls(world)[0]["stdin"]))
    assert hook["cwd"] == "/"
    assert "cwd_fallback=/" in line_for(result, ORIGIN_ID)
    lines = calls(world)[0]["lines"]
    assert isinstance(lines, list)
    assert lines[0]["cwd"] == "/work/demo-app"


def test_existing_cwd_is_passed_as_is(world: dict[str, Path], tmp_path: Path) -> None:
    workdir = tmp_path / "work" / "demo-app"
    workdir.mkdir(parents=True)
    source = world["project"] / f"{ORIGIN_ID}.jsonl"
    source.write_text(source.read_text(encoding="utf-8").replace("/work/demo-app", str(workdir)), encoding="utf-8")
    os.utime(source, (OLD, OLD))

    result = migrate(world)

    assert result.exit_code == 0, result.output
    origin = next(call for call in calls(world) if ORIGIN_ID in str(call["stdin"]))
    assert json.loads(str(origin["stdin"]))["cwd"] == str(workdir)
    assert "cwd_fallback" not in line_for(result, ORIGIN_ID)


def test_second_run_writes_nothing(world: dict[str, Path]) -> None:
    assert migrate(world).exit_code == 0
    parts = snapshot(world["vault"])

    result = migrate(world)

    assert result.exit_code == 0, result.output
    assert len(calls(world)) == 2
    assert snapshot(world["vault"]) == parts
    session_lines = [line for line in result.output.splitlines() if line.startswith("proj-vault ")]
    assert session_lines == [line_for(result, MISSING_ID)]


def test_exchange_count_mismatch_fails(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODE", "bad_count")

    result = migrate(world)

    assert result.exit_code == 1
    line = line_for(result, ORIGIN_ID)
    assert " failed:exchange_count " in line
    assert line.endswith(" expected=2 got=1")
    assert "migrate_failed_sessions: 2" in result.output


def test_uncovered_after_write_fails_and_is_not_written_again(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_MODE", "no_cover")

    first = migrate(world)

    assert first.exit_code == 1
    assert " failed:uncovered " in line_for(first, ORIGIN_ID)
    assert len(calls(world)) == 2
    parts = snapshot(world["vault"])

    second = migrate(world)

    assert second.exit_code == 1
    assert " already_recaptured_uncovered " in line_for(second, ORIGIN_ID)
    assert len(calls(world)) == 2
    assert snapshot(world["vault"]) == parts


def test_written_to_another_vault_stops_the_run(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_MODE", "wrong_vault")

    result = migrate(world)

    assert result.exit_code == 1
    assert " failed:vault_mismatch " in line_for(result, ORIGIN_ID)
    assert len(calls(world)) == 1
    assert "migrate_stopped" in result.output


def test_recent_source_is_skipped_without_failing(world: dict[str, Path]) -> None:
    now = time.time()
    os.utime(world["project"] / f"{ORIGIN_ID}.jsonl", (now, now))

    result = migrate(world)

    assert result.exit_code == 0, result.output
    assert line_for(result, ORIGIN_ID).startswith(f"proj-vault {ORIGIN_ID} recent")
    assert all(ORIGIN_ID not in str(call["stdin"]) for call in calls(world))


@pytest.mark.parametrize("mode", ["skipped", "fail_exit"])
def test_launcher_problems_fail_and_the_run_continues(
    world: dict[str, Path], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("FAKE_MODE", mode)

    result = migrate(world)

    assert result.exit_code == 1
    assert len(calls(world)) == 2
    assert " failed:" in line_for(result, ORIGIN_ID)
    assert " failed:" in line_for(result, COMPACT_ID)


def test_missing_launcher_fails(world: dict[str, Path]) -> None:
    (world["builder"] / "vault_hooks.py").unlink()

    result = migrate(world)

    assert result.exit_code == 1
    assert " failed:launcher " in line_for(result, ORIGIN_ID)


def test_duplicate_source_fails_without_running(world: dict[str, Path]) -> None:
    other = world["project"].parent / "-other"
    other.mkdir()
    shutil.copy(world["project"] / f"{ORIGIN_ID}.jsonl", other / f"{ORIGIN_ID}.jsonl")
    _age(other)

    result = migrate(world)

    assert result.exit_code == 1
    assert " failed:duplicate_source " in line_for(result, ORIGIN_ID)
    assert all(ORIGIN_ID not in str(call["stdin"]) for call in calls(world))


def test_unreadable_v1_part_is_reported_and_its_session_is_not_recaptured(world: dict[str, Path]) -> None:
    (world["sessions"] / "2026-11-04-bad-part1.md").write_text(
        v1_part("bad", 1, "not a time", "2026-11-04T00:00:00Z"), encoding="utf-8"
    )
    (world["sessions"] / f"2026-11-01-{ORIGIN_ID}-part2.md").write_text(
        v1_part(ORIGIN_ID, 2, "2026-11-01T10:00:30.000Z", "broken"), encoding="utf-8"
    )

    result = migrate(world)

    assert result.exit_code == 1
    assert (
        "proj-vault bad failed:unreadable_part v1_parts=1 exchanges=- raw/sessions/claude-code/2026-11-04-bad-part1.md"
        in (result.output)
    )
    assert f"proj-vault {ORIGIN_ID} failed:unreadable_part " in result.output
    assert f"proj-vault {ORIGIN_ID} written" not in result.output
    assert all(ORIGIN_ID not in str(call["stdin"]) for call in calls(world))
    assert "unreadable=2" in summary(result, "proj-vault")


def test_unknown_vault_or_broken_map_runs_nothing(world: dict[str, Path]) -> None:
    unknown = migrate(world, "--vault", "nope")
    assert unknown.exit_code == 1
    assert "unknown_vault: nope" in unknown.output

    world["map"].write_text("{", encoding="utf-8")
    broken = migrate(world)
    assert broken.exit_code == 1
    assert "vault_map_invalid" in broken.output
    assert calls(world) == []
