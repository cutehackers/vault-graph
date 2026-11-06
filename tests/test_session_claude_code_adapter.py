"""Claude Code adapter and vg-session-jsonl/1 (spec 2026-11-05 §4.2.2, 위험A2, A-1).

Fixtures under tests/fixtures/session_adapter/ are synthetic. Each case folder holds raw/ (what
composition would read) and expected.jsonl (the normalized bytes).
"""

import json
import random
from pathlib import Path

import pytest

from vault_graph.operation.sessions.claude_code_adapter import CLAUDE_CODE_ADAPTER_VERSION, ClaudeCodeAdapter
from vault_graph.operation.sessions.models import (
    NORMALIZED_SESSION_SCHEMA,
    ExchangeLine,
    SessionAdapter,
    SessionLine,
    SourceRecord,
    TurnLine,
)
from vault_graph.operation.sessions.normalized_jsonl import encode_session

FIXTURES = Path(__file__).parent / "fixtures" / "session_adapter"
_FAKE_SECRETS = ("hunter2xyz", "FakeTestToken0123456789", "abcDEF123456ghi789")

# (case folder, session_ended)
_CASES = (("with_origin", False), ("without_origin", True), ("subagent_compact", True))


def _records(case: str) -> list[SourceRecord]:
    raw = FIXTURES / case / "raw"
    records: list[SourceRecord] = []
    for path in sorted(item for item in raw.rglob("*") if item.is_file()):
        relative = path.relative_to(raw).as_posix()
        text = path.read_text(encoding="utf-8")
        if relative.endswith(".jsonl"):
            records.extend(
                SourceRecord(source_path=relative, line_no=number, text=line)
                for number, line in enumerate(text.splitlines(), start=1)
            )
        else:
            records.append(SourceRecord(source_path=relative, line_no=1, text=text))
    return records


def _normalize(case: str, *, session_ended: bool) -> str:
    return encode_session(ClaudeCodeAdapter(session_ended=session_ended).normalize(_records(case)))


def _lines(case: str, *, session_ended: bool) -> tuple[object, ...]:
    return ClaudeCodeAdapter(session_ended=session_ended).normalize_session(_records(case)).lines


def _turns(case: str, *, session_ended: bool) -> dict[str, TurnLine]:
    return {line.turn_id: line for line in _lines(case, session_ended=session_ended) if isinstance(line, TurnLine)}


def _exchanges(case: str, *, session_ended: bool) -> list[ExchangeLine]:
    return [line for line in _lines(case, session_ended=session_ended) if isinstance(line, ExchangeLine)]


def test_adapter_meets_the_protocol() -> None:
    adapter: SessionAdapter = ClaudeCodeAdapter()

    assert (adapter.agent, adapter.version) == ("claude-code", CLAUDE_CODE_ADAPTER_VERSION)
    assert CLAUDE_CODE_ADAPTER_VERSION == "claude-code/1"


@pytest.mark.parametrize(("case", "session_ended"), _CASES)
def test_fixture_output_matches_expected_bytes(case: str, session_ended: bool) -> None:
    expected = (FIXTURES / case / "expected.jsonl").read_bytes()

    first = _normalize(case, session_ended=session_ended).encode("utf-8")
    second = _normalize(case, session_ended=session_ended).encode("utf-8")

    assert first == expected
    assert second == first


@pytest.mark.parametrize(("case", "session_ended"), _CASES)
def test_record_input_order_does_not_change_output(case: str, session_ended: bool) -> None:
    shuffled = _records(case)
    random.Random(7).shuffle(shuffled)

    result = encode_session(ClaudeCodeAdapter(session_ended=session_ended).normalize(shuffled))

    assert result == _normalize(case, session_ended=session_ended)


@pytest.mark.parametrize(("case", "session_ended"), _CASES)
def test_every_line_has_schema_and_kind_first(case: str, session_ended: bool) -> None:
    lines = [json.loads(line) for line in _normalize(case, session_ended=session_ended).splitlines()]

    assert [list(line)[:2] for line in lines] == [["schema", "kind"]] * len(lines)
    assert {line["schema"] for line in lines} == {NORMALIZED_SESSION_SCHEMA}
    assert lines[0]["kind"] == "session"
    assert [line["kind"] for line in lines].count("session") == 1


def test_non_human_user_records_are_not_human_turns() -> None:
    turns = _turns("with_origin", session_ended=False)
    compact = _turns("subagent_compact", session_ended=True)

    assert turns["u-005"].turn_kind == "notification"  # turnOrigin task_notification
    assert turns["u-006"].turn_kind == "meta"  # isMeta
    assert turns["u-002"].turn_kind == "tool_only"  # tool_result
    assert compact["u-202"].turn_kind == "compact_summary"  # isCompactSummary with turnOrigin human
    assert [turn_id for turn_id, turn in turns.items() if turn.turn_kind == "human"] == ["u-001", "u-007"]


def test_records_without_origin_use_the_angle_bracket_rule() -> None:
    turns = _turns("without_origin", session_ended=True)

    assert turns["u-101"].turn_kind == "meta"  # starts with "<"
    assert turns["u-107"].turn_kind == "meta"  # interruption marker
    assert [turn_id for turn_id, turn in turns.items() if turn.turn_kind == "human"] == ["u-102", "u-103", "u-105"]


