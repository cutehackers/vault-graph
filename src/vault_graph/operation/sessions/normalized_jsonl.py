"""Encode normalized session lines as ``vg-session-jsonl/1`` text (spec 2026-11-05 §4.2.2).

Same lines give the same bytes: keys follow the dataclass field order after ``schema`` and ``kind``,
mapping keys are sorted, non-ASCII text stays as is, and every line ends with ``\\n``.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Mapping

from vault_graph.operation.sessions.models import NORMALIZED_SESSION_SCHEMA, NormalizedLine

type _Json = None | bool | int | str | list[_Json] | dict[str, _Json]


def encode_line(line: NormalizedLine) -> str:
    """Return one JSON line without the trailing newline."""
    payload: dict[str, _Json] = {"schema": NORMALIZED_SESSION_SCHEMA, "kind": line.kind}
    payload.update(_fields(line))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def encode_session(lines: Iterable[NormalizedLine]) -> str:
    """Return the whole normalized file text, one line per item, each ending with a newline."""
    return "".join(encode_line(line) + "\n" for line in lines)


def _fields(value: object) -> dict[str, _Json]:
    return {item.name: _plain(getattr(value, item.name)) for item in dataclasses.fields(value)}  # type: ignore[arg-type]


def _plain(value: object) -> _Json:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _plain(value[key]) for key in sorted(value)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _fields(value)
    raise TypeError(f"not a normalized session value: {type(value).__name__}")
