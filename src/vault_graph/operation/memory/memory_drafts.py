"""Build the Vault drafts for add, update and retire from the agent's fields and the run date only.

spec 2026-11-02 V3 draft table, 결정7, 결정S6, 결정S8. The formats follow Vault ``tools/wiki``:

- add and update: ``upsert-page`` (``tools/wiki/lib/draft.py``, ``templates/draft-upsert-page.json``).
- retire: frontmatter-only ``patch-page`` (계약3, ``tools/wiki/lib/draft_patch.py``), so the Vault
  reads the current page when it applies the draft and the body is never sent again.
- memory fields and status ``retired``: 계약2 (``tools/wiki/lib/memory_fields.py``).

Every function here is pure: no file, no clock. Nothing the agent wrote is rewritten or summarized.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from typing import Any

from vault_graph.operation.memory.memory_ports import PageText
from vault_graph.operation.memory.memory_requests import RememberRequest, RetireRequest, UpdateRequest

MEMORY_SCHEMA = "vault-memory/v1"

_KIND_FOLDERS = {"decision": "decisions", "system": "systems"}
_KIND_INDEX_SECTIONS = {"decision": "Decisions", "system": "Systems"}
_KIND_LOG_EVENTS = {"decision": "decision", "system": "manual-note"}
_MAX_SLUG_CHARS = 80


def build_remember_draft(request: RememberRequest, *, today: date) -> dict[str, object]:
    """Build the ``upsert-page`` draft for a new page."""
    title = request.title.strip()
    evidence = _evidence(request.evidence)
    target = f"{_KIND_FOLDERS[request.kind]}/{page_slug(title)}"
    day = today.isoformat()
    frontmatter: dict[str, Any] = {
        "title": title,
        "type": request.kind,
        "status": "active",
        "created": day,
        "updated": day,
        "owner": "agent",
        "summary": title,
        "source_count": len(evidence),
        "tags": [],
        "related": [],
        "confidence": "medium",
        "quality": {
            "provenance": "section",
            "links": "unchecked",
            "contradictions": "unchecked",
            "review_required": False,
        },
    }
    _set_memory_fields(frontmatter, pin=True if request.pin else None, memory_kind=request.memory_kind)
    return {
        "version": 1,
        "operation": "upsert-page",
        "path": f"wiki/{target}.md",
        "frontmatter": frontmatter,
        "body": _body(title, request.body, request.basis, evidence),
        "index": {"section": _KIND_INDEX_SECTIONS[request.kind], "target": target, "summary": title},
        "log": {
            "event_type": _KIND_LOG_EVENTS[request.kind],
            "title": f"Remember {request.kind}: {title}",
            "items": [f"Added [[{target}]]."],
        },
    }


def build_update_draft(request: UpdateRequest, current: PageText, *, today: date) -> dict[str, object]:
    """Build the ``upsert-page`` draft that keeps the current frontmatter and replaces the body (결정S8).

    Raises ``ValueError`` when the current page has no frontmatter to keep.
    """
    current_frontmatter = parse_frontmatter(current.text)
    if current_frontmatter is None:
        raise ValueError(f"{request.path} has no frontmatter, so it cannot be updated as a memory page.")
    frontmatter = dict(current_frontmatter)
    evidence = _evidence(request.evidence)
    if request.title is not None:
        frontmatter["title"] = request.title.strip()
        frontmatter["summary"] = request.title.strip()
    frontmatter["updated"] = today.isoformat()
    frontmatter["source_count"] = len(evidence)
    _set_memory_fields(frontmatter, pin=request.pin, memory_kind=request.memory_kind)
    title = str(frontmatter.get("title") or _link_target(request.path))
    target = _link_target(request.path)
    return {
        "version": 1,
        "operation": "upsert-page",
        "path": request.path,
        "frontmatter": frontmatter,
        "body": _body(title, request.body, request.basis, evidence),
        "log": {
            "event_type": "decision" if frontmatter.get("type") == "decision" else "manual-note",
            "title": f"Update memory: {title}",
            "items": [f"Updated [[{target}]]."],
        },
    }


def build_retire_draft(request: RetireRequest, *, today: date) -> dict[str, object]:
    """Build the frontmatter-only ``patch-page`` draft that retires or deprecates a page."""
    target = _link_target(request.path)
    reason = request.reason.strip()
    if request.replaced_by is None:
        frontmatter: dict[str, object] = {
            "status": "retired",
            "retired_reason": reason,
            "retired_at": today.isoformat(),
        }
        item = f"Retired [[{target}]]: {reason}"
    else:
        replacement = _link_target(request.replaced_by)
        frontmatter = {"status": "deprecated", "superseded_by": [replacement]}
        item = f"Retired [[{target}]], replaced by [[{replacement}]]: {reason}"
    return {
        "version": 1,
        "operation": "patch-page",
        "path": request.path,
        "frontmatter": frontmatter,
        "log": {"event_type": "manual-note", "title": f"Retire memory: {target}", "items": [item]},
    }


def page_slug(title: str) -> str:
    """Turn a title into a file name: lowercase word characters joined by ``-``."""
    text = unicodedata.normalize("NFC", title).lower()
    slug = re.sub(r"[\W_]+", "-", text).strip("-")[:_MAX_SLUG_CHARS].strip("-")
    if slug:
        return slug
    return "memory-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]


def parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Read page frontmatter the way Vault ``tools/wiki/lib/frontmatter.py`` ``parse_page`` does.

    Using the Vault's own rules keeps every unchanged value as the Vault would render it again.
    Returns None when the page has no closed frontmatter block.
    """
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    lines = text[4:end].splitlines()
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


def _set_memory_fields(frontmatter: dict[str, Any], *, pin: bool | None, memory_kind: str | None) -> None:
    """Add 계약2 fields. ``memory_schema`` comes with any of them (lint rule 1)."""
    if pin is not None:
        frontmatter["pin"] = pin
    if memory_kind is not None:
        frontmatter["memory_kind"] = memory_kind
    if pin is not None or memory_kind is not None:
        frontmatter["memory_schema"] = MEMORY_SCHEMA


def _body(title: str, body: str, basis: str, evidence: tuple[str, ...]) -> str:
    evidence_lines = "".join(f"- Evidence: {item}\n" for item in evidence)
    return f"# {title}\n\n{body.strip()}\n\n## Evidence\n\nStatus: {basis}\n\n{evidence_lines}"


def _evidence(items: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item.strip() for item in items)


def _link_target(path: str) -> str:
    """``wiki/decisions/a.md`` -> ``decisions/a``, the form Vault wiki links and ``superseded_by`` use."""
    return path.removeprefix("wiki/").removesuffix(".md")


__all__ = [
    "MEMORY_SCHEMA",
    "build_remember_draft",
    "build_retire_draft",
    "build_update_draft",
    "page_slug",
    "parse_frontmatter",
]