def test_actions_carry_target_ok_and_error_head() -> None:
    turns = _turns("with_origin", session_ended=False)

    edit = turns["a-002"].actions[0]
    bash = turns["a-003"].actions[0]
    fetch = turns["a-004"].actions[0]
    pending = turns["a-006"].actions[0]

    assert (edit.tool, edit.call_id, edit.target, edit.ok, edit.error_head) == (
        "Edit",
        "toolu_edit1",
        "/work/demo-app/src/app.py",
        True,
        None,
    )
    assert bash.tool == "Bash"
    assert bash.target == "ANTHROPIC_API_KEY=[REDACTED:anthropic-key] pytest -q tests/test_app.py"
    assert (bash.ok, bash.error_head) == (False, "Auth failed: Bearer [REDACTED:bearer] rejected")
    assert (fetch.tool, fetch.target, fetch.ok) == ("WebFetch", "https://docs.example.com/pytest?page=2", True)
    assert (pending.target, pending.ok) == ("ls docs", None)
    assert turns["a-003"].turn_kind == "tool_only"
    assert turns["a-002"].turn_kind == "assistant_text"


def test_error_head_is_first_line_and_redacted() -> None:
    turns = _turns("without_origin", session_ended=True)

    assert turns["a-102"].actions[0].error_head == "ls: /root: Permission denied"
    assert turns["a-103"].actions[0].ok is False  # toolUseResult.interrupted


def test_fixed_secrets_do_not_survive_in_text_commands_or_error_head() -> None:
    for case, session_ended in _CASES:
        output = _normalize(case, session_ended=session_ended)
        for secret in _FAKE_SECRETS:
            assert secret not in output, (case, secret)
    raw = "".join(record.text for case, _ in _CASES for record in _records(case))
    assert all(secret in raw for secret in _FAKE_SECRETS)


def test_exchanges_group_turns_and_report_outcome() -> None:
    with_origin = _exchanges("with_origin", session_ended=False)
    without_origin = _exchanges("without_origin", session_ended=True)

    first, second = with_origin
    assert (first.exchange_id, first.closed, first.outcome, first.prompt_source) == ("u-001", True, "answered", "typed")
    assert first.tools == {"Bash": 1, "Edit": 1, "WebFetch": 1}
    assert first.files_touched == ("/work/demo-app/src/app.py",)
    assert first.commands == ("ANTHROPIC_API_KEY=[REDACTED:anthropic-key] pytest -q tests/test_app.py",)
    assert first.errors == 1
    assert (second.exchange_id, second.closed, second.outcome) == ("u-007", False, "open")
    assert [(item.exchange_id, item.outcome) for item in without_origin] == [
        ("u-102", "answered"),  # the leading /model meta turn joins the first exchange
        ("u-103", "tool_error_unresolved"),
        ("u-105", "interrupted"),
    ]
    assert [item.seq for item in without_origin] == [1, 2, 3]
    assert without_origin[0].started_at == "2026-03-02T08:00:00.000Z"


def test_subagent_exchange_comes_after_main_and_links_the_agent_call() -> None:
    lines = _lines("subagent_compact", session_ended=False)
    exchanges = [line for line in lines if isinstance(line, ExchangeLine)]
    turns = {line.turn_id: line for line in lines if isinstance(line, TurnLine)}

    main, subagent = exchanges
    assert (main.agent_scope, main.closed, main.outcome) == ("main", False, "open")
    assert (subagent.agent_scope, subagent.subagent_type, subagent.parent_tool_use_id) == (
        "subagent:a7f3",
        "code-reviewer",
        "toolu_agent1",
    )
    assert (subagent.closed, subagent.outcome) == (True, "answered")
    assert subagent.files_touched == ("/work/demo-app/src/app.py",)
    assert (turns["s-301"].turn_kind, turns["s-301"].agent_id, turns["s-301"].sidechain) == ("human", "a7f3", True)
    assert main.tools == {"Agent": 1}
    assert turns["a-201"].actions[0].target == "code-reviewer"


def test_turn_order_follows_parent_tree_and_skips_duplicates() -> None:
    lines = _lines("with_origin", session_ended=False)
    turn_ids = [line.turn_id for line in lines if isinstance(line, TurnLine)]
    turns = {line.turn_id: line for line in lines if isinstance(line, TurnLine)}

    assert turn_ids == [
        *("u-001", "a-002", "u-002", "a-003", "u-003", "a-004", "u-004", "a-005", "u-005", "u-006"),
        *("u-007", "a-006"),
    ]
    assert turns["a-002"].parent_id == "u-001"  # attachment and thinking-only records are skipped
    assert turns["u-001"].parent_id is None


def test_session_line_and_report() -> None:
    result = ClaudeCodeAdapter().normalize_session(_records("with_origin"))
    session = result.lines[0]

    assert isinstance(session, SessionLine)
    assert (session.session_id, session.agent, session.adapter) == (
        "11111111-1111-4111-8111-111111111111",
        "claude-code",
        "claude-code/1",
    )
    assert (session.cwd, session.project, session.git_branch, session.agent_version) == (
        "/work/demo-app",
        "demo-app",
        "main",
        "2.1.300",
    )
    assert session.title is not None
    assert (session.title.text, session.title.source) == ("Fix failing app test", "ai-title")
    assert (session.started_at, session.ended_at) == ("2026-11-01T10:00:00.000Z", "2026-11-01T10:01:01.000Z")
    assert session.source_paths == ("11111111-1111-4111-8111-111111111111.jsonl",)
    assert len(session.source_sha256) == 64
    assert result.invalid_lines == 1
    assert dict(result.unknown_record_types) == {"future-record": 1}


def test_source_sha256_changes_when_the_source_grows() -> None:
    records = _records("with_origin")
    grown = [*records, SourceRecord(source_path=records[-1].source_path, line_no=records[-1].line_no + 1, text="{}")]

    before = ClaudeCodeAdapter().normalize_session(records).lines[0]
    after = ClaudeCodeAdapter().normalize_session(grown).lines[0]

    assert isinstance(before, SessionLine) and isinstance(after, SessionLine)
    assert before.source_sha256 != after.source_sha256
