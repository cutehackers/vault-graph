from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import yaml


@dataclass(frozen=True)
class FrontmatterProjection:
    data: dict[str, Any]
    body: str
    frontmatter_hash: str


def read_frontmatter(text: str) -> FrontmatterProjection:
    empty_hash = hashlib.sha256(b"").hexdigest()
    if not text.startswith("---\n"):
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=empty_hash)

    closing = text.find("\n---\n", 4)
    if closing == -1:
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=empty_hash)

    raw_frontmatter = text[4:closing]
    parsed = yaml.safe_load(raw_frontmatter) or {}
    data = parsed if isinstance(parsed, dict) else {}
    body = text[closing + len("\n---\n") :]
    digest = hashlib.sha256(raw_frontmatter.encode("utf-8")).hexdigest()
    return FrontmatterProjection(data=_json_safe_mapping(data), body=body, frontmatter_hash=digest)


def _json_safe_mapping(values: dict[object, object]) -> dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in values.items()}


def _json_safe_value(value: object) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value
