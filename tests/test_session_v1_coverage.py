"""v1 part coverage and normalized exchange counts (spec 2026-11-25-v1-session-recapture D2, I2, F9, A1)."""

from __future__ import annotations

from dataclasses import replace

from vault_graph.operation.sessions.models import ExchangeLine, NormalizedLine, SessionLine, TurnLine
from vault_graph.operation.sessions.v1_coverage import (
    V1_SCHEMA,
    V2_SCHEMA,
    ExchangeSummary,
    PartHead,
    exchange_summary,
    exchange_time_range,
    uncovered_v1_parts,
)

SESSION = "ae647dc5-0913-4815-acd3-87d60f77b9bb"


def _v1(
    path: str = "raw/sessions/claude-code/s-part1.md",
    *,
    vault: str = "vault-graph",
    session_id: str | None = SESSION,
    first: str | None = "2026-11-07T09:00:00.000Z",
    last: str | None = "2026-11-07T10:00:00.000Z",
) -> PartHead:
    return PartHead(
        vault=vault,
        path=path,
        schema=V1_SCHEMA,
        agent="claude-code",
        session_id=session_id,
        part=1,
        first_turn_at=first,
        last_turn_at=last,
    )


def _v2(
    path: str = "raw/sessions/claude-code/s-part2.md",
    *,
    vault: str = "vault-graph",
    session_id: str | None = SESSION,
    started: str | None = "2026-11-07T08:59:00Z",
    ended: str | None = "2026-11-07T10:01:00Z",
    last_turn_at: str | None = None,
) -> PartHead:
    return PartHead(
        vault=vault,
        path=path,
        schema=V2_SCHEMA,
        agent="claude-code",
        session_id=session_id,
        part=2,
        first_turn_at=started,
        last_turn_at=last_turn_at if last_turn_at is not None else ended,
        first_exchange_id="e1",
        last_exchange_id="e9",
        exchange_started=started,
        exchange_ended=ended,
    )


def test_v2_exchange_range_containing_v1_range_covers_it() -> None:
    v1 = _v1()
    result = uncovered_v1_parts([v1, _v2()])
    assert result.uncovered == ()
    assert result.covered == (v1,)
    assert result.unreadable == ()


def test_equal_bounds_cover() -> None:
    v1 = _v1()
    result = uncovered_v1_parts([v1, _v2(started=v1.first_turn_at, ended=v1.last_turn_at)])
    assert result.covered == (v1,)


def test_v2_frontmatter_last_turn_at_is_ignored() -> None:
    # The v2 file's last turn is a subagent turn earlier than the v1 end, but an exchange meta ends later.
    v1 = _v1()
    v2 = _v2(last_turn_at="2026-11-07T09:30:00Z", ended="2026-11-07T10:05:00Z")
    assert uncovered_v1_parts([v1, v2]).covered == (v1,)


def test_v2_exchange_range_ending_early_does_not_cover_even_with_late_last_turn_at() -> None:
    v1 = _v1()
    v2 = _v2(ended="2026-11-07T09:59:59Z", last_turn_at="2026-11-07T11:00:00Z")
    assert uncovered_v1_parts([v1, v2]).uncovered == (v1,)


def test_mixed_session_later_v2_part_does_not_cover_earlier_v1() -> None:
    v1 = _v1()
    later = _v2(started="2026-11-08T00:00:00Z", ended="2026-11-08T01:00:00Z")
    assert uncovered_v1_parts([v1, later]).uncovered == (v1,)


def test_other_vault_or_other_session_v2_part_is_not_counted() -> None:
    v1 = _v1()
    other_vault = _v2(vault="bake")
    other_session = _v2(session_id="d353dbe2-0000-0000-0000-000000000000")
    other_agent = replace(_v2(), agent="codex")
    result = uncovered_v1_parts([v1, other_vault, other_session, other_agent])
    assert result.uncovered == (v1,)


def test_two_v2_parts_are_not_joined() -> None:
    v1 = _v1()
    head = _v2("a.md", started="2026-11-07T08:00:00Z", ended="2026-11-07T09:30:00Z")
    tail = _v2("b.md", started="2026-11-07T09:30:00Z", ended="2026-11-07T11:00:00Z")
    assert uncovered_v1_parts([v1, head, tail]).uncovered == (v1,)


def test_same_instant_with_and_without_milliseconds_is_equal() -> None:
    v1 = _v1(first="2026-11-07T09:00:00.000Z", last="2026-11-07T10:00:00.000Z")
    v2 = _v2(started="2026-11-07T09:00:00Z", ended="2026-11-07T10:00:00+00:00")
    assert uncovered_v1_parts([v1, v2]).covered == (v1,)


def test_times_compare_as_instants_not_strings() -> None:
    # 18:00+09:00 is 09:00Z, so it starts no later than the v1 part even though the string sorts later.
    v1 = _v1()
    v2 = _v2(started="2026-11-07T18:00:00+09:00")
    assert uncovered_v1_parts([v1, v2]).covered == (v1,)


def test_unreadable_v1_parts_come_back_separately() -> None:
    no_session = _v1("a.md", session_id=None)
    no_first = _v1("b.md", first=None)
    bad_last = _v1("c.md", last="yesterday")
    empty = _v1("d.md", first="")
    result = uncovered_v1_parts([no_session, no_first, bad_last, empty, _v2()])
    assert result.unreadable == (no_session, no_first, bad_last, empty)
    assert result.uncovered == ()
    assert result.covered == ()


