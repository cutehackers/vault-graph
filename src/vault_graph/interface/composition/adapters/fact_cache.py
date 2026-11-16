"""Cache of extracted facts by exchange content (spec 2026-11-16 D20, F8, F9).

The key is (extractor, model, schema version, sha256 of the exchange text). An exchange that comes back in a new
part with the same text is not extracted again, and a job whose attachment could not be written is written later
from the cache without calling the extractor. An entry with no facts records "no facts" for that exchange.

Entries live in `<cache dir>/<key[:2]>/<key>.json`, `{"schema": "vault-graph-facts-cache/1", "extractor", "model",
"schema_version", "exchange_sha256", "facts": [{"text", "date"}]}`. The default cache dir is
`<graph-home>/facts/cache`. LongMemEval passes one folder for all its Graph Homes. Exchange ids are not cached:
the same text may carry another id in another part.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

FACT_SCHEMA_VERSION = 1
"""Version of the fact schema and prompt. Raising it makes every cached entry a miss."""

_CACHE_FORMAT = "vault-graph-facts-cache/1"


@dataclass(frozen=True)
class CachedFact:
    text: str
    date: str


def fact_cache_dir(graph_home: Path) -> Path:
    return graph_home / "facts" / "cache"


def exchange_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FactCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, extractor: str, model: str, content_hash: str) -> list[CachedFact] | None:
        """The cached facts, `[]` for "no facts", or None when there is no usable entry."""
        path = self._path(extractor, model, content_hash)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema") != _CACHE_FORMAT:
            return None
        if (payload.get("extractor"), payload.get("model"), payload.get("schema_version")) != (
            extractor,
            model,
            FACT_SCHEMA_VERSION,
        ) or payload.get("exchange_sha256") != content_hash:
            return None
        facts = payload.get("facts")
        if not isinstance(facts, list):
            return None
        cached: list[CachedFact] = []
        for item in facts:
            if not isinstance(item, dict):
                return None
            if not isinstance(item.get("text"), str) or not isinstance(item.get("date"), str):
                return None
            cached.append(CachedFact(text=item["text"], date=item["date"]))
        return cached

    def put(self, extractor: str, model: str, content_hash: str, facts: list[CachedFact]) -> None:
        path = self._path(extractor, model, content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": _CACHE_FORMAT,
            "extractor": extractor,
            "model": model,
            "schema_version": FACT_SCHEMA_VERSION,
            "exchange_sha256": content_hash,
            "facts": [{"text": fact.text, "date": fact.date} for fact in facts],
        }
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, prefix=".entry-", suffix=".tmp", delete=False
            ) as stream:
                temporary = stream.name
                json.dump(payload, stream, ensure_ascii=False)
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def _path(self, extractor: str, model: str, content_hash: str) -> Path:
        key = hashlib.sha256(
            "\0".join((extractor, model, str(FACT_SCHEMA_VERSION), content_hash)).encode("utf-8")
        ).hexdigest()
        return self.root / key[:2] / f"{key}.json"
