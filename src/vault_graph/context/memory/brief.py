"""When a project brief needs an update (spec 2026-11-05 §4.4.7, §4.4.4 rule 4, A-35).

The brief is the Vault page ``wiki/projects/<project>.md`` with ``type: project``. The agent writes
it through the existing write paths (``remember(kind="project")``, then ``update_memory``). vg never
writes or edits the brief: this module only reads indexed document metadata and decides when to ask.

Rule: count the decision pages (``type: decision`` or ``memory_kind: decision``) that are current
(status not ``superseded``, ``deprecated``, ``retired`` or ``stale``) and were created or updated after
the brief's ``updated``. The page date is its ``updated``, else ``created``, else ``date``. With
``threshold`` or more the brief needs an update. Without a brief, or with a brief that has no readable
``updated``, every current decision counts. A decision without a readable date never counts against a
dated brief. Dates compare by day unless both sides carry a time, so a decision written on the day of
the brief update does not count against a date-only brief.

``project_brief_staleness`` picks the brief and the decisions of one project with the project scope
rule (§4.4.2). The candidate key is ``brief:<project>:<12 hex>``, the sha256 of the counted pages'
paths and dates: a new decision changes it, so a skipped brief candidate comes back (§4.4.4 rule 4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from vault_graph.context.memory.project_memory import STALE_STATUSES
from vault_graph.context.memory.project_scope import UNMAPPED_VAULT_SCOPE, VaultProjectScope, page_in_project
from vault_graph.indexing.ingestion.document_normalizer import DocumentSnapshot

# Spec 2026-11-05 목표4, risk D9: [가정] five new decisions since the brief.
BRIEF_STALE_THRESHOLD = 5
BRIEF_PAGE_TYPE = "project"
BRIEF_KEY_PREFIX = "brief:"
BRIEF_KEY_HASH_LENGTH = 12
DECISION_KIND = "decision"
_DATE_FIELDS = ("updated", "created", "date")


@dataclass(frozen=True)
class BriefStaleness:
    """Result of the brief update rule. ``new_decisions`` are the counted pages, sorted by path."""

    brief: DocumentSnapshot | None
    new_decisions: tuple[DocumentSnapshot, ...]
    threshold: int

    @property
    def count(self) -> int:
        return len(self.new_decisions)

    @property
    def stale(self) -> bool:
        """True when the brief needs an update: ``count`` reached ``threshold``."""
        return self.count >= self.threshold

    @property
    def digest(self) -> str:
        """First 12 hex digits of the sha256 of the counted pages' paths and dates."""
        text = "".join(f"{document.path}\t{_date_text(document)}\n" for document in self.new_decisions)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:BRIEF_KEY_HASH_LENGTH]


@dataclass(frozen=True)
class ProjectBriefStaleness:
    """The brief rule for one project, with the candidate key and the brief path to write."""

    project_id: str
    staleness: BriefStaleness
    warnings: tuple[str, ...] = ()

    @property
    def stale(self) -> bool:
        return self.staleness.stale

    @property
    def key(self) -> str:
        return brief_candidate_key(self.project_id, self.staleness.digest)

    @property
    def brief_path(self) -> str:
        return brief_path(self.project_id)


def brief_staleness(
    brief: DocumentSnapshot | None, decisions: Sequence[DocumentSnapshot], *, threshold: int
) -> BriefStaleness:
    """Apply the update rule. ``decisions`` may hold other pages: only current decision pages count.

    The project scope is the caller's job (``project_brief_staleness`` does it).
    """
    if isinstance(threshold, bool) or threshold < 1:
        raise ValueError("threshold must be a positive integer")
    since = _page_moment(brief) if brief is not None else None
    counted: dict[tuple[str, str], DocumentSnapshot] = {}
    for document in decisions:
        if not is_current_decision(document):
            continue
        if since is not None:
            moment = _page_moment(document)
            if moment is None or not _after(moment, since):
                continue
        counted.setdefault((document.path, document.vault_id), document)
    ordered = tuple(counted[key] for key in sorted(counted))
    return BriefStaleness(brief=brief, new_decisions=ordered, threshold=threshold)