def test_v2_part_with_unreadable_exchange_times_does_not_cover() -> None:
    v1 = _v1()
    assert uncovered_v1_parts([v1, _v2(started=None)]).uncovered == (v1,)
    assert uncovered_v1_parts([v1, _v2(ended="not a time")]).uncovered == (v1,)


def test_other_schemas_are_ignored() -> None:
    other = replace(_v1(), schema="vault-session/v3")
    result = uncovered_v1_parts([other])
    assert result == uncovered_v1_parts([])


def test_same_input_gives_same_result() -> None:
    parts = [_v1("a.md"), _v1("b.md", first="2026-11-07T07:00:00Z"), _v2(), _v1("c.md", last=None)]
    first = uncovered_v1_parts(parts)
    assert first == uncovered_v1_parts(list(parts))
    assert [p.path for p in first.uncovered] == ["b.md"]
    assert [p.path for p in first.covered] == ["a.md"]
    assert [p.path for p in first.unreadable] == ["c.md"]


def test_exchange_time_range_takes_earliest_started_and_latest_ended() -> None:
    body = [
        "## Title 2026-11-09 01:00 · 4ebb8ad7",
        "<!-- vg:exchange id=a scope=main started=2026-11-09T01:00:00.000Z ended=2026-11-09T02:00:00.000Z"
        " tools=Bash:1 errors=0 outcome=answered -->",
        "### user · 01:00 · 11111111",
        "<!-- vg:exchange id=b scope=subagent:x started=2026-11-09T00:30:00Z ended=2026-11-09T01:10:00Z -->",
        "<!-- vg:exchange id=c scope=main started=2026-11-09T01:05:00Z ended=2026-11-09T03:00:00Z -->",
        "some text with started=2026-11-01T00:00:00Z that is not a meta line",
    ]
    assert exchange_time_range(body) == ("2026-11-09T00:30:00Z", "2026-11-09T03:00:00Z")


def test_exchange_time_range_compares_instants_and_skips_bad_values() -> None:
    body = [
        "<!-- vg:exchange id=a scope=main started=2026-11-09T10:00:00%2B09:00 ended=garbage -->",
        "<!-- vg:exchange id=b scope=main started=2026-11-09T02:00:00Z ended=2026-11-09T02:30:00Z -->",
        "<!-- vg:exchange id=c scope=main -->",
    ]
    assert exchange_time_range(body) == ("2026-11-09T10:00:00+09:00", "2026-11-09T02:30:00Z")


def test_exchange_time_range_without_meta_times_is_none() -> None:
    assert exchange_time_range(["## heading", "<!-- vg:exchange id=a scope=main -->", "text"]) is None
    assert exchange_time_range([]) is None


def _session() -> SessionLine:
    return SessionLine(
        session_id=SESSION,
        agent="claude-code",
        agent_version=None,
        adapter="claude-code/1",
        project=None,
        cwd=None,
        git_branch=None,
        git_commit=None,
        parent_session_id=None,
        title=None,
        started_at=None,
        ended_at=None,
        source_paths=(),
        source_sha256="0",
    )


def _exchange(exchange_id: str, seq: int) -> ExchangeLine:
    return ExchangeLine(
        exchange_id=exchange_id,
        seq=seq,
        agent_scope="main",
        subagent_type=None,
        parent_tool_use_id=None,
        started_at=None,
        ended_at=None,
        closed=True,
        prompt_source=None,
        tools={},
        files_touched=(),
        commands=(),
        errors=0,
        outcome="answered",
    )


def _turn(turn_id: str, exchange_id: str) -> TurnLine:
    return TurnLine(
        turn_id=turn_id,
        parent_id=None,
        exchange_id=exchange_id,
        role="user",
        turn_kind="human",
        at=None,
        agent_id=None,
        sidechain=False,
        text="hi",
        actions=(),
    )


def test_exchange_summary_counts_exchanges_with_turns_and_takes_first_and_last_ids() -> None:
    lines: list[NormalizedLine] = [
        _session(),
        _exchange("e0", 0),  # no turns
        _exchange("e1", 1),
        _turn("t1", "e1"),
        _turn("t2", "e1"),
        _exchange("e2", 2),  # no turns
        _exchange("e3", 3),
        _turn("t3", "e3"),
        _exchange("e4", 4),  # no turns, last line
    ]
    assert exchange_summary(lines) == ExchangeSummary(count=2, first_exchange_id="e1", last_exchange_id="e3")


def test_exchange_summary_skips_exchanges_without_turns() -> None:
    lines: list[NormalizedLine] = [_session(), _exchange("e0", 0), _exchange("e1", 1), _turn("t", "missing")]
    assert exchange_summary(lines) == ExchangeSummary(count=0, first_exchange_id=None, last_exchange_id=None)


def test_exchange_summary_follows_exchange_line_order() -> None:
    # Turns may appear after a later exchange line; order comes from the exchange lines.
    lines: list[NormalizedLine] = [_exchange("a", 0), _exchange("b", 1), _turn("tb", "b"), _turn("ta", "a")]
    assert exchange_summary(lines) == ExchangeSummary(count=2, first_exchange_id="a", last_exchange_id="b")
