"""Vault frontmatter line rules, shared by indexing (M02) and memory writes (M18).

The rules follow Vault ``tools/wiki/lib/frontmatter.py`` ``parse_page``. Indexing uses them when
strict YAML rejects a block that the Vault accepts. Memory writes use them to keep every unchanged
value as the Vault would render it again.
"""

from __future__ import annotations

from typing import Any

_OPEN = "---\n"
_CLOSE = "\n---\n"


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return ``(raw block, body)``, or None when the page has no closed frontmatter block."""
    if not text.startswith(_OPEN):
        return None
    end = text.find(_CLOSE, len(_OPEN))
    if end == -1:
        return None
    return text[len(_OPEN) : end], text[end + len(_CLOSE) :]


def parse_vault_frontmatter(raw: str) -> dict[str, Any]:
    """Parse a raw frontmatter block (without the ``---`` lines) with the Vault line rules."""
    lines = raw.splitlines()
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


__all__ = ["parse_vault_frontmatter", "split_frontmatter"]
