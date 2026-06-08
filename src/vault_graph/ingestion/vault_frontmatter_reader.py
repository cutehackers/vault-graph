from __future__ import annotations

import hashlib
from dataclasses import dataclass
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
    return FrontmatterProjection(data=dict(data), body=body, frontmatter_hash=digest)
