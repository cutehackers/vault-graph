from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.test_context_pack_contract import make_pack
from vault_graph.context import ContextPack
from vault_graph.errors import ContextPackError
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache


def fixed_clock() -> datetime:
    return datetime(2026, 6, 17, 1, 2, 3, tzinfo=UTC)


def pack_with_id(pack_id: str) -> ContextPack:
    return replace(make_pack(generated_at="2026-06-12T00:00:00+00:00"), pack_id=pack_id)


def test_cache_put_and_get_returns_exact_rendered_json() -> None:
    cache = ContextPackResourceCache(max_entries=2, clock=fixed_clock)
    rendered_json = '{"pack_id":"pack-1"}\n'

    cached = cache.put(pack_with_id("pack-1"), rendered_json=rendered_json)

    assert cached.pack_id == "pack-1"
    assert cached.pack_json == rendered_json
    assert cached.generated_at == "2026-06-12T00:00:00+00:00"
    assert cached.requested_scope_key == "main:wiki,docs:cross=False"
    assert cached.actual_scope_keys == ("main:wiki,docs:local",)
    assert cached.cached_at == "2026-06-17T01:02:03+00:00"
    assert cache.get("pack-1") == cached


def test_cache_get_moves_entry_to_most_recently_used() -> None:
    cache = ContextPackResourceCache(max_entries=2, clock=fixed_clock)
    cache.put(pack_with_id("pack-1"), rendered_json="one")
    cache.put(pack_with_id("pack-2"), rendered_json="two")

    assert cache.get("pack-1") is not None
    cache.put(pack_with_id("pack-3"), rendered_json="three")

    assert cache.get("pack-2") is None
    assert cache.get("pack-1") is not None
    assert cache.get("pack-3") is not None


def test_cache_evicts_least_recently_used_entry() -> None:
    cache = ContextPackResourceCache(max_entries=1, clock=fixed_clock)

    cache.put(pack_with_id("pack-1"), rendered_json="one")
    cache.put(pack_with_id("pack-2"), rendered_json="two")

    assert len(cache) == 1
    assert cache.get("pack-1") is None
    assert cache.get("pack-2") is not None


def test_cache_rejects_invalid_max_entries() -> None:
    with pytest.raises(ContextPackError, match="max_entries must be positive"):
        ContextPackResourceCache(max_entries=0)


def test_cache_rejects_empty_pack_id() -> None:
    cache = ContextPackResourceCache(clock=fixed_clock)

    with pytest.raises(ContextPackError, match="pack_id is required"):
        cache.put(pack_with_id(""), rendered_json="{}")


def test_cache_does_not_create_files(tmp_path: Path) -> None:
    cache = ContextPackResourceCache(clock=fixed_clock)

    cache.put(pack_with_id("pack-1"), rendered_json="{}")

    assert list(tmp_path.iterdir()) == []
