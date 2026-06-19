from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.test_result_explanation import make_record
from vault_graph.errors import ResultExplanationError
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


class Clock:
    def __init__(self) -> None:
        self._value = datetime(2026, 6, 19, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._value
        self._value += timedelta(seconds=1)
        return value


def test_result_explanation_cache_stores_and_returns_records() -> None:
    cache = ResultExplanationCache(clock=Clock())
    record = make_record("result-1")

    cached = cache.put(record)

    assert cached.record == record
    assert cached.cached_at == "2026-06-19T00:00:00+00:00"
    retrieved = cache.get("result-1")
    assert retrieved is not None
    assert retrieved == cached
    assert len(cache) == 1


def test_result_explanation_cache_evicts_oldest_record() -> None:
    cache = ResultExplanationCache(max_entries=2, clock=Clock())

    cache.put(make_record("result-1"))
    cache.put(make_record("result-2"))
    cache.put(make_record("result-3"))

    assert cache.get("result-1") is None
    assert cache.get("result-2") is not None
    assert cache.get("result-3") is not None


def test_result_explanation_cache_reput_moves_record_to_newest() -> None:
    cache = ResultExplanationCache(max_entries=2, clock=Clock())

    cache.put(make_record("result-1"))
    cache.put(make_record("result-2"))
    cache.put(make_record("result-1"))
    cache.put(make_record("result-3"))

    assert cache.get("result-1") is not None
    assert cache.get("result-2") is None
    assert cache.get("result-3") is not None


def test_result_explanation_cache_put_many_is_bounded() -> None:
    cache = ResultExplanationCache(max_entries=2, clock=Clock())

    cached = cache.put_many((make_record("result-1"), make_record("result-2"), make_record("result-3")))

    assert tuple(item.record.result_id for item in cached) == ("result-1", "result-2", "result-3")
    assert cache.get("result-1") is None
    assert cache.get("result-2") is not None
    assert cache.get("result-3") is not None
    assert cache.put_many(()) == ()


def test_result_explanation_cache_rejects_non_positive_max_entries() -> None:
    with pytest.raises(ResultExplanationError, match="max_entries must be positive"):
        ResultExplanationCache(max_entries=0)
