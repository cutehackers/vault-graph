"""What a memory proposal would change, built from its draft and the target page text (spec 2026-11-20 D4).

The draft shape decides what is shown:

- ``upsert-page`` with no current page: the whole new page (frontmatter and body).
- ``upsert-page`` on an existing page: a line diff of the body and the frontmatter keys whose value differs.
- ``patch-page``: the draft as written, that is the frontmatter keys it sets and each edit with its fields.
  The page that results is never computed here. Only the Vault's ``materialize_patch`` knows the patch
  rules, and a second implementation could drift from it.

Evidence lines are the ``- Evidence:`` lines of an ``upsert-page`` body and the ``evidence`` value of each edit.

Every function here is pure: no file, no clock, no process. The caller reads the draft and the page.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from vault_graph.operation.memory.memory_drafts import parse_frontmatter
from vault_graph.operation.scope.vault_frontmatter import split_frontmatter

ChangeKind = Literal["new-page", "page-update", "patch"]
FrontmatterChangeKind = Literal["added", "changed", "removed", "set"]

UPSERT_OPERATION = "upsert-page"
PATCH_OPERATION = "patch-page"
EVIDENCE_PREFIX = "- Evidence:"
BODY_UNCHANGED_LINE = "(body unchanged)"
_DIFF_CONTEXT_LINES = 3
_EDIT_FIELD_LABELS: dict[str, dict[str, str]] = {"supersede-claim": {"claim": "old claim", "by": "new claim"}}


@dataclass(frozen=True)
class FrontmatterChange:
    """One frontmatter key the proposal touches.

    ``added``, ``changed`` and ``removed`` compare an ``upsert-page`` draft with the current page. ``set`` is a
    key a ``patch-page`` draft writes: the current value is not looked up, so ``before`` is None.
    """

    key: str
    kind: FrontmatterChangeKind
    before: object | None
    after: object | None


@dataclass(frozen=True)
class EditChange:
    """One ``patch-page`` edit as the draft wrote it: its ``op`` and every other field in draft order."""

    op: str
    fields: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ProposalChange:
    kind: ChangeKind
    path: str
    # The whole page a new-page proposal would create. None for the other kinds.
    new_page: str | None = None
    # Unified diff lines of the body without the file header lines. Empty when the body stays the same.
    body_diff: tuple[str, ...] = ()
    frontmatter: tuple[FrontmatterChange, ...] = ()
    edits: tuple[EditChange, ...] = ()
    evidence: tuple[str, ...] = ()


def build_proposal_change(draft: Mapping[str, object], current_text: str | None) -> ProposalChange:
    """Build the change of one draft. ``current_text`` is the target page as read now, or None when it is absent.

    Raises ``ValueError`` with the reason when the draft is not one of the shapes vault-graph proposes.
    """
    operation = draft.get("operation")
    path = draft.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("The draft has no target path.")
    if operation == UPSERT_OPERATION:
        return _upsert_change(draft, path, current_text)
    if operation == PATCH_OPERATION:
        return _patch_change(draft, path)
    raise ValueError(f"The draft operation {operation!r} is not {UPSERT_OPERATION} or {PATCH_OPERATION}.")


def render_proposal_change(change: ProposalChange) -> tuple[str, ...]:
    """Turn a change into display lines. Text from the draft and the page is kept as it is."""
    lines: list[str] = []
    if change.kind == "new-page":
        lines.append(f"New page: {change.path}")
        lines.extend((change.new_page or "").splitlines())
    elif change.kind == "page-update":
        lines.append(f"Changed page: {change.path}")
        if change.frontmatter:
            lines.append("Frontmatter:")
            lines.extend(_frontmatter_line(item) for item in change.frontmatter)
        lines.append("Body:")
        lines.extend(change.body_diff or (BODY_UNCHANGED_LINE,))
    else:
        lines.append(f"Patch to page: {change.path}")
        if change.frontmatter:
            lines.append("Frontmatter:")
            lines.extend(_frontmatter_line(item) for item in change.frontmatter)
        for edit in change.edits:
            labels = _EDIT_FIELD_LABELS.get(edit.op, {})
            lines.append(f"Edit: {edit.op}")
            lines.extend(f"  {labels.get(name, name)}: {value}" for name, value in edit.fields)
    if change.evidence:
        lines.append("Evidence:")
        lines.extend(f"- {item}" for item in change.evidence)
    return tuple(lines)


def _upsert_change(draft: Mapping[str, object], path: str, current_text: str | None) -> ProposalChange:
    frontmatter = draft.get("frontmatter")
    body = draft.get("body")
    if not isinstance(frontmatter, Mapping):
        raise ValueError(f"The {UPSERT_OPERATION} draft has no frontmatter object.")
    if not isinstance(body, str):
        raise ValueError(f"The {UPSERT_OPERATION} draft has no body text.")
    evidence = _body_evidence(body)
    if current_text is None:
        return ProposalChange("new-page", path, new_page=_page_text(frontmatter, body), evidence=evidence)
    block = split_frontmatter(current_text)
    current_body = block[1] if block is not None else current_text
    return ProposalChange(
        "page-update",
        path,
        body_diff=_body_diff(current_body, body),
        frontmatter=_frontmatter_changes(parse_frontmatter(current_text) or {}, frontmatter),
        evidence=evidence,
    )


def _patch_change(draft: Mapping[str, object], path: str) -> ProposalChange:
    frontmatter = draft.get("frontmatter", {})
    edits = draft.get("edits", [])
    if not isinstance(frontmatter, Mapping):
        raise ValueError(f"The {PATCH_OPERATION} draft frontmatter is not an object.")
    if not isinstance(edits, list):
        raise ValueError(f"The {PATCH_OPERATION} draft edits are not a list.")
    edit_changes: list[EditChange] = []
    evidence: list[str] = []
    for edit in edits:
        if not isinstance(edit, Mapping) or not isinstance(edit.get("op"), str):
            raise ValueError(f"A {PATCH_OPERATION} draft edit has no op.")
        fields = tuple((str(name), _display(value)) for name, value in edit.items() if name != "op")
        edit_changes.append(EditChange(str(edit["op"]), fields))
        edit_evidence = edit.get("evidence")
        if isinstance(edit_evidence, str) and edit_evidence.strip():
            evidence.append(edit_evidence.strip())
    return ProposalChange(
        "patch",
        path,
        frontmatter=tuple(FrontmatterChange(str(key), "set", None, value) for key, value in frontmatter.items()),
        edits=tuple(edit_changes),
        evidence=tuple(evidence),
    )


def _frontmatter_changes(
    current: Mapping[str, object], proposed: Mapping[str, object]
) -> tuple[FrontmatterChange, ...]:
    """Keys in draft order whose value differs, then the keys the draft drops."""
    changes: list[FrontmatterChange] = []
    for key, value in proposed.items():
        if key not in current:
            changes.append(FrontmatterChange(str(key), "added", None, value))
        elif current[key] != value:
            changes.append(FrontmatterChange(str(key), "changed", current[key], value))
    changes.extend(
        FrontmatterChange(str(key), "removed", value, None) for key, value in current.items() if key not in proposed
    )
    return tuple(changes)


def _body_diff(current_body: str, proposed_body: str) -> tuple[str, ...]:
    """Line diff of the two bodies. Blank lines at either end are not compared."""
    before = current_body.strip("\n").splitlines()
    after = proposed_body.strip("\n").splitlines()
    diff = difflib.unified_diff(before, after, lineterm="", n=_DIFF_CONTEXT_LINES)
    return tuple(line for line in diff if not line.startswith(("--- ", "+++ ")) and line not in ("---", "+++"))


def _body_evidence(body: str) -> tuple[str, ...]:
    lines = (line.strip() for line in body.splitlines())
    return tuple(line.removeprefix(EVIDENCE_PREFIX).strip() for line in lines if line.startswith(EVIDENCE_PREFIX))


def _page_text(frontmatter: Mapping[str, object], body: str) -> str:
    """The new page for display. The Vault renders the stored page itself when it publishes."""
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, Mapping) and value:
            lines.append(f"{key}:")
            lines.extend(f"  {name}: {_display(item)}" for name, item in value.items())
        elif isinstance(value, list) and value:
            lines.append(f"{key}:")
            lines.extend(f"  - {_display(item)}" for item in value)
        else:
            lines.append(f"{key}: {_display(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def _frontmatter_line(change: FrontmatterChange) -> str:
    if change.kind == "set":
        return f"{change.key}: {_display(change.after)}"
    before = "(none)" if change.kind == "added" else _display(change.before)
    after = "(removed)" if change.kind == "removed" else _display(change.after)
    return f"{change.key}: {before} -> {after}"


def _display(value: object) -> str:
    """Text stays as written. Other values are JSON without ASCII escapes, so Korean stays readable."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


__all__ = [
    "BODY_UNCHANGED_LINE",
    "EVIDENCE_PREFIX",
    "ChangeKind",
    "EditChange",
    "FrontmatterChange",
    "FrontmatterChangeKind",
    "ProposalChange",
    "build_proposal_change",
    "render_proposal_change",
]
