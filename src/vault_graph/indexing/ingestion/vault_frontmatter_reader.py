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
    # Set when YAML rejected the block and the Vault line rules were used instead.
    yaml_error: str | None = None


def read_frontmatter(text: str) -> FrontmatterProjection:
    empty_hash = hashlib.sha256(b"").hexdigest()
    if not text.startswith("---\n"):
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=empty_hash)

    closing = text.find("\n---\n", 4)
    if closing == -1:
        return FrontmatterProjection(data={}, body=text, frontmatter_hash=empty_hash)

    raw_frontmatter = text[4:closing]
    yaml_error = None
    try:
        parsed = yaml.safe_load(raw_frontmatter) or {}
    except yaml.YAMLError as exc:
        # Vault accepts frontmatter that strict YAML rejects, so read it the way Vault does.
        parsed = _vault_line_rules(raw_frontmatter)
        yaml_error = _short_yaml_error(exc)
    data = parsed if isinstance(parsed, dict) else {}
    body = text[closing + len("\n---\n") :]
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


def _vault_line_rules(raw_frontmatter: str) -> dict[str, Any]:
    """Parse frontmatter with Vault ``tools/wiki/lib/frontmatter.py`` ``parse_page`` rules.

    The same rules live in ``operation/memory/memory_drafts.parse_frontmatter``. Indexing may not import
    operation code, so the small rule set is repeated here.
    """
    lines = raw_frontmatter.splitlines()
    root: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.startswith(" ") or ":" not in line:
            index += 1
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if value == "":
            root[key], index = _block_value(lines, index + 1)
            continue
        root[key] = _scalar(value)
        index += 1
    return root


def _block_value(lines: list[str], start: int) -> tuple[Any, int]:
    mapping: dict[str, Any] = {}
    sequence: list[Any] = []
    index = start
    while index < len(lines) and lines[index].startswith("  "):
        stripped = lines[index].strip()
        if stripped.startswith("- "):
            sequence.append(_scalar(stripped[2:].strip()))
        elif ":" in stripped:
            key, value = (part.strip() for part in stripped.split(":", 1))
            mapping[key] = _scalar(value)
        index += 1
    if mapping and not sequence:
        return mapping, index
    if sequence and not mapping:
        return sequence, index
    return {}, index


def _scalar(value: str) -> Any:
    if value == "":
        return ""
    if value in {"true", "false"}:
        return value == "true"
    if value.isdigit():
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [_scalar(part.strip()) for part in inner.split(",")] if inner else []
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


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
