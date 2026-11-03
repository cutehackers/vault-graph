from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import yaml

from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter


@dataclass(frozen=True)
class FrontmatterProjection:
    data: dict[str, Any]
    body: str
    frontmatter_hash: str
    # Set when YAML rejected the block and the Vault line rules were used instead.
    yaml_error: str | None = None


def read_frontmatter(text: str) -> FrontmatterProjection:
    block = split_frontmatter(text)
    if block is None:
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=hashlib.sha256(b"").hexdigest())

    raw_frontmatter, body = block
    yaml_error = None
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        # Vault accepts frontmatter that strict YAML rejects, so read it the way Vault does.
        parsed = parse_vault_frontmatter(raw_frontmatter)
        yaml_error = _short_yaml_error(exc)
    data = parsed if isinstance(parsed, dict) else {}
    digest = hashlib.sha256(raw_frontmatter.encode("utf-8")).hexdigest()
    return FrontmatterProjection(
        data=_json_safe_mapping(data),
        body=body,
        frontmatter_hash=digest,
        yaml_error=yaml_error,
    )


def _short_yaml_error(exc: yaml.YAMLError) -> str:
    if isinstance(exc, yaml.MarkedYAMLError) and exc.problem:
        mark = exc.problem_mark
        # Frontmatter line numbers count the opening "---" as line 1.
        return f"line {mark.line + 2}: {exc.problem}" if mark is not None else exc.problem
    return " ".join(str(exc).split()) or type(exc).__name__


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
