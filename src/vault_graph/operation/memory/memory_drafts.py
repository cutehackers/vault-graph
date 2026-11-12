"""Build the Vault drafts for add, update, retire, claim supersede and restore from the agent's fields and the run date.

spec 2026-11-02 V3 draft table, 결정7, 결정S6, 결정S8. The formats follow Vault ``tools/wiki``:

- add and update: ``upsert-page`` (``tools/wiki/lib/draft.py``, ``templates/draft-upsert-page.json``).
- retire: frontmatter-only ``patch-page`` (계약3, ``tools/wiki/lib/draft_patch.py``), so the Vault
  reads the current page when it applies the draft and the body is never sent again.
- supersede one claim: ``patch-page`` with one ``supersede-claim`` edit (spec 2026-11-05 §4.4.4, 결정43,
  ``docs/agent/DRAFTS.md`` patch table).
- restore: frontmatter-only ``patch-page`` that sets ``status: active``, ``restored_at`` and
  ``restored_reason`` and leaves ``retired_reason``, ``retired_at`` and ``superseded_by`` as history
  (spec 2026-11-05 §4.4.13-3, Vault request S12).
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
from vault_graph.operation.memory.memory_requests import (
    PROJECT_KIND,
    TAGGED_MEMORY_KINDS,
    RememberRequest,
    RestoreRequest,
    RetireRequest,
    SupersedeClaimRequest,
    UpdateRequest,
)
from vault_graph.operation.scope.vault_frontmatter import parse_vault_frontmatter, split_frontmatter

MEMORY_SCHEMA = "vault-memory/v1"

_KIND_FOLDERS = {"decision": "decisions", "system": "systems", PROJECT_KIND: "projects"}
_KIND_INDEX_SECTIONS = {"decision": "Decisions", "system": "Systems", PROJECT_KIND: "Projects"}
_KIND_LOG_EVENTS = {"decision": "decision", "system": "manual-note", PROJECT_KIND: "manual-note"}
_MAX_SLUG_CHARS = 80
# The page statuses a page leaves recall with, and so the ones restore accepts
# (context/memory/project_memory.py STALE_STATUSES, spec 2026-11-05 §4.4.13).
RESTORABLE_STATUSES: tuple[str, ...] = ("superseded", "deprecated", "retired")


def build_remember_draft(request: RememberRequest, *, today: date) -> dict[str, object]:
    """Build the ``upsert-page`` draft for a new page.

    With ``project_id`` the page gets frontmatter ``project``, and a ``correction`` or ``rule`` memory
    kind is also put in ``tags``, so the Vault project summary lists the page (spec 2026-11-05 §4.4.3).

    Kind ``project`` is the project brief: its file name is the project id, not the title, because the
    Vault accepts ``type: project`` only at ``wiki/projects/<project>.md`` (spec 2026-11-05 §4.4.7).
    ``validate_remember`` has already checked that a brief request has a project id.

    ``summary`` and ``aliases`` are the agent's own words (spec 2026-11-11 §4.3.1). The Vault requires a
    ``summary``, so a request without one keeps the title there.
    """
    title = request.title.strip()
    evidence = _evidence(request.evidence)
    name = str(request.project_id) if request.kind == PROJECT_KIND else page_slug(title)
    target = f"{_KIND_FOLDERS[request.kind]}/{name}"
    day = today.isoformat()
    frontmatter: dict[str, Any] = {
        "title": title,
        "type": request.kind,
        "status": "active",
        "created": day,
        "updated": day,
        "owner": "agent",
        "summary": request.summary.strip() if request.summary is not None else title,
        "source_count": len(evidence),
        "tags": [request.memory_kind] if request.memory_kind in TAGGED_MEMORY_KINDS else [],
        "related": [],
        "confidence": "medium",
        "quality": {
            "provenance": "section",
            "links": "unchecked",
            "contradictions": "unchecked",
            "review_required": False,
        },
    }
    if request.project_id is not None:
        frontmatter["project"] = request.project_id
    if request.aliases:
        frontmatter["aliases"] = _aliases(request.aliases)
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

    A new title also replaces a ``summary`` that only repeated the old title. A summary the agent or a
    person wrote stays until the request gives a new one.

    Raises ``ValueError`` when the current page has no frontmatter to keep.
    """
    current_frontmatter = parse_frontmatter(current.text)
    if current_frontmatter is None:
        raise ValueError(f"{request.path} has no frontmatter, so it cannot be updated as a memory page.")
    frontmatter = dict(current_frontmatter)
    evidence = _evidence(request.evidence)
    if request.title is not None:
        if frontmatter.get("summary") in (None, "", frontmatter.get("title")):
            frontmatter["summary"] = request.title.strip()
        frontmatter["title"] = request.title.strip()
    if request.summary is not None:
        frontmatter["summary"] = request.summary.strip()
    if request.aliases:
        frontmatter["aliases"] = _aliases(request.aliases)
    elif request.aliases is not None:
        frontmatter.pop("aliases", None)
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


def build_supersede_claim_draft(request: SupersedeClaimRequest) -> dict[str, object]:
    """Build the ``patch-page`` draft whose one ``supersede-claim`` edit replaces one claim row.

    The Vault marks the matching row ``superseded``, adds ``Superseded by:`` to its evidence and inserts
    the new row below it. The new row's status is the basis. The Vault sets ``updated`` itself.
    """
    target = _link_target(request.path)
    claim = request.claim.strip()
    return {
        "version": 1,
        "operation": "patch-page",
        "path": request.path,
        "edits": [
            {
                "op": "supersede-claim",
                "claim": claim,
                "by": request.new_claim.strip(),
                "status": request.basis,
                "evidence": request.evidence.strip(),
            }
        ],
        "log": {
            "event_type": "manual-note",
            "title": f"Supersede claim: {target}",
            "items": [f"Superseded a claim in [[{target}]]: {claim}"],
        },
    }


def build_restore_draft(request: RestoreRequest, current: PageText, *, today: date) -> dict[str, object]:
    """Build the frontmatter-only ``patch-page`` draft that makes a retired page current again.

    Raises ``ValueError`` when the current page is not retired, deprecated or superseded.
    """
    status = (parse_frontmatter(current.text) or {}).get("status")
    if status not in RESTORABLE_STATUSES:
        raise ValueError(f"{request.path} is not a retired page (status: {status}), so there is nothing to restore.")
    target = _link_target(request.path)
    reason = request.reason.strip()
    return {
        "version": 1,
        "operation": "patch-page",
        "path": request.path,
        "frontmatter": {"status": "active", "restored_at": today.isoformat(), "restored_reason": reason},
        "log": {
            "event_type": "manual-note",
            "title": f"Restore memory: {target}",
            "items": [f"Restored [[{target}]]: {reason}"],
        },
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
    block = split_frontmatter(text)
    return parse_vault_frontmatter(block[0]) if block is not None else None


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


def _aliases(items: tuple[str, ...]) -> list[str]:
    return [item.strip() for item in items]


def _link_target(path: str) -> str:
    """``wiki/decisions/a.md`` -> ``decisions/a``, the form Vault wiki links and ``superseded_by`` use."""
    return path.removeprefix("wiki/").removesuffix(".md")


__all__ = [
    "MEMORY_SCHEMA",
    "RESTORABLE_STATUSES",
    "build_remember_draft",
    "build_restore_draft",
    "build_retire_draft",
    "build_supersede_claim_draft",
    "build_update_draft",
    "page_slug",
    "parse_frontmatter",
]
