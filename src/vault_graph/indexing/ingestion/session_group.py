"""Rules that need every file of one session together (spec 2026-11-05 §4.2.13).

A session group is the files whose frontmatter has the same (`agent`, `session_id`). After chunking and
before the metadata apply, `reprocess_session_groups` runs two rules on each group:

1. The same v2 exchange id in two files stays in one file: the whole (not continued) copy first,
   then the lower part number, then the path (§4.2.6-9, `drop_duplicate_exchanges`).
2. A v1 exchange whose time range overlaps a v2 exchange's `started`~`ended` in the same scope (main
   agent, or the same subagent) is left out (§4.2.7 last bullet). A v2 subagent exchange never removes a
   v1 main exchange: the v2 file does not hold that main exchange, so removing it would lose the text.
   A continued v2 copy (`continued=1`) holds only the turns after the cut, so it removes a v1 exchange
   only when the turns it holds cover that whole v1 exchange.
   Only index rows change. Vault files are never touched.

Both only remove chunks, and both are pure functions of the group's files, so a run that reads the
whole group gives the same chunks as a full run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime

from vault_graph.indexing.ingestion.document_models import ExtractedDocument
from vault_graph.indexing.ingestion.document_snapshots import NormalizedDocument
from vault_graph.indexing.ingestion.session_exchange_v1_chunker import (
    exchange_time_ranges as v1_exchange_time_ranges,
)
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import (
    drop_duplicate_exchanges,
)
from vault_graph.indexing.ingestion.session_exchange_v2_chunker import (
    exchange_time_ranges as v2_exchange_time_ranges,
)

SESSION_SCHEMA_PREFIX = "vault-session/"
SESSION_SCHEMA_V1 = "vault-session/v1"
SESSION_SCHEMA_V2 = "vault-session/v2"
# Part of the metadata index code: a store written before session groups reads every file once, so
# each session file gets its stored group key. v2: v1 exchanges that only touch a v2 range are kept, so
# a store written by v1 reads every file again to bring them back. v3: the overlap rule compares
# exchanges of the same scope only, so a store written by v2 reads every file again to bring back the
# v1 main exchanges that overlapped a v2 subagent exchange or a continued v2 copy.
SESSION_GROUP_VERSION = "session-group-v3"

Key = tuple[str, str]
# (first time, last time, scope, whole). Scope is `main` or `subagent:<id>`. `whole` is False for a
# continued v2 copy, whose times are those of the turns the file holds.
TimeRange = tuple[str, str, str, bool]
ExchangeRanges = Mapping[str, TimeRange | None]


def session_group_key(frontmatter: Mapping[str, object]) -> str | None:
    """`<agent>:<session_id>` of a session file, None for any other file or a session file missing either."""
    schema = frontmatter.get("schema")
    if not isinstance(schema, str) or not schema.startswith(SESSION_SCHEMA_PREFIX):
        return None
    agent = _text(frontmatter.get("agent"))
    session_id = _text(frontmatter.get("session_id"))
    if not agent or not session_id:
        return None
    return f"{agent}:{session_id}"


def exchange_ranges(document: ExtractedDocument) -> dict[str, TimeRange | None]:
    """Time range and scope of each exchange by chunk `parent_key`. Empty for a file that is not a v1 or v2 session."""
    schema = document.frontmatter.data.get("schema")
    if schema == SESSION_SCHEMA_V1:
        return dict(v1_exchange_time_ranges(document))
    if schema == SESSION_SCHEMA_V2:
        return v2_exchange_time_ranges(document)
    return {}


def reprocess_session_groups(
    documents: Sequence[NormalizedDocument],
    ranges: Mapping[Key, ExchangeRanges],
    *,
    incomplete_groups: Mapping[Key, Sequence[str]] | None = None,
) -> tuple[tuple[NormalizedDocument, ...], tuple[str, ...]]:
    """Apply the group rules to `documents`. Returns them in the same order, plus warning lines.

    `ranges` holds `exchange_ranges` of each session document by (vault_id, path). A session document
    without an entry makes its group incomplete. `incomplete_groups` names, by (vault_id, group key),
    the paths of group members that could not be read. An incomplete group keeps every v1 exchange
    (§6: no record is lost) and gets one warning line.
    """
    incomplete: dict[Key, list[str]] = {key: list(paths) for key, paths in (incomplete_groups or {}).items()}
    groups: dict[Key, list[NormalizedDocument]] = {}
    for item in documents:
        group = session_group_key(item.document.frontmatter)
        if group is None:
            continue
        group_id = (item.document.vault_id, group)
        groups.setdefault(group_id, []).append(item)
        if (item.document.vault_id, item.document.path) not in ranges:
            incomplete.setdefault(group_id, []).append(item.document.path)
    replaced: dict[Key, NormalizedDocument] = {}
    warnings: list[str] = []
    for group_id in sorted(groups):
        members, group_warnings = _reprocess_group(
            groups[group_id], ranges, group=group_id[1], unreadable=incomplete.get(group_id)
        )
        warnings.extend(group_warnings)
        for item in members:
            replaced[(item.document.vault_id, item.document.path)] = item
    result = tuple(replaced.get((item.document.vault_id, item.document.path), item) for item in documents)
    return result, tuple(warnings)


def _reprocess_group(
    members: list[NormalizedDocument],
    ranges: Mapping[Key, ExchangeRanges],
    *,
    group: str,
    unreadable: Sequence[str] | None,
) -> tuple[tuple[NormalizedDocument, ...], list[str]]:
    deduplicated, duplicate_warnings = drop_duplicate_exchanges(members)
    warnings = list(duplicate_warnings)
    v1 = [item for item in deduplicated if _schema(item) == SESSION_SCHEMA_V1]
    v2 = [item for item in deduplicated if _schema(item) == SESSION_SCHEMA_V2]
    if not v1 or not v2:
        return deduplicated, warnings
    if unreadable:
        warnings.append(
            f"session_group_incomplete: session {group}: could not read {', '.join(sorted(set(unreadable)))}; "
            "kept every v1 exchange"
        )
        return deduplicated, warnings
    v2_ranges: dict[str, list[tuple[datetime, datetime, bool]]] = {}
    for item in v2:
        for parent_key, time_range in sorted(ranges[_key(item)].items()):
            parsed = _parse_range(time_range)
            if parsed is None:
                warnings.append(
                    f"session_overlap_time_missing: session {group}: exchange {parent_key} in "
                    f"{item.document.path} has no started/ended time; kept every v1 exchange"
                )
                return deduplicated, warnings
            v2_ranges.setdefault(parsed[2], []).append((parsed[0], parsed[1], parsed[3]))
    kept: list[NormalizedDocument] = []
    for item in deduplicated:
        if _schema(item) != SESSION_SCHEMA_V1:
            kept.append(item)
            continue
        overlapped = {
            parent_key
            for parent_key, time_range in ranges[_key(item)].items()
            if (parsed := _parse_range(time_range)) is not None and _overlaps(parsed[:2], v2_ranges.get(parsed[2], []))
        }
        if not overlapped:
            kept.append(item)
            continue
        chunks = tuple(chunk for chunk in item.chunks if chunk.parent_key not in overlapped)
        kept.append(replace(item, chunks=chunks) if len(chunks) != len(item.chunks) else item)
    return tuple(kept), warnings


def _overlaps(time_range: tuple[datetime, datetime], others: list[tuple[datetime, datetime, bool]]) -> bool:
    """True when the ranges share time, or start at the same moment (the same exchange).

    A continued copy (`whole` False) counts only when its turns cover the whole range.

    Ranges that only touch at one end do not overlap. A continued v1 part opens with the last turn of the
    previous exchange, so its first v1 exchange touches the last v2 range without being in any v2 file.
    """
    start, end = time_range
    return any(
        ((start < other_end and other_start < end) or start == other_start)
        if whole
        else (other_start <= start and end <= other_end)
        for other_start, other_end, whole in others
    )


def _parse_range(time_range: TimeRange | None) -> tuple[datetime, datetime, str, bool] | None:
    if time_range is None:
        return None
    start, end = (_parse_time(value) for value in time_range[:2])
    if start is None or end is None:
        return None
    scope, whole = time_range[2], time_range[3]
    return (start, end, scope, whole) if start <= end else (end, start, scope, whole)


def _parse_time(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    # A time without a zone cannot be compared with zoned ones. Session files write UTC.
    return parsed if parsed.tzinfo is not None else None


def _schema(item: NormalizedDocument) -> object:
    return item.document.frontmatter.get("schema")


def _key(item: NormalizedDocument) -> Key:
    return (item.document.vault_id, item.document.path)


def _text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return str(value).strip()
