"""Build the Vault ``upsert-page`` draft from the agent's fields only (spec 4.2.4, 결정7, V1).

The draft format follows Vault ``tools/wiki/lib/draft.py`` (``version`` 1, ``upsert-page``) and
``tools/wiki/templates/draft-upsert-page.json``. The draft holds only the agent's fields and
the run date; nothing is rewritten or summarized.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date

from vault_graph.operation.memory.memory_requests import RememberRequest

_KIND_FOLDERS = {"decision": "decisions", "system": "systems"}
_KIND_INDEX_SECTIONS = {"decision": "Decisions", "system": "Systems"}
_KIND_LOG_EVENTS = {"decision": "decision", "system": "manual-note"}
_MAX_SLUG_CHARS = 80


def build_draft(request: RememberRequest, *, today: date) -> dict[str, object]:
    """Build the Vault ``upsert-page`` draft from the agent's fields only."""
    title = request.title.strip()
    evidence = tuple(item.strip() for item in request.evidence)
    target = f"{_KIND_FOLDERS[request.kind]}/{page_slug(title)}"
    day = today.isoformat()
    evidence_lines = "".join(f"- Evidence: {item}\n" for item in evidence)
    return {
        "version": 1,
        "operation": "upsert-page",
        "path": f"wiki/{target}.md",
        "frontmatter": {
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
        },
        "body": f"# {title}\n\n{request.body.strip()}\n\n## Evidence\n\nStatus: stated\n\n{evidence_lines}",
        "index": {"section": _KIND_INDEX_SECTIONS[request.kind], "target": target, "summary": title},
        "log": {
            "event_type": _KIND_LOG_EVENTS[request.kind],
            "title": f"Remember {request.kind}: {title}",
            "items": [f"Added [[{target}]]."],
        },
    }


def page_slug(title: str) -> str:
    """Turn a title into a file name: lowercase word characters joined by ``-``."""
    text = unicodedata.normalize("NFC", title).lower()
    slug = re.sub(r"[\W_]+", "-", text).strip("-")[:_MAX_SLUG_CHARS].strip("-")
    if slug:
        return slug
    return "memory-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:12]


__all__ = ["build_draft", "page_slug"]
