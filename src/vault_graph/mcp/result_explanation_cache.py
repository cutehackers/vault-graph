from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.errors import ResultExplanationError
from vault_graph.memory.result_explanation import CachedExplanationView, ExplanationRecord


@dataclass(frozen=True)
class CachedExplanation(CachedExplanationView):
    record: ExplanationRecord
    cached_at: str


class ResultExplanationCache:
    def __init__(
        self,
        *,
        max_entries: int = 256,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_entries <= 0:
            raise ResultExplanationError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock or (lambda: datetime.now(UTC))
        self._entries: OrderedDict[str, CachedExplanation] = OrderedDict()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def put(self, record: ExplanationRecord) -> CachedExplanation:
        cached = CachedExplanation(record=record, cached_at=_utc_isoformat(self._clock()))
        self._entries[record.result_id] = cached
        self._entries.move_to_end(record.result_id)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return cached

    def put_many(self, records: tuple[ExplanationRecord, ...]) -> tuple[CachedExplanation, ...]:
        if not records:
            return ()
        return tuple(self.put(record) for record in records)

    def get(self, result_id: str) -> CachedExplanation | None:
        return self._entries.get(result_id)

    def __len__(self) -> int:
        return len(self._entries)


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
