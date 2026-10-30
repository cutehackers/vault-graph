"""Record one stated memory in a Vault through the Vault tool's publish-draft (spec 4.2.4, 결정8, S5, S6).

vault-graph never writes Vault files itself. This service checks the agent's fields, picks one
Vault without guessing, builds a draft in the operating system's temporary directory, and
hands the draft to a ``VaultPublisher``. The draft directory is removed after every outcome.
The draft format follows Vault ``tools/wiki/lib/draft.py`` (``version`` 1, ``upsert-page``) and
``tools/wiki/templates/draft-upsert-page.json``. The draft holds only the agent's fields and
the run date; nothing is rewritten or summarized (결정7).
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import threading
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

from vault_graph.project.context.project_binding_reader import MappedVault, VaultMapReader

RememberStatus = Literal["published", "rejected", "error"]

REMEMBER_KINDS: tuple[str, ...] = ("decision", "system")
PUBLISH_TIMEOUT_SECONDS = 120.0  # Same as the llm-wiki router CLI_TIMEOUT_SECONDS.
NEXT_INDEX_MESSAGE = "The recorded page becomes searchable after the next index run (vg index)."

_KIND_FOLDERS = {"decision": "decisions", "system": "systems"}
_KIND_INDEX_SECTIONS = {"decision": "Decisions", "system": "Systems"}
_KIND_LOG_EVENTS = {"decision": "decision", "system": "manual-note"}
_MAX_SLUG_CHARS = 80


@dataclass(frozen=True)
class PublishOutcome:
    """What the Vault publish-draft run reported."""

    status: RememberStatus
    written_paths: tuple[str, ...] = ()
    messages: tuple[str, ...] = ()


class VaultPublisher(Protocol):
    def publish_draft(self, vault_root: Path, draft_path: Path, *, timeout_s: float) -> PublishOutcome: ...


@dataclass(frozen=True)
class RememberRequest:
    title: str
    kind: str
    body: str
    evidence: tuple[str, ...]
    cwd: str | None = None
    vault: str | None = None


@dataclass(frozen=True)
class RememberResult:
    status: RememberStatus
    vault: str | None
    written_paths: tuple[str, ...]
    messages: tuple[str, ...]


_LOCKS_GUARD = threading.Lock()
_VAULT_LOCKS: dict[str, threading.Lock] = {}


def _vault_lock(vault_root: Path) -> threading.Lock:
    """Return the process-wide lock for one Vault so calls for it run one at a time."""
    with _LOCKS_GUARD:
        return _VAULT_LOCKS.setdefault(str(vault_root), threading.Lock())


class RememberService:
    def __init__(
        self,
        *,
        vault_map: VaultMapReader | None,
        publisher: VaultPublisher,
        today: Callable[[], date] = date.today,
        temp_root: Path | None = None,
        timeout_s: float = PUBLISH_TIMEOUT_SECONDS,
        vault_map_problem: str | None = None,
    ) -> None:
        self._vault_map = vault_map
        self._publisher = publisher
        self._today = today
        self._temp_root = temp_root
        self._timeout_s = timeout_s
        self._vault_map_problem = vault_map_problem

    def remember(self, request: RememberRequest) -> RememberResult:
        problems = validate_request(request)
        if problems:
            return RememberResult("rejected", request.vault, (), problems)

        selected = self._select_vault(request)
        if isinstance(selected, str):
            return RememberResult("error", None, (), (selected,))

        draft = build_draft(request, today=self._today())
        target = str(draft["path"])
        if (selected.path / target).exists():
            return RememberResult(
                "rejected",
                selected.name,
                (),
                (f"A page already exists at {target}. remember only adds new pages.",),
            )

        with _vault_lock(selected.path):
            outcome = self._publish(selected.path, draft)
        messages = outcome.messages
        if outcome.status == "published":
            messages = (*messages, NEXT_INDEX_MESSAGE)
        return RememberResult(outcome.status, selected.name, outcome.written_paths, messages)

    def _publish(self, vault_root: Path, draft: dict[str, object]) -> PublishOutcome:
        with tempfile.TemporaryDirectory(prefix="vault-graph-remember-", dir=self._temp_root) as folder:
            draft_path = Path(folder) / f"{Path(str(draft['path'])).stem}.json"
            draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                return self._publisher.publish_draft(vault_root, draft_path, timeout_s=self._timeout_s)
            except Exception as exc:  # noqa: BLE001 - any publisher failure is reported, never retried.
                return PublishOutcome("error", (), (f"publish-draft could not run: {exc}",))

    def _select_vault(self, request: RememberRequest) -> MappedVault | str:
        if self._vault_map is None:
            reason = self._vault_map_problem or "vault-map.json is missing or unusable."
            return f"Cannot choose the target Vault: {reason}"
        if request.vault is not None:
            for vault in self._vault_map.vaults:
                if vault.name == request.vault:
                    return vault
            return f"Cannot choose the target Vault: no Vault named {request.vault} in vault-map.json."
        if request.cwd is None:
            return "Cannot choose the target Vault: pass vault or cwd."
        match = self._vault_map.find_project(Path(request.cwd))
        if len(match.vaults) == 1:
            return match.vaults[0]
        if len(match.vaults) > 1:
            names = ", ".join(vault.name for vault in match.vaults)
            return f"Cannot choose the target Vault: the project links several Vaults ({names}). Pass vault."
        reason = match.reason or f"{request.cwd} is not linked to a Vault."
        return f"Cannot choose the target Vault: {reason}"


def validate_request(request: RememberRequest) -> tuple[str, ...]:
    problems: list[str] = []
    if not _non_empty(request.title):
        problems.append("title must be a non-empty string.")
    if not _non_empty(request.body):
        problems.append("body must be a non-empty string.")
    if request.kind not in REMEMBER_KINDS:
        problems.append(f"kind must be one of {', '.join(REMEMBER_KINDS)}.")
    if not _is_evidence(request.evidence):
        problems.append("evidence must list at least one non-empty string.")
    return tuple(problems)


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


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_evidence(value: object) -> bool:
    if isinstance(value, str) or not isinstance(value, Sequence):
        return False
    return bool(value) and all(_non_empty(item) for item in value)


__all__ = [
    "NEXT_INDEX_MESSAGE",
    "PUBLISH_TIMEOUT_SECONDS",
    "REMEMBER_KINDS",
    "PublishOutcome",
    "RememberRequest",
    "RememberResult",
    "RememberService",
    "RememberStatus",
    "VaultPublisher",
    "build_draft",
    "page_slug",
    "validate_request",
]