def project_brief_staleness(
    documents_by_vault: Mapping[str, Sequence[DocumentSnapshot]],
    *,
    project_id: str,
    vault_scopes: Mapping[str, VaultProjectScope],
    threshold: int = BRIEF_STALE_THRESHOLD,
) -> ProjectBriefStaleness:
    """The brief rule over the project's ``wiki/`` pages, chosen by ``page_in_project`` (§4.4.2).

    The brief is the first Vault in ``documents_by_vault`` order with a current in-scope
    ``wiki/projects/<project>.md`` of ``type: project``, as in recall block L3. A brief in another
    Vault too gives one warning line and is not used.
    """
    path = brief_path(project_id)
    briefs: list[DocumentSnapshot] = []
    decisions: list[DocumentSnapshot] = []
    for vault_id, documents in documents_by_vault.items():
        vault_scope = vault_scopes.get(vault_id, UNMAPPED_VAULT_SCOPE)
        for document in documents:
            if not document.path.startswith("wiki/"):
                continue
            if not page_in_project(document.frontmatter, project_id, vault_scope=vault_scope):
                continue
            if document.path == path and _is_current_brief(document):
                briefs.append(document)
            elif is_current_decision(document):
                decisions.append(document)
    warnings: tuple[str, ...] = ()
    if len(briefs) > 1:
        others = ", ".join(document.vault_id for document in briefs[1:])
        warnings = (f"Brief {path} is in more than one Vault; using Vault {briefs[0].vault_id}, not {others}.",)
    staleness = brief_staleness(briefs[0] if briefs else None, decisions, threshold=threshold)
    return ProjectBriefStaleness(project_id=project_id, staleness=staleness, warnings=warnings)


def brief_path(project_id: str) -> str:
    return f"wiki/projects/{project_id}.md"


def brief_candidate_key(project_id: str, digest: str) -> str:
    return f"{BRIEF_KEY_PREFIX}{project_id}:{digest}"


def is_current_decision(document: DocumentSnapshot) -> bool:
    frontmatter = document.frontmatter
    is_decision = DECISION_KIND in (_value(frontmatter.get("type")), _value(frontmatter.get("memory_kind")))
    return is_decision and _value(frontmatter.get("status")) not in STALE_STATUSES


def _is_current_brief(document: DocumentSnapshot) -> bool:
    frontmatter = document.frontmatter
    is_brief = _value(frontmatter.get("type")) == BRIEF_PAGE_TYPE
    return is_brief and _value(frontmatter.get("status")) not in STALE_STATUSES


def _value(value: object) -> str:
    return str(value).strip().casefold() if value is not None else ""


def _date_value(document: DocumentSnapshot) -> object:
    for name in _DATE_FIELDS:
        value = document.frontmatter.get(name)
        if value is not None and str(value).strip():
            return value
    return None


def _date_text(document: DocumentSnapshot) -> str:
    value = _date_value(document)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return "" if value is None else str(value).strip()


def _page_moment(document: DocumentSnapshot) -> date | datetime | None:
    """The page date as a day, or as an aware time when the value carries one. None when unreadable."""
    value = _date_value(document)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if len(text) > 10:
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            pass
        else:
            return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _after(moment: date | datetime, since: date | datetime) -> bool:
    if isinstance(moment, datetime) and isinstance(since, datetime):
        return moment > since
    return _day(moment) > _day(since)


def _day(moment: date | datetime) -> date:
    return moment.date() if isinstance(moment, datetime) else moment


__all__ = [
    "BRIEF_KEY_PREFIX",
    "BRIEF_PAGE_TYPE",
    "BRIEF_STALE_THRESHOLD",
    "BriefStaleness",
    "ProjectBriefStaleness",
    "brief_candidate_key",
    "brief_path",
    "brief_staleness",
    "is_current_decision",
    "project_brief_staleness",
]
