"""`CaptureOutcome.exchange_count` and `recapture_session(hook_cwd=...)` (spec 2026-11-25 D4, A9).

A fake ``vault_hooks.py`` records its arguments and stdin, then prints the result line given in
``FAKE_RESULT``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vault_graph.interface.composition.adapters.session_capture_runner import recapture_session
from vault_graph.interface.composition.adapters.session_export_files import ClaudeCodeSession
from vault_graph.interface.composition.adapters.vault_capture_cli import run_capture

SESSION_ID = "33333333-3333-4333-8333-333333333333"

FAKE_LAUNCHER = """\
import json, os, sys
data = sys.stdin.buffer.read()
with open(os.environ["FAKE_LAUNCHER_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": data.decode("utf-8")}) + "\\n")
print(os.environ["FAKE_RESULT"])
"""


@pytest.fixture
def launcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vault_hooks.py"
    path.write_text(FAKE_LAUNCHER, encoding="utf-8")
    monkeypatch.setenv("FAKE_LAUNCHER_LOG", str(tmp_path / "launcher.log"))
    monkeypatch.setenv("FAKE_RESULT", json.dumps({"status": "written", "vault": "v", "path": "raw/p.md"}))
    return path


def _calls(launcher: Path) -> list[dict[str, object]]:
    log = launcher.parent / "launcher.log"
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _session(tmp_path: Path, *, newest: bool = False) -> ClaudeCodeSession:
    return ClaudeCodeSession(session_id=SESSION_ID, project_dir=tmp_path / "proj", modified_at=0.0, newest=newest)


def _normalized(tmp_path: Path, cwd: str = "/work/repo/sub") -> Path:
    path = tmp_path / "normalized.jsonl"
    content = json.dumps({"type": "session", "cwd": cwd}) + "\n" + json.dumps({"type": "exchange"}) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"status": "written", "vault": "v", "path": "p", "exchange_count": 7}, 7),
        ({"status": "written", "vault": "v", "path": "p", "exchange_count": 0}, 0),
        ({"status": "no-new-turns", "vault": "v"}, None),
        ({"status": "written", "exchange_count": "7"}, None),
        ({"status": "written", "exchange_count": True}, None),
    ],
)
def test_exchange_count_is_read_from_the_result_line(
    launcher: Path, monkeypatch: pytest.MonkeyPatch, result: dict[str, object], expected: int | None
) -> None:
    monkeypatch.setenv("FAKE_RESULT", json.dumps(result))

    outcome = run_capture(b"{}", launcher=launcher, timeout_s=30)

    assert outcome.finished
    assert outcome.exchange_count == expected


def test_exchange_count_is_none_without_a_result_line(launcher: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_RESULT", "not json")

    outcome = run_capture(b"{}", launcher=launcher, timeout_s=30)

    assert outcome.status == "unknown"
    assert outcome.exchange_count is None


def test_hook_cwd_replaces_only_the_hook_json_cwd(launcher: Path, tmp_path: Path) -> None:
    normalized = _normalized(tmp_path)
    before = normalized.read_bytes()

    outcome = recapture_session(_session(tmp_path), normalized, launcher=launcher, hook_cwd="/work/repo")

    assert outcome.status == "written"
    (call,) = _calls(launcher)
    hook = json.loads(str(call["stdin"]))
    assert hook["cwd"] == "/work/repo"
    assert hook["hook_event_name"] == "SessionEnd"
    assert call["argv"] == ["capture", "--direct", "--normalized", str(normalized), "--rerender"]
    assert normalized.read_bytes() == before


def test_hook_cwd_is_used_when_the_normalized_file_has_no_cwd(launcher: Path, tmp_path: Path) -> None:
    normalized = tmp_path / "normalized.jsonl"
    normalized.write_text(json.dumps({"type": "session"}) + "\n", encoding="utf-8")

    recapture_session(_session(tmp_path), normalized, launcher=launcher, hook_cwd="/work/repo")

    (call,) = _calls(launcher)
    assert json.loads(str(call["stdin"]))["cwd"] == "/work/repo"


def test_default_hook_json_and_arguments_are_unchanged(launcher: Path, tmp_path: Path) -> None:
    normalized = _normalized(tmp_path)
    session = _session(tmp_path)

    recapture_session(session, normalized, launcher=launcher)

    (call,) = _calls(launcher)
    assert call["argv"] == ["capture", "--direct", "--normalized", str(normalized), "--rerender"]
    assert json.loads(str(call["stdin"])) == {
        "session_id": SESSION_ID,
        "transcript_path": str(session.main_file),
        "hook_event_name": "SessionEnd",
        "cwd": "/work/repo/sub",
    }


def test_newest_session_still_gets_pre_compact_by_default(launcher: Path, tmp_path: Path) -> None:
    recapture_session(_session(tmp_path, newest=True), _normalized(tmp_path), launcher=launcher)

    (call,) = _calls(launcher)
    assert json.loads(str(call["stdin"]))["hook_event_name"] == "PreCompact"
