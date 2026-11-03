"""`vg hook capture` with a fake Vault hook launcher (spec V5, 계약6, A-4 unit level, A-18).

The fake ``vault_hooks.py`` records its arguments and stdin to a log file outside the Vault and
prints a fixed ``sessions capture --json`` result. It never writes inside the Vault.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner, Result

from vault_graph.interface.cli.main import app
from vault_graph.interface.composition.adapters.vault_capture_cli import CaptureOutcome, run_capture

runner = CliRunner()

FAKE_LAUNCHER = """\
import json, os, sys, time
data = sys.stdin.buffer.read()
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": data.decode("utf-8")}) + "\\n")
mode = os.environ.get("FAKE_LAUNCHER_MODE", "written")
if mode == "sleep":
    time.sleep(30)
if mode == "crash":
    sys.stderr.write("launcher broke\\n")
    sys.exit(1)
if mode == "garbage":
    print("not json")
    sys.exit(0)
sys.stderr.write("launcher note\\n")
result = {
    "status": mode,
    "message": "fake",
    "vault": None if mode == "skipped" else "proj-vault",
    "path": "raw/sessions/2026-11-02-s1.md" if mode == "written" else None,
    "turn_count": 2,
    "redactions": 0,
    "warnings": [],
}
print(json.dumps(result))
"""

HOOK_JSON = (
    b'{"session_id": "s1", "transcript_path": "/tmp/t.jsonl", "cwd": "/tmp/repo", '
    b'"hook_event_name": "SessionEnd", "reason": "exit", "note": "\xed\x95\x9c"}'
)


def tree_digest(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    config = tmp_path / "claude" / "vault-builder"
    config.mkdir(parents=True)
    vault = tmp_path / "vaults" / "proj-vault"
    (vault / "raw" / "sessions").mkdir(parents=True)
    (vault / "wiki").mkdir()
    (vault / "wiki" / "page.md").write_text("# Page\n", encoding="utf-8")
    (vault / "raw" / "sessions" / "old.md").write_text("old\n", encoding="utf-8")
    vault_map = config / "vault-map.json"
    vault_map.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"proj-vault": {"path": str(vault), "role": "personal"}},
                "projects": {},
            }
        ),
        encoding="utf-8",
    )
    launcher = config / "vault_hooks.py"
    launcher.write_text(FAKE_LAUNCHER, encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "launcher.log"
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(log))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("FAKE_LAUNCHER_MODE", raising=False)
    monkeypatch.delenv("VAULT_GRAPH_VAULT_MAP", raising=False)
    return {"vault": vault, "map": vault_map, "launcher": launcher, "home": home, "log": log}


def calls(log: Path) -> list[dict[str, object]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


# Adapter


def test_run_capture_passes_hook_json_unchanged_to_capture_direct(setup: dict[str, Path]) -> None:
    outcome = run_capture(HOOK_JSON, launcher=setup["launcher"], timeout_s=10)

    assert isinstance(outcome, CaptureOutcome)
    assert outcome.finished
    assert (outcome.status, outcome.vault, outcome.path) == ("written", "proj-vault", "raw/sessions/2026-11-02-s1.md")
    assert "launcher note" in outcome.stderr
    assert calls(setup["log"]) == [{"argv": ["capture", "--direct"], "stdin": HOOK_JSON.decode("utf-8")}]


def test_run_capture_reports_missing_launcher(tmp_path: Path) -> None:
    outcome = run_capture(HOOK_JSON, launcher=tmp_path / "vault_hooks.py", timeout_s=10)

    assert not outcome.finished
    assert outcome.problem is not None and "vault_hooks.py" in outcome.problem


def test_run_capture_stops_launcher_after_timeout(setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", "sleep")
    started = time.monotonic()

    outcome = run_capture(HOOK_JSON, launcher=setup["launcher"], timeout_s=0.5)

    assert time.monotonic() - started < 10
    assert not outcome.finished
    assert outcome.problem is not None and "0.5 seconds" in outcome.problem


def test_run_capture_reports_launcher_failure(setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", "crash")

    outcome = run_capture(HOOK_JSON, launcher=setup["launcher"], timeout_s=10)

    assert not outcome.finished
    assert outcome.problem is not None and "1" in outcome.problem
    assert "launcher broke" in outcome.stderr


def test_run_capture_keeps_unreadable_result_as_unknown(
    setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", "garbage")

    outcome = run_capture(HOOK_JSON, launcher=setup["launcher"], timeout_s=10)

    assert outcome.finished
    assert (outcome.status, outcome.vault, outcome.path) == ("unknown", None, None)


# CLI


def invoke(*args: str) -> Result:
    return runner.invoke(app, ["hook", "capture", *args], input=HOOK_JSON)


@pytest.mark.parametrize("mode", ["written", "no-new-turns", "skipped"])
def test_cli_exits_0_when_launcher_finishes(setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", mode)

    result = invoke("--vault-map", str(setup["map"]))

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    summary = [line for line in result.stderr.splitlines() if line.startswith("vg hook capture:")]
    assert len(summary) == 1
    assert f"status={mode}" in summary[0]
    if mode == "written":
        assert "vault=proj-vault" in summary[0]
        assert "path=raw/sessions/2026-11-02-s1.md" in summary[0]
    assert calls(setup["log"]) == [{"argv": ["capture", "--direct"], "stdin": HOOK_JSON.decode("utf-8")}]


def test_cli_finds_launcher_next_to_vault_map_from_environment(
    setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAULT_GRAPH_VAULT_MAP", str(setup["map"]))

    result = invoke()

    assert result.exit_code == 0, result.output
    assert len(calls(setup["log"])) == 1


def test_cli_exits_3_when_launcher_is_missing(setup: dict[str, Path]) -> None:
    setup["launcher"].unlink()

    result = invoke("--vault-map", str(setup["map"]))

    assert result.exit_code == 3
    assert "vg hook capture:" in result.stderr
    assert "vault_hooks.py" in result.stderr


def test_cli_exits_3_after_timeout(setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", "sleep")

    result = invoke("--vault-map", str(setup["map"]), "--timeout", "0.5")

    assert result.exit_code == 3
    assert "0.5 seconds" in result.stderr


def test_cli_exits_3_when_launcher_fails(setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_LAUNCHER_MODE", "crash")

    result = invoke("--vault-map", str(setup["map"]))

    assert result.exit_code == 3
    assert "launcher broke" in result.stderr


def test_cli_writes_nothing_to_vault_or_graph_home_and_does_not_index(
    setup: dict[str, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def no_index(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("vg hook capture must not index")

    monkeypatch.setattr("vault_graph.interface.cli.main._text_embeddings", no_index)
    before = tree_digest(setup["vault"])
    graph_home = tmp_path / "graph-home"

    result = invoke("--vault-map", str(setup["map"]))

    assert result.exit_code == 0, result.output
    assert tree_digest(setup["vault"]) == before
    assert list(setup["home"].iterdir()) == []
    assert not graph_home.exists()


def test_cli_does_not_choose_vault_by_role(setup: dict[str, Path]) -> None:
    """The map has only a role personal vault. vg still hands the hook JSON to the launcher once."""

    result = invoke("--vault-map", str(setup["map"]))

    assert result.exit_code == 0, result.output
    assert calls(setup["log"]) == [{"argv": ["capture", "--direct"], "stdin": HOOK_JSON.decode("utf-8")}]


def test_cli_has_no_graph_home_option() -> None:
    result = runner.invoke(app, ["hook", "capture", "--graph-home", "x"], input=HOOK_JSON)

    assert result.exit_code == 2


def test_capture_adapter_has_no_vault_choice_indexing_or_file_writes() -> None:
    adapters = Path(__file__).parents[1] / "src" / "vault_graph" / "interface" / "composition" / "adapters"
    source = (adapters / "vault_capture_cli.py").read_text(encoding="utf-8")

    for forbidden in ("role", "index", "graph_home", "write_text", "write_bytes"):
        assert forbidden not in source, forbidden
