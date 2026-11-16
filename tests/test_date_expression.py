"""Date arguments and the fixed `--when` rules (spec 2026-11-16 longmemeval-session-memory D10, D13, F5, A8, A10)."""

import socket
import subprocess
from datetime import date

import pytest

from vault_graph.errors import SearchError
from vault_graph.retrieval.search.date_expression import (
    DateArgumentError,
    DateRange,
    date_range_from_arguments,
    parse_date_argument,
    resolve_date_expression,
)

# Monday 2023-05-29 is not used as today. Today is a Wednesday so week rules are visible.
TODAY = date(2023, 5, 31)


def _range(since: str, until: str) -> DateRange:
    return DateRange(since=date.fromisoformat(since), until=date.fromisoformat(until))


ENGLISH_CASES = (
    # 1. "N days/weeks/months ago"
    ("10 days ago", "2023-05-21", "2023-05-21"),
    ("ten days ago", "2023-05-21", "2023-05-21"),
    ("a day ago", "2023-05-30", "2023-05-30"),
    ("a couple of days ago", "2023-05-27", "2023-05-29"),
    ("a few days ago", "2023-05-27", "2023-05-29"),
    ("two weeks ago", "2023-05-15", "2023-05-21"),
    ("1 week ago", "2023-05-22", "2023-05-28"),
    ("3 months ago", "2023-02-01", "2023-02-28"),
    ("a month ago", "2023-04-01", "2023-04-30"),
    ("the Wednesday two months ago", "2023-03-27", "2023-04-02"),
    # 2. "last <weekday>", "last week/month"
    ("last Saturday", "2023-05-27", "2023-05-27"),
    ("last wednesday", "2023-05-24", "2023-05-24"),
    ("last week", "2023-05-22", "2023-05-28"),
    ("last month", "2023-04-01", "2023-04-30"),
    # 3. "in the past N months", "during the past month"
    ("in the past 2 months", "2023-03-31", "2023-05-31"),
    ("in the past three months", "2023-02-28", "2023-05-31"),
    ("during the past month", "2023-04-30", "2023-05-31"),
    ("in the last 10 days", "2023-05-21", "2023-05-31"),
    ("past week", "2023-05-24", "2023-05-31"),
    # 4. "in <month>", "in <month> and <month>"
    ("in May", "2023-05-01", "2023-05-31"),
    ("in March", "2023-03-01", "2023-03-31"),
    ("in June", "2022-06-01", "2022-06-30"),
    ("in March and April", "2023-03-01", "2023-04-30"),
    ("in April and February", "2023-02-01", "2023-04-30"),
    ("Feb", "2023-02-01", "2023-02-28"),
    # 5. explicit month and day, explicit dates and months
    ("May 20th", "2023-05-20", "2023-05-20"),
    ("on March 3", "2023-03-03", "2023-03-03"),
    ("20 May", "2023-05-20", "2023-05-20"),
    ("December 24", "2022-12-24", "2022-12-24"),
    ("May 20, 2021", "2021-05-20", "2021-05-20"),
    ("2023-05-20", "2023-05-20", "2023-05-20"),
    ("2023/05/20", "2023-05-20", "2023-05-20"),
    ("2022-11", "2022-11-01", "2022-11-30"),
    ("May 2021", "2021-05-01", "2021-05-31"),
    ("in February 2024", "2024-02-01", "2024-02-29"),
)

KOREAN_CASES = (
    ("지난주", "2023-05-22", "2023-05-28"),
    ("지난 주", "2023-05-22", "2023-05-28"),
    ("지난달", "2023-04-01", "2023-04-30"),
    ("지난 달", "2023-04-01", "2023-04-30"),
    ("5월에", "2023-05-01", "2023-05-31"),
    ("12월에", "2022-12-01", "2022-12-31"),
    ("3월", "2023-03-01", "2023-03-31"),
    ("3일 전", "2023-05-28", "2023-05-28"),
    ("10일전", "2023-05-21", "2023-05-21"),
)


@pytest.mark.parametrize(("text", "since", "until"), ENGLISH_CASES + KOREAN_CASES)
def test_expression_resolves_to_fixed_inclusive_range(text: str, since: str, until: str) -> None:
    assert resolve_date_expression(text, TODAY) == _range(since, until)


def test_case_and_surrounding_space_do_not_matter() -> None:
    assert resolve_date_expression("  LAST Week  ", TODAY) == resolve_date_expression("last week", TODAY)


def test_month_rules_clamp_short_months() -> None:
    assert resolve_date_expression("in the past month", date(2023, 3, 31)) == _range("2023-02-28", "2023-03-31")
    assert resolve_date_expression("last month", date(2024, 1, 15)) == _range("2023-12-01", "2023-12-31")


@pytest.mark.parametrize(
    "text",
    (
        "",
        "   ",
        "recently",
        "what did I do last week?",
        "How many days ago did I buy the plant",
        "지난주에 뭐 했지",
        "0 days ago",
        "February 30",
        "2023-02-30",
        "13월에",
        "in Smarch",
    ),
)
def test_unresolvable_expression_raises_and_does_not_read_query_text(text: str) -> None:
    with pytest.raises(DateArgumentError):
        resolve_date_expression(text, TODAY)


def test_date_argument_error_is_search_input_error() -> None:
    assert issubclass(DateArgumentError, SearchError)


def test_today_must_be_a_date_not_a_datetime() -> None:
    from datetime import datetime

    with pytest.raises(TypeError):
        resolve_date_expression("last week", datetime(2023, 5, 31, 12, 0))


def test_parse_date_argument_accepts_only_yyyy_mm_dd() -> None:
    assert parse_date_argument("2023-05-20", name="since") == date(2023, 5, 20)
    for bad in ("2023-5-20", "2023/05/20", "20230520", "2023-02-30", "", "last week", "2023-05-20T00:00"):
        with pytest.raises(DateArgumentError, match="since"):
            parse_date_argument(bad, name="since")


def test_date_range_from_arguments_allows_one_side() -> None:
    assert date_range_from_arguments(None, None) is None
    assert date_range_from_arguments("2023-05-01", None) == DateRange(since=date(2023, 5, 1), until=None)
    assert date_range_from_arguments(None, "2023-05-01") == DateRange(since=None, until=date(2023, 5, 1))
    assert date_range_from_arguments("2023-05-01", "2023-05-01") == _range("2023-05-01", "2023-05-01")


def test_date_range_from_arguments_rejects_since_after_until() -> None:
    with pytest.raises(DateArgumentError, match="since"):
        date_range_from_arguments("2023-05-02", "2023-05-01")


def test_date_range_rejects_since_after_until() -> None:
    with pytest.raises(DateArgumentError):
        DateRange(since=date(2023, 5, 2), until=date(2023, 5, 1))


def test_resolving_starts_no_subprocess_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("date expression resolution must not start a process or open a connection")

    monkeypatch.setattr(subprocess, "Popen", _blocked)
    monkeypatch.setattr(subprocess, "run", _blocked)
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)
    for text, since, until in ENGLISH_CASES + KOREAN_CASES:
        assert resolve_date_expression(text, TODAY) == _range(since, until)
    with pytest.raises(DateArgumentError):
        resolve_date_expression("sometime around the holidays", TODAY)
