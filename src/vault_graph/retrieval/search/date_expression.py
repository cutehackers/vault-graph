"""Date range arguments and the fixed `--when` rules (spec 2026-11-16 longmemeval-session-memory D10, D13, D14, F5).

`resolve_date_expression` turns one date expression into an inclusive date range counted from `today`. It reads
only the expression the caller passes, never the query text, and it fails instead of guessing: a range nobody asked
for would silently drop results (D13). It calls no model, process, or network (D14, I2).

Fixed rules (weeks run Monday to Sunday, months are calendar months, "N months before" clamps to the month end):

- "N days ago": that one day. "a couple of days ago", "a few days ago": 4 to 2 days ago.
- "N weeks ago": the week that holds the day 7*N days ago.
- "N months ago": the calendar month N months before this month.
- "the <weekday> N weeks/months ago": the week that holds the day N weeks/months ago.
- "last <weekday>": the latest such day before today. "last week", "last month": the previous week or month.
- "in the past N days/weeks/months", "in the last …", "during the past month", "past week": N units ago to today.
- "in <month>", "<month>", "in <month> and <month>": the latest such month not after this month. With "and", the
  span from the earliest to the latest month.
- Explicit dates and months: "YYYY-MM-DD", "YYYY/MM/DD", "YYYY-MM", "<month> YYYY", "<month> D[, YYYY]",
  "D <month> [YYYY]". Without a year, the latest such day not after today.
- Korean: "지난주", "지난달", "N월에" (or "N월"), "N일 전".
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from vault_graph.errors import SearchError

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sept": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_WEEKDAYS = {
    "monday": 0,
    "mon": 0,
    "tuesday": 1,
    "tue": 1,
    "tues": 1,
    "wednesday": 2,
    "wed": 2,
    "thursday": 3,
    "thu": 3,
    "thurs": 3,
    "friday": 4,
    "fri": 4,
    "saturday": 5,
    "sat": 5,
    "sunday": 6,
    "sun": 6,
}
_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_MONTH = f"(?P<month>{_MONTH_NAMES})"
_WEEKDAY = "(?P<weekday>" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + ")"
_COUNT = r"(?P<count>\d+|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + ")"
_UNIT = r"(?P<unit>day|week|month)s?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
_YEAR = r"(?P<year>\d{4})"


class DateArgumentError(SearchError):
    """A date argument or `--when` expression is malformed or cannot be resolved (F5)."""


@dataclass(frozen=True, slots=True)
class DateRange:
    """Inclusive date range. A missing side means no limit on that side (D10)."""

    since: date | None
    until: date | None

    def __post_init__(self) -> None:
        if self.since is not None and self.until is not None and self.since > self.until:
            raise DateArgumentError(f"since {self.since.isoformat()} is after until {self.until.isoformat()}")


def parse_date_argument(value: str, *, name: str) -> date:
    """Parse one `YYYY-MM-DD` argument. `name` (`since`, `until`) goes into the error reason."""
    if not _ISO_DATE.fullmatch(value):
        raise DateArgumentError(f"{name} must be a YYYY-MM-DD date, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DateArgumentError(f"{name} is not a real date: {value!r}") from error


def date_range_from_arguments(since: str | None, until: str | None) -> DateRange | None:
    """Build the range from `since`/`until` arguments. Returns None when neither is given."""
    if since is None and until is None:
        return None
    return DateRange(
        since=None if since is None else parse_date_argument(since, name="since"),
        until=None if until is None else parse_date_argument(until, name="until"),
    )


def resolve_date_expression(text: str, today: date) -> DateRange:
    """Resolve one date expression to an inclusive range counted from `today` by the fixed rules above."""
    if isinstance(today, datetime) or not isinstance(today, date):
        raise TypeError("today must be a date")
    normalized = " ".join(text.strip().lower().split())
    for pattern, rule in _RULES:
        match = pattern.fullmatch(normalized)
        if match is None:
            continue
        try:
            resolved = rule(match.groupdict(), today)
        except ValueError as error:
            raise DateArgumentError(f"cannot resolve date expression {text!r}: {error}") from error
        if resolved is not None:
            return resolved
    raise DateArgumentError(f"cannot resolve date expression {text!r}")


def _count(value: str) -> int:
    count = _NUMBER_WORDS[value] if value in _NUMBER_WORDS else int(value)
    if count < 1:
        raise ValueError("the count must be at least 1")
    return count


def _months_before(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _month_range(year: int, month: int) -> DateRange:
    return DateRange(since=date(year, month, 1), until=date(year, month, calendar.monthrange(year, month)[1]))


def _week_range(day: date) -> DateRange:
    monday = day - timedelta(days=day.weekday())
    return DateRange(since=monday, until=monday + timedelta(days=6))


def _single_day(day: date) -> DateRange:
    return DateRange(since=day, until=day)


def _latest_month(month: int, today: date) -> DateRange:
    year = today.year if month <= today.month else today.year - 1
    return _month_range(year, month)


def _latest_day(month: int, day: int, today: date) -> DateRange:
    candidate = date(today.year, month, day) if _is_real_day(today.year, month, day) else None
    if candidate is None or candidate > today:
        if not _is_real_day(today.year - 1, month, day):
            raise ValueError("no such day")
        candidate = date(today.year - 1, month, day)
    return _single_day(candidate)


def _is_real_day(year: int, month: int, day: int) -> bool:
    return 1 <= day <= calendar.monthrange(year, month)[1]


def _units_before(today: date, count: int, unit: str) -> date:
    if unit == "day":
        return today - timedelta(days=count)
    if unit == "week":
        return today - timedelta(weeks=count)
    return _months_before(today, count)


def _ago(groups: dict[str, str], today: date) -> DateRange:
    count = _count(groups["count"])
    anchor = _units_before(today, count, groups["unit"])
    if groups["unit"] == "day":
        return _single_day(anchor)
    if groups["unit"] == "week":
        return _week_range(anchor)
    return _month_range(anchor.year, anchor.month)


def _weekday_ago(groups: dict[str, str], today: date) -> DateRange:
    return _week_range(_units_before(today, _count(groups["count"]), groups["unit"]))


def _few_days_ago(groups: dict[str, str], today: date) -> DateRange:
    return DateRange(since=today - timedelta(days=4), until=today - timedelta(days=2))


def _last_weekday(groups: dict[str, str], today: date) -> DateRange:
    back = (today.weekday() - _WEEKDAYS[groups["weekday"]]) % 7 or 7
    return _single_day(today - timedelta(days=back))


def _last_week(groups: dict[str, str], today: date) -> DateRange:
    return _week_range(today - timedelta(weeks=1))


def _last_month(groups: dict[str, str], today: date) -> DateRange:
    previous = _months_before(today, 1)
    return _month_range(previous.year, previous.month)


def _past(groups: dict[str, str], today: date) -> DateRange:
    count = _count(groups["count"]) if groups.get("count") else 1
    return DateRange(since=_units_before(today, count, groups["unit"]), until=today)


def _named_month(groups: dict[str, str], today: date) -> DateRange:
    month = _MONTHS[groups["month"]]
    if groups.get("year"):
        return _month_range(int(groups["year"]), month)
    return _latest_month(month, today)


def _two_months(groups: dict[str, str], today: date) -> DateRange:
    first = _latest_month(_MONTHS[groups["month"]], today)
    second = _latest_month(_MONTHS[groups["second"]], today)
    return DateRange(since=min(first.since, second.since), until=max(first.until, second.until))  # type: ignore[type-var]


def _named_day(groups: dict[str, str], today: date) -> DateRange:
    month = _MONTHS[groups["month"]]
    day = int(groups["day"])
    if groups.get("year"):
        return _single_day(date(int(groups["year"]), month, day))
    return _latest_day(month, day, today)


def _numeric_day(groups: dict[str, str], today: date) -> DateRange:
    return _single_day(date(int(groups["year"]), int(groups["num_month"]), int(groups["day"])))


def _numeric_month(groups: dict[str, str], today: date) -> DateRange:
    month = int(groups["num_month"])
    if not 1 <= month <= 12:
        raise ValueError("month must be 1 to 12")
    if groups.get("year"):
        return _month_range(int(groups["year"]), month)
    return _latest_month(month, today)


def _korean_days_ago(groups: dict[str, str], today: date) -> DateRange:
    return _single_day(today - timedelta(days=_count(groups["count"])))


_Rule = Callable[[dict[str, str], date], DateRange]

_IN = r"(?:(?:in|on|during) )?"
_RULES: tuple[tuple[re.Pattern[str], _Rule], ...] = tuple(
    (re.compile(pattern), rule)
    for pattern, rule in (
        (r"(?:a couple of|a few|couple of|few) days ago", _few_days_ago),
        (rf"(?:on )?(?:the )?{_WEEKDAY} {_COUNT} (?P<unit>week|month)s? ago", _weekday_ago),
        (rf"{_COUNT} {_UNIT} ago", _ago),
        (rf"(?:on )?last {_WEEKDAY}", _last_weekday),
        (r"last week", _last_week),
        (r"last month", _last_month),
        (rf"(?:(?:in|during|over|within) )?the (?:past|last) (?:{_COUNT} )?{_UNIT}", _past),
        (rf"(?:past|last) {_COUNT} {_UNIT}", _past),
        (rf"past {_UNIT}", _past),
        (rf"{_IN}{_MONTH} and (?P<second>{_MONTH_NAMES})", _two_months),
        (rf"{_IN}{_MONTH}(?:,? {_YEAR})?", _named_month),
        (rf"{_IN}{_MONTH} {_DAY}(?:,? {_YEAR})?", _named_day),
        (rf"{_IN}(?:the )?{_DAY} (?:of )?{_MONTH}(?:,? {_YEAR})?", _named_day),
        (rf"{_IN}{_YEAR}[-/](?P<num_month>\d{{1,2}})[-/]{_DAY}", _numeric_day),
        (rf"{_IN}{_YEAR}-(?P<num_month>\d{{1,2}})", _numeric_month),
        (r"지난 ?주", _last_week),
        (r"지난 ?달", _last_month),
        (r"(?P<num_month>\d{1,2}) ?월(?: ?에)?", _numeric_month),
        (r"(?P<count>\d+) ?일 ?전", _korean_days_ago),
    )
)
