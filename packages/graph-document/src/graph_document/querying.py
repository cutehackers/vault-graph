from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass

from .contracts import canonical, digest, valid_limit, valid_string
from .errors import InvalidCursorError, InvalidDocumentError
from .extraction import normalize


@dataclass(frozen=True, slots=True)
class GraphNode:
    node_id: str
    kind: str
    key: str
    label: str
    aliases: tuple[str, ...]
    source_available: bool


@dataclass(frozen=True, slots=True)
class GraphEdge:
    edge_id: str
    source_node_id: str
    target_node_id: str
    relation_type: str


@dataclass(frozen=True, slots=True)
class GraphEvidence:
    evidence_id: str
    owner_id: str
    document_id: str
    source_revision: str
    input_digest: str
    structural_id: str
    text_span: tuple[int, int] | None
    rule_id: str
    source_locator: str | None
    excerpt: str | None
    excerpt_truncated: bool


@dataclass(frozen=True, slots=True)
class GraphDocumentInfo:
    document_id: str
    source_revision: str
    input_digest: str
    extraction_digest: str
    source_locator: str | None


@dataclass(frozen=True, slots=True)
class GraphCounts:
    nodes: int
    edges: int
    evidence: int


@dataclass(frozen=True, slots=True)
class UpdateResult:
    collection_id: str
    previous_revision: int
    graph_revision: int
    changed_document_ids: tuple[str, ...]
    removed_document_ids: tuple[str, ...]
    counts: GraphCounts
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ItemQuery:
    name: str
    kinds: tuple[str, ...] = ()
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        valid_string(self.name, "name")
        valid_limit(self.limit, "limit")
        if not isinstance(self.kinds, tuple) or any(
            not isinstance(k, str) or not k for k in self.kinds
        ):
            raise InvalidDocumentError("kinds must be a tuple of nonempty strings")


@dataclass(frozen=True, slots=True)
class ItemPage:
    items: tuple[GraphNode, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class EvidenceLookup:
    by_node_id: tuple[tuple[str, tuple[GraphEvidence, ...]], ...]
    by_edge_id: tuple[tuple[str, tuple[GraphEvidence, ...]], ...]
    unknown_node_ids: tuple[str, ...]
    unknown_edge_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DocumentLookup:
    documents: tuple[GraphDocumentInfo, ...]
    unknown_document_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DocumentGraphSnapshot:
    collection_id: str
    graph_revision: int
    profile_digest: str
    name_normalization: str
    selection: str | tuple[str, ...]
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    evidence: tuple[GraphEvidence, ...]
    documents: tuple[GraphDocumentInfo, ...]
    digest: str

    def find_items(self, query: ItemQuery) -> ItemPage:
        if not isinstance(query, ItemQuery):
            raise InvalidDocumentError("query must be ItemQuery")
        query_digest = digest(
            {"name": query.name, "kinds": sorted(set(query.kinds)), "limit": query.limit}
        )
        after = ""
        if query.cursor is not None:
            if not isinstance(query.cursor, str):
                raise InvalidCursorError("cursor must be a string")
            try:
                payload = json.loads(base64.urlsafe_b64decode(query.cursor.encode("ascii")))
            except (ValueError, UnicodeError, binascii.Error) as exc:
                raise InvalidCursorError("invalid cursor") from exc
            if not isinstance(payload, dict):
                raise InvalidCursorError("invalid cursor payload")
            if payload != {
                "collection_id": self.collection_id,
                "graph_revision": self.graph_revision,
                "read_digest": self.digest,
                "query_digest": query_digest,
                "last_node_id": payload.get("last_node_id"),
            } or not isinstance(payload.get("last_node_id"), str):
                raise InvalidCursorError("cursor does not match snapshot and query")
            after = payload["last_node_id"]
        requested_name = normalize(query.name, self.name_normalization)
        items = tuple(
            node
            for node in self.nodes
            if node.node_id > after
            and (not query.kinds or node.kind in query.kinds)
            and (
                node.key == query.name
                or any(
                    normalize(alias, self.name_normalization) == requested_name
                    for alias in node.aliases
                )
            )
        )
        page = items[: query.limit]
        next_cursor = None
        if len(items) > query.limit:
            payload = {
                "collection_id": self.collection_id,
                "graph_revision": self.graph_revision,
                "read_digest": self.digest,
                "query_digest": query_digest,
                "last_node_id": page[-1].node_id,
            }
            next_cursor = base64.urlsafe_b64encode(canonical(payload).encode("utf-8")).decode(
                "ascii"
            )
        return ItemPage(page, next_cursor)

    def evidence_for(
        self, *, node_ids: tuple[str, ...] = (), edge_ids: tuple[str, ...] = ()
    ) -> EvidenceLookup:
        nodes = {node.node_id for node in self.nodes}
        edges = {edge.edge_id for edge in self.edges}

        def owner_evidence(owner: str) -> tuple[GraphEvidence, ...]:
            return tuple(ev for ev in self.evidence if ev.owner_id == owner)

        return EvidenceLookup(
            tuple(
                (owner, owner_evidence(owner)) for owner in sorted(set(node_ids)) if owner in nodes
            ),
            tuple(
                (owner, owner_evidence(owner)) for owner in sorted(set(edge_ids)) if owner in edges
            ),
            tuple(sorted(set(node_ids) - nodes)),
            tuple(sorted(set(edge_ids) - edges)),
        )

    def resolve_documents(self, document_ids: tuple[str, ...]) -> DocumentLookup:
        selected = {d.document_id: d for d in self.documents}
        return DocumentLookup(
            tuple(selected[d] for d in sorted(set(document_ids)) if d in selected),
            tuple(sorted(set(document_ids) - selected.keys())),
        )
