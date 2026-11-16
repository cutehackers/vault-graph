"""Port for session fact extractors (spec 2026-11-16 §4 B.2, D17, D18).

The fact worker hands the exchanges it has no cached result for to one `FactExtractor`. The Claude CLI adapter
(`claude_fact_extractor.py`) and the `llama-server` adapter (`llama_fact_extractor.py`) implement it. Only
`fact_extractor_selection.select_fact_extractor` builds one. Search, indexing and recall never import this
port or its adapters (I2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from vault_graph.errors import VaultGraphError


@dataclass(frozen=True)
class FactExchange:
    """One exchange of a captured session, as the extractor sees it."""

    exchange_id: str
    date: str
    """`YYYY-MM-DD` of the exchange start."""
    text: str


@dataclass(frozen=True)
class ExtractedFact:
    """One fact: a sentence in the session's language, its date, and the exchange it came from."""

    text: str
    date: str
    exchange_id: str


class FactExtractorUnavailable(VaultGraphError):
    """The extractor cannot run now: missing command, not logged in, usage limit, timeout, no answer (F7)."""


class FactOutputInvalid(VaultGraphError):
    """The extractor answered, but the answer does not match the fact schema (F8)."""


@runtime_checkable
class FactExtractor(Protocol):
    extractor: str
    """`claude` or `llama-server`. Part of the cache key (D20)."""
    model: str
    """Model name or file. Part of the cache key (D20)."""

    def extract(self, exchanges: Sequence[FactExchange]) -> list[ExtractedFact]:
        """Return the facts of `exchanges`.

        Raises `FactExtractorUnavailable` when the extractor cannot run and `FactOutputInvalid` when its
        answer does not match the schema.
        """
        ...
