from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from vault_graph.context.context_pack import ContextPack
from vault_graph.errors import ContextPackError


@dataclass(frozen=True)
class CachedContextPack:
    pack_id: str
    pack_json: str
    generated_at: str
    requested_scope_key: str
    actual_scope_keys: tuple[str, ...]
    cached_at: str


class ContextPackResourceCache:
    def __init__(
        self,
        *,
        max_entries: int = 32,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if max_entries <= 0:
            raise ContextPackError("max_entries must be positive")
        self._max_entries = max_entries
        self._clock = clock or (lambda: datetime.now(UTC))
        self._entries: OrderedDict[str, CachedContextPack] = OrderedDict()

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def put(self, pack: ContextPack, *, rendered_json: str) -> CachedContextPack:
        if not pack.pack_id:
            raise ContextPackError("pack_id is required")
        cached = CachedContextPack(
            pack_id=pack.pack_id,
            pack_json=rendered_json,
            generated_at=pack.generated_at,
            requested_scope_key=_requested_scope_key(pack),
            actual_scope_keys=tuple(scope.scope_key for scope in pack.scope.actual_scopes),
            cached_at=_utc_isoformat(self._clock()),
        )
        self._entries[pack.pack_id] = cached
        self._entries.move_to_end(pack.pack_id)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return cached

    def get(self, pack_id: str) -> CachedContextPack | None:
        cached = self._entries.get(pack_id)
        if cached is None:
            return None
        self._entries.move_to_end(pack_id)
        return cached

    def __len__(self) -> int:
        return len(self._entries)


def _requested_scope_key(pack: ContextPack) -> str:
    requested = pack.scope.requested
    return (
        f"{','.join(requested.vault_ids)}:"
        f"{','.join(requested.content_scopes)}:"
        f"cross={requested.include_cross_vault}"
    )


def _utc_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()
