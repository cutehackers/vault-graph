from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Self, cast
from urllib.parse import quote

from .contracts import (
    Document,
    ExtractionProfile,
    Extractor,
    GraphLimits,
    ReadLimits,
    canonical,
    digest,
    valid_limit,
    valid_string,
)
from .errors import (
    CapacityError,
    ClosedStoreError,
    ExtractionFailedError,
    ExtractionResultConflictError,
    GraphDocumentError,
    IdentityConflictError,
    InvalidDocumentError,
    ProfileMismatchError,
    ReadOnlyOpenError,
    ReadOnlyStoreError,
    RevisionConflictError,
    SchemaMismatchError,
    SourceRevisionConflictError,
    StoreBusyError,
    StoreCorruptError,
    StoreWriteError,
    UnknownCollectionError,
    UnknownDocumentError,
)
from .extraction import RuleExtractor, extraction_digest, validate_extraction
from .querying import (
    DocumentGraphSnapshot,
    GraphCounts,
    GraphDocumentInfo,
    GraphEdge,
    GraphEvidence,
    GraphNode,
    UpdateResult,
)

SCHEMA = "graph-document-v1"


def _is_busy(exc: sqlite3.Error) -> bool:
    return getattr(exc, "sqlite_errorcode", None) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)


def _snapshot(
    collection_id: str,
    revision: int,
    profile: ExtractionProfile,
    rows: list[dict[str, Any]],
    selection: str | tuple[str, ...],
    limits: ReadLimits | None = None,
) -> DocumentGraphSnapshot:
    node_ident: dict[str, tuple[str, str]] = {}
    edge_ident: dict[str, tuple[str, str, str]] = {}
    labels: dict[str, set[str]] = {}
    direct_nodes: set[str] = set()
    edges: dict[str, GraphEdge] = {}
    evidences: dict[str, GraphEvidence] = {}
    documents: list[GraphDocumentInfo] = []

    def check_capacity() -> None:
        if limits is not None and (
            len(node_ident) > limits.max_nodes
            or len(edges) > limits.max_edges
            or len(evidences) > limits.max_evidence
        ):
            raise CapacityError("read exceeds graph limits")

    def node_id(kind: str, key: str) -> str:
        identifier = digest([1, collection_id, kind, key])
        identity = (kind, key)
        prior = node_ident.setdefault(identifier, identity)
        if prior != identity:
            raise IdentityConflictError("node identity collision")
        return identifier

    for row in rows:
        document_id = str(row["document_id"])
        source_revision = str(row["source_revision"])
        input_digest = str(row["input_digest"])
        source_locator = row["source_locator"]
        if source_locator is not None and not isinstance(source_locator, str):
            raise StoreCorruptError("invalid source locator")
        documents.append(
            GraphDocumentInfo(
                document_id,
                source_revision,
                input_digest,
                str(row["extraction_digest"]),
                source_locator,
            )
        )
        text = row.get("text")
        # Text is intentionally absent from the persisted contribution.
        if text is not None:
            raise StoreCorruptError("document text found in contribution")
        for fact in row["entities"]:
            key_data = fact["key"]
            owner = node_id(key_data["kind"], key_data["key"])
            direct_nodes.add(owner)
            labels.setdefault(owner, set()).update([fact["label"], *fact["aliases"]])
            _add_evidence(evidences, owner, fact["rule_id"], fact["locations"], row)
            check_capacity()
        for fact in row["relations"]:
            source = node_id(fact["source"]["kind"], fact["source"]["key"])
            target = node_id(fact["target"]["kind"], fact["target"]["key"])
            relation_type = fact["relation_type"]
            edge_id = digest([1, collection_id, relation_type, source, target])
            identity = (relation_type, source, target)
            prior = edge_ident.setdefault(edge_id, identity)
            if prior != identity:
                raise IdentityConflictError("edge identity collision")
            edges[edge_id] = GraphEdge(edge_id, source, target, relation_type)
            _add_evidence(evidences, edge_id, fact["rule_id"], fact["locations"], row)
            check_capacity()
    available = {doc.document_id for doc in documents}
    nodes = tuple(
        GraphNode(
            identifier,
            kind,
            key,
            min(labels.get(identifier, {key})),
            tuple(sorted(labels.get(identifier, {key}))),
            kind != "document" or key in available,
        )
        for identifier, (kind, key) in sorted(node_ident.items())
    )
    edge_values = tuple(edges[key] for key in sorted(edges))
    evidence_values = tuple(evidences[key] for key in sorted(evidences))
    docs = tuple(sorted(documents, key=lambda d: d.document_id))
    return _build_snapshot(
        collection_id, revision, profile, selection, nodes, edge_values, evidence_values, docs
    )


def _build_snapshot(
    collection_id: str,
    revision: int,
    profile: ExtractionProfile,
    selection: str | tuple[str, ...],
    nodes: tuple[GraphNode, ...],
    edge_values: tuple[GraphEdge, ...],
    evidence_values: tuple[GraphEvidence, ...],
    docs: tuple[GraphDocumentInfo, ...],
) -> DocumentGraphSnapshot:
    read_digest = digest(
        {
            "collection_id": collection_id,
            "graph_revision": revision,
            "profile_digest": profile.profile_digest,
            "selection": selection,
            "nodes": [asdict(n) for n in nodes],
            "edges": [asdict(e) for e in edge_values],
            "evidence": [asdict(e) for e in evidence_values],
            "documents": [asdict(d) for d in docs],
        }
    )
    return DocumentGraphSnapshot(
        collection_id,
        revision,
        profile.profile_digest,
        profile.name_normalization,
        selection,
        nodes,
        edge_values,
        evidence_values,
        docs,
        read_digest,
    )


def _add_evidence(
    target: dict[str, GraphEvidence],
    owner_id: str,
    rule_id: str,
    locations: list[dict[str, Any]],
    row: dict[str, Any],
) -> None:
    for loc in locations:
        span = loc["text_span"]
        if span is not None and (not isinstance(span, (list, tuple)) or len(span) != 2):
            raise StoreCorruptError("invalid stored span")
        evidence_id = digest(
            [
                row["document_id"],
                row["source_revision"],
                row["input_digest"],
                owner_id,
                loc["structural_id"],
                span,
                rule_id,
            ]
        )
        excerpts = row["excerpts"]
        item = excerpts[canonical(loc)]
        evidence = GraphEvidence(
            evidence_id,
            owner_id,
            str(row["document_id"]),
            str(row["source_revision"]),
            str(row["input_digest"]),
            str(loc["structural_id"]),
            tuple(span) if span is not None else None,
            rule_id,
            row["source_locator"],
            item["text"],
            item["truncated"],
        )
        prior = target.setdefault(evidence_id, evidence)
        if prior != evidence:
            raise IdentityConflictError("evidence identity collision")


class GraphDocument:
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        mode: str,
        limits: GraphLimits,
        profile: ExtractionProfile,
        extractor: Extractor,
    ) -> None:
        self._connection = connection
        self._mode = mode
        self._limits = limits
        self._profile = profile
        self._extractor = extractor
        self._closed = False

    @classmethod
    def open(
        cls,
        path: str | Path,
        *,
        mode: str,
        limits: GraphLimits,
        profile: ExtractionProfile,
        extractor: Extractor | None = None,
        max_excerpt_chars: int = 0,
        busy_timeout_ms: int = 5000,
    ) -> GraphDocument:
        if mode not in ("create", "read_write", "read_only"):
            raise InvalidDocumentError("unsupported open mode")
        if not isinstance(limits, GraphLimits) or not isinstance(profile, ExtractionProfile):
            raise InvalidDocumentError("limits and profile are required")
        valid_limit(busy_timeout_ms, "busy_timeout_ms", zero=True)
        valid_limit(max_excerpt_chars, "max_excerpt_chars", zero=True)
        if max_excerpt_chars != profile.max_excerpt_chars:
            raise InvalidDocumentError("max_excerpt_chars must match profile")
        db_path = Path(path)
        if not db_path.is_absolute() or str(db_path) == ":memory:":
            raise InvalidDocumentError("DB path must be absolute")
        if mode == "create" and (db_path.exists() or not db_path.parent.is_dir()):
            raise InvalidDocumentError("create needs an absent DB and existing parent")
        if mode != "create" and not db_path.is_file():
            raise (
                ReadOnlyOpenError("existing DB required")
                if mode == "read_only"
                else SchemaMismatchError("existing DB required")
            )
        uri = f"file:{quote(str(db_path), safe='/')}?mode={'ro' if mode == 'read_only' else 'rwc' if mode == 'create' else 'rw'}"
        try:
            connection = sqlite3.connect(
                uri,
                uri=True,
                isolation_level=None,
                timeout=busy_timeout_ms / 1000,
                check_same_thread=True,
            )
            connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            connection.execute("PRAGMA foreign_keys=ON")
            if mode == "create":
                connection.execute("PRAGMA journal_mode=DELETE")
                connection.execute("PRAGMA synchronous=FULL")
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE schema_info (version TEXT NOT NULL);
                    INSERT INTO schema_info VALUES ('graph-document-v1');
                    CREATE TABLE collections (
                        collection_id TEXT PRIMARY KEY,
                        graph_revision INTEGER NOT NULL,
                        profile_digest TEXT NOT NULL
                    );
                    CREATE TABLE documents (
                        collection_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source_revision TEXT NOT NULL,
                        input_digest TEXT NOT NULL,
                        extraction_digest TEXT NOT NULL,
                        source_locator TEXT,
                        PRIMARY KEY(collection_id, document_id),
                        FOREIGN KEY(collection_id) REFERENCES collections(collection_id) ON DELETE CASCADE
                    );
                    CREATE TABLE contributions (
                        collection_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source_revision TEXT NOT NULL,
                        input_digest TEXT NOT NULL,
                        extraction_digest TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        PRIMARY KEY(collection_id, document_id),
                        FOREIGN KEY(collection_id, document_id)
                            REFERENCES documents(collection_id, document_id) ON DELETE CASCADE
                    );
                    CREATE TABLE node_contributions (
                        collection_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        entity_key TEXT NOT NULL,
                        aliases_json TEXT NOT NULL,
                        PRIMARY KEY(collection_id, document_id, node_id),
                        FOREIGN KEY(collection_id, document_id)
                            REFERENCES documents(collection_id, document_id) ON DELETE CASCADE
                    );
                    CREATE TABLE edge_contributions (
                        collection_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        source_node_id TEXT NOT NULL,
                        target_node_id TEXT NOT NULL,
                        relation_type TEXT NOT NULL,
                        PRIMARY KEY(collection_id, document_id, edge_id),
                        FOREIGN KEY(collection_id, document_id)
                            REFERENCES documents(collection_id, document_id) ON DELETE CASCADE
                    );
                    CREATE TABLE nodes (
                        collection_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        entity_key TEXT NOT NULL,
                        label TEXT NOT NULL,
                        aliases_json TEXT NOT NULL,
                        PRIMARY KEY(collection_id, node_id),
                        FOREIGN KEY(collection_id) REFERENCES collections(collection_id) ON DELETE CASCADE
                    );
                    CREATE TABLE edges (
                        collection_id TEXT NOT NULL,
                        edge_id TEXT NOT NULL,
                        source_node_id TEXT NOT NULL,
                        target_node_id TEXT NOT NULL,
                        relation_type TEXT NOT NULL,
                        PRIMARY KEY(collection_id, edge_id),
                        FOREIGN KEY(collection_id, source_node_id)
                            REFERENCES nodes(collection_id, node_id),
                        FOREIGN KEY(collection_id, target_node_id)
                            REFERENCES nodes(collection_id, node_id)
                    );
                    CREATE TABLE evidence (
                        collection_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        evidence_id TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        source_revision TEXT NOT NULL,
                        input_digest TEXT NOT NULL,
                        structural_id TEXT NOT NULL,
                        span_start INTEGER,
                        span_end INTEGER,
                        rule_id TEXT NOT NULL,
                        source_locator TEXT,
                        excerpt TEXT,
                        excerpt_truncated INTEGER NOT NULL,
                        PRIMARY KEY(collection_id, document_id, evidence_id),
                        FOREIGN KEY(collection_id, document_id)
                            REFERENCES documents(collection_id, document_id) ON DELETE CASCADE
                    );
                    COMMIT;
                """)
            else:
                try:
                    row = connection.execute("SELECT version FROM schema_info").fetchone()
                except sqlite3.DatabaseError as exc:
                    raise SchemaMismatchError("schema_info is missing or invalid") from exc
                if row != (SCHEMA,):
                    raise SchemaMismatchError("unsupported graph_document schema")
                journal = connection.execute("PRAGMA journal_mode").fetchone()
                if journal != ("delete",):
                    raise SchemaMismatchError("unsupported SQLite journal mode")
                if mode == "read_write":
                    connection.execute("PRAGMA synchronous=FULL")
                required_columns = {
                    "schema_info": {"version"},
                    "collections": {"collection_id", "graph_revision", "profile_digest"},
                    "documents": {
                        "collection_id",
                        "document_id",
                        "source_revision",
                        "input_digest",
                        "extraction_digest",
                        "source_locator",
                    },
                    "contributions": {
                        "collection_id",
                        "document_id",
                        "source_revision",
                        "input_digest",
                        "extraction_digest",
                        "payload",
                    },
                    "node_contributions": {
                        "collection_id",
                        "document_id",
                        "node_id",
                        "kind",
                        "entity_key",
                        "aliases_json",
                    },
                    "edge_contributions": {
                        "collection_id",
                        "document_id",
                        "edge_id",
                        "source_node_id",
                        "target_node_id",
                        "relation_type",
                    },
                    "nodes": {
                        "collection_id",
                        "node_id",
                        "kind",
                        "entity_key",
                        "label",
                        "aliases_json",
                    },
                    "edges": {
                        "collection_id",
                        "edge_id",
                        "source_node_id",
                        "target_node_id",
                        "relation_type",
                    },
                    "evidence": {
                        "collection_id",
                        "document_id",
                        "evidence_id",
                        "owner_id",
                        "source_revision",
                        "input_digest",
                        "structural_id",
                        "span_start",
                        "span_end",
                        "rule_id",
                        "source_locator",
                        "excerpt",
                        "excerpt_truncated",
                    },
                }
                for table, columns in required_columns.items():
                    actual = {
                        column[1] for column in connection.execute(f"PRAGMA table_info({table})")
                    }
                    if actual != columns:
                        raise SchemaMismatchError(f"unsupported {table} table")
                check = connection.execute("PRAGMA integrity_check").fetchone()
                if check != ("ok",):
                    raise StoreCorruptError("DB integrity check failed")
                if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise StoreCorruptError("DB foreign key check failed")
            return cls(
                connection,
                mode=mode,
                limits=limits,
                profile=profile,
                extractor=extractor or RuleExtractor(),
            )
        except (SchemaMismatchError, StoreCorruptError):
            connection.close()
            raise
        except sqlite3.Error as exc:
            if "connection" in locals():
                connection.close()
            if _is_busy(exc):
                raise StoreBusyError("DB busy") from exc
            if mode == "read_only":
                raise ReadOnlyOpenError("read-only open failed") from exc
            raise SchemaMismatchError("DB open failed") from exc

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._connection.close()
            self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise ClosedStoreError("store closed")

    def _ensure_write(self) -> None:
        self._ensure_open()
        if self._mode == "read_only":
            raise ReadOnlyStoreError("read-only store")

    def _collection(self, collection_id: str) -> tuple[int, str] | None:
        row = self._connection.execute(
            "SELECT graph_revision, profile_digest FROM collections WHERE collection_id=?",
            (collection_id,),
        ).fetchone()
        return (int(row[0]), str(row[1])) if row else None

    def _rows(self, collection_id: str, ids: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        columns = "c.document_id, c.source_revision, c.input_digest, c.extraction_digest, c.payload"
        if ids is None:
            records = self._connection.execute(
                f"SELECT {columns} FROM contributions AS c WHERE c.collection_id=? ORDER BY c.document_id",
                (collection_id,),
            ).fetchall()
        else:
            records = [
                row
                for document_id in ids
                for row in self._connection.execute(
                    f"SELECT {columns} FROM contributions AS c WHERE c.collection_id=? AND c.document_id=?",
                    (collection_id, document_id),
                ).fetchall()
            ]
        try:
            parsed = []
            for record in records:
                payload = json.loads(record[4])
                if any(
                    payload[name] != record[index]
                    for index, name in enumerate(
                        ("document_id", "source_revision", "input_digest", "extraction_digest")
                    )
                ):
                    raise StoreCorruptError("contribution metadata differs from indexed columns")
                parsed.append(payload)
            return parsed
        except (ValueError, TypeError, KeyError) as exc:
            raise StoreCorruptError("invalid contribution payload") from exc

    def _write_document_projection(
        self, collection_id: str, revision: int, row: dict[str, Any]
    ) -> None:
        document_id = row["document_id"]
        self._connection.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?)",
            (
                collection_id,
                document_id,
                row["source_revision"],
                row["input_digest"],
                row["extraction_digest"],
                row["source_locator"],
            ),
        )
        self._connection.execute(
            "INSERT INTO contributions VALUES (?,?,?,?,?,?)",
            (
                collection_id,
                document_id,
                row["source_revision"],
                row["input_digest"],
                row["extraction_digest"],
                canonical(row),
            ),
        )
        projection = _snapshot(collection_id, revision, self._profile, [row], (document_id,))
        self._connection.executemany(
            "INSERT INTO node_contributions VALUES (?,?,?,?,?,?)",
            (
                (
                    collection_id,
                    document_id,
                    node.node_id,
                    node.kind,
                    node.key,
                    canonical(node.aliases),
                )
                for node in projection.nodes
            ),
        )
        self._connection.executemany(
            "INSERT INTO edge_contributions VALUES (?,?,?,?,?,?)",
            (
                (
                    collection_id,
                    document_id,
                    edge.edge_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.relation_type,
                )
                for edge in projection.edges
            ),
        )
        self._connection.executemany(
            "INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                (
                    collection_id,
                    document_id,
                    item.evidence_id,
                    item.owner_id,
                    item.source_revision,
                    item.input_digest,
                    item.structural_id,
                    item.text_span[0] if item.text_span else None,
                    item.text_span[1] if item.text_span else None,
                    item.rule_id,
                    item.source_locator,
                    item.excerpt,
                    int(item.excerpt_truncated),
                )
                for item in projection.evidence
            ),
        )

    def _write_collection_projection(self, snapshot: DocumentGraphSnapshot) -> None:
        collection_id = snapshot.collection_id
        self._connection.execute("DELETE FROM edges WHERE collection_id=?", (collection_id,))
        self._connection.execute("DELETE FROM nodes WHERE collection_id=?", (collection_id,))
        self._connection.executemany(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?)",
            (
                (
                    collection_id,
                    node.node_id,
                    node.kind,
                    node.key,
                    node.label,
                    canonical(node.aliases),
                )
                for node in snapshot.nodes
            ),
        )
        self._connection.executemany(
            "INSERT INTO edges VALUES (?,?,?,?,?)",
            (
                (
                    collection_id,
                    edge.edge_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.relation_type,
                )
                for edge in snapshot.edges
            ),
        )

    def _selected_rows(
        self, table: str, collection_id: str, ids: tuple[str, ...] | None
    ) -> list[tuple[Any, ...]]:
        if ids is None:
            return self._connection.execute(
                f"SELECT * FROM {table} WHERE collection_id=?", (collection_id,)
            ).fetchall()
        return [
            row
            for document_id in ids
            for row in self._connection.execute(
                f"SELECT * FROM {table} WHERE collection_id=? AND document_id=?",
                (collection_id, document_id),
            ).fetchall()
        ]

    def _read_materialized(
        self,
        collection_id: str,
        revision: int,
        selection: str | tuple[str, ...],
        limits: ReadLimits,
    ) -> DocumentGraphSnapshot:
        ids: tuple[str, ...] | None = (
            None if selection == "all" else cast(tuple[str, ...], selection)
        )
        documents = tuple(
            sorted(
                (
                    GraphDocumentInfo(row[1], row[2], row[3], row[4], row[5])
                    for row in self._selected_rows("documents", collection_id, ids)
                ),
                key=lambda item: item.document_id,
            )
        )
        if len(documents) > limits.max_documents:
            raise CapacityError("read exceeds document limit")
        available = {document.document_id for document in documents}
        labels: dict[str, set[str]] = {}
        identities: dict[str, tuple[str, str]] = {}
        node_table = "nodes" if ids is None else "node_contributions"
        for row in self._selected_rows(node_table, collection_id, ids):
            node_id, kind, key, aliases_json = (
                (row[1], row[2], row[3], row[5])
                if ids is None
                else (row[2], row[3], row[4], row[5])
            )
            if digest([1, collection_id, kind, key]) != node_id:
                raise StoreCorruptError("invalid stored node ID")
            prior = identities.setdefault(node_id, (kind, key))
            if prior != (kind, key):
                raise IdentityConflictError("stored node identity collision")
            names = json.loads(aliases_json)
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise StoreCorruptError("invalid stored aliases")
            labels.setdefault(node_id, set()).update(names)
            if len(identities) > limits.max_nodes:
                raise CapacityError("read exceeds node limit")
        nodes = tuple(
            GraphNode(
                node_id,
                kind,
                key,
                min(labels[node_id] or {key}),
                tuple(sorted(labels[node_id] or {key})),
                kind != "document" or key in available,
            )
            for node_id, (kind, key) in sorted(identities.items())
        )
        edges: dict[str, GraphEdge] = {}
        edge_table = "edges" if ids is None else "edge_contributions"
        for row in self._selected_rows(edge_table, collection_id, ids):
            edge_id, source, target, relation = (
                (row[1], row[2], row[3], row[4])
                if ids is None
                else (row[2], row[3], row[4], row[5])
            )
            if digest([1, collection_id, relation, source, target]) != edge_id:
                raise StoreCorruptError("invalid stored edge ID")
            if source not in identities or target not in identities:
                raise StoreCorruptError("stored edge endpoint missing")
            edge = GraphEdge(edge_id, source, target, relation)
            prior_edge = edges.setdefault(edge_id, edge)
            if prior_edge != edge:
                raise IdentityConflictError("stored edge identity collision")
            if len(edges) > limits.max_edges:
                raise CapacityError("read exceeds edge limit")
        evidence: dict[str, GraphEvidence] = {}
        owners = set(identities) | set(edges)
        document_info = {document.document_id: document for document in documents}
        for row in self._selected_rows("evidence", collection_id, ids):
            span = (row[7], row[8]) if row[7] is not None else None
            item = GraphEvidence(
                row[2],
                row[3],
                row[1],
                row[4],
                row[5],
                row[6],
                span,
                row[9],
                row[10],
                row[11],
                bool(row[12]),
            )
            document = document_info.get(item.document_id)
            if document is None or (
                item.source_revision,
                item.input_digest,
                item.source_locator,
            ) != (document.source_revision, document.input_digest, document.source_locator):
                raise StoreCorruptError("evidence metadata differs from document")
            if (
                item.owner_id not in owners
                or digest(
                    [
                        item.document_id,
                        item.source_revision,
                        item.input_digest,
                        item.owner_id,
                        item.structural_id,
                        span,
                        item.rule_id,
                    ]
                )
                != item.evidence_id
            ):
                raise StoreCorruptError("invalid stored evidence")
            prior_evidence = evidence.setdefault(item.evidence_id, item)
            if prior_evidence != item:
                raise IdentityConflictError("stored evidence identity collision")
            if len(evidence) > limits.max_evidence:
                raise CapacityError("read exceeds evidence limit")
        return _build_snapshot(
            collection_id,
            revision,
            self._profile,
            selection,
            nodes,
            tuple(edges[key] for key in sorted(edges)),
            tuple(evidence[key] for key in sorted(evidence)),
            documents,
        )

    def update_documents(
        self, documents: tuple[Document, ...], *, collection_id: str, expected_revision: int
    ) -> UpdateResult:
        self._ensure_write()
        valid_string(collection_id, "collection_id")
        if len(collection_id.encode("utf-8")) > self._limits.max_id_utf8_bytes:
            raise CapacityError("collection ID exceeds limit")
        valid_limit(expected_revision, "expected_revision", zero=True)
        if (
            not isinstance(documents, tuple)
            or not documents
            or len(documents) > self._limits.max_batch_documents
        ):
            raise CapacityError("batch size exceeds limit or is empty")
        if any(not isinstance(doc, Document) for doc in documents):
            raise InvalidDocumentError("batch must contain Document values")
        if len({d.document_id for d in documents}) != len(documents):
            raise InvalidDocumentError("duplicate document_id in batch")
        total_bytes = 0
        prepared: list[dict[str, Any]] = []
        for doc in documents:
            if len(doc.document_id.encode("utf-8")) > self._limits.max_id_utf8_bytes:
                raise CapacityError("document ID exceeds limit")
            size = len(canonical(asdict(doc)).encode("utf-8"))
            total_bytes += size
            if (
                size > self._limits.max_document_utf8_bytes
                or total_bytes > self._limits.max_batch_utf8_bytes
            ):
                raise CapacityError("document byte size exceeds limit")
            try:
                extracted = self._extractor.extract(doc, profile=self._profile)
            except Exception as exc:
                raise ExtractionFailedError("extractor failed") from exc
            validate_extraction(doc, extracted, self._profile)
            excerpts: dict[str, dict[str, Any]] = {}
            for loc in extracted.evidence:
                excerpt = doc.text[loc.text_span[0] : loc.text_span[1]] if loc.text_span else None
                limit = self._profile.max_excerpt_chars
                excerpts[canonical(asdict(loc))] = {
                    "text": excerpt[:limit] if excerpt is not None and limit else None,
                    "truncated": excerpt is not None and limit > 0 and len(excerpt) > limit,
                }
            for fact in extracted.entities:
                for identifier in (fact.key.kind, fact.key.key, fact.rule_id):
                    if len(identifier.encode("utf-8")) > self._limits.max_id_utf8_bytes:
                        raise CapacityError("entity ID exceeds limit")
            for relation_fact in extracted.relations:
                for identifier in (
                    relation_fact.source.kind,
                    relation_fact.source.key,
                    relation_fact.target.kind,
                    relation_fact.target.key,
                    relation_fact.relation_type,
                    relation_fact.rule_id,
                ):
                    if len(identifier.encode("utf-8")) > self._limits.max_id_utf8_bytes:
                        raise CapacityError("relation ID exceeds limit")
            prepared.append(
                {
                    "document_id": doc.document_id,
                    "source_revision": doc.source_revision,
                    "input_digest": doc.input_digest,
                    "extraction_digest": extraction_digest(extracted),
                    "source_locator": doc.source_locator,
                    "entities": [asdict(x) for x in extracted.entities],
                    "relations": [asdict(x) for x in extracted.relations],
                    "excerpts": excerpts,
                    "warnings": list(extracted.warnings),
                }
            )
        prepared = [json.loads(canonical(row)) for row in prepared]
        output_bytes = sum(len(canonical(row).encode("utf-8")) for row in prepared)
        if output_bytes > self._limits.max_batch_utf8_bytes or any(
            len(canonical(row).encode("utf-8")) > self._limits.max_document_utf8_bytes
            for row in prepared
        ):
            raise CapacityError("extraction output exceeds byte limit")
        return self._apply(collection_id, expected_revision, prepared, ())

    def remove_documents(
        self, document_ids: tuple[str, ...], *, collection_id: str, expected_revision: int
    ) -> UpdateResult:
        self._ensure_write()
        valid_string(collection_id, "collection_id")
        if len(collection_id.encode("utf-8")) > self._limits.max_id_utf8_bytes:
            raise CapacityError("collection ID exceeds limit")
        valid_limit(expected_revision, "expected_revision", zero=True)
        if not isinstance(document_ids, tuple) or not document_ids:
            raise InvalidDocumentError("document_ids must be a nonempty tuple")
        for doc_id in document_ids:
            valid_string(doc_id, "document_id")
        if len(set(document_ids)) != len(document_ids):
            raise InvalidDocumentError("duplicate document_id")
        return self._apply(collection_id, expected_revision, [], document_ids)

    def _apply(
        self,
        collection_id: str,
        expected_revision: int,
        prepared: list[dict[str, Any]],
        removals: tuple[str, ...],
    ) -> UpdateResult:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            current = self._collection(collection_id)
            if current is None and removals:
                raise UnknownCollectionError("unknown collection")
            revision = current[0] if current else 0
            if revision != expected_revision:
                raise RevisionConflictError(revision)
            if current and current[1] != self._profile.profile_digest:
                raise ProfileMismatchError("collection profile differs")
            old = (
                {str(row["document_id"]): row for row in self._rows(collection_id)}
                if current
                else {}
            )
            new = old.copy()
            changed: list[str] = []
            removed: list[str] = []
            for row in prepared:
                doc_id = str(row["document_id"])
                prior = old.get(doc_id)
                if (
                    prior
                    and prior["source_revision"] == row["source_revision"]
                    and prior["input_digest"] != row["input_digest"]
                ):
                    raise SourceRevisionConflictError("same source revision has different input")
                if (
                    prior
                    and prior["input_digest"] == row["input_digest"]
                    and prior["extraction_digest"] != row["extraction_digest"]
                ):
                    raise ExtractionResultConflictError("same input has different extraction")
                if prior != row:
                    changed.append(doc_id)
                    new[doc_id] = row
            for doc_id in removals:
                if doc_id in new:
                    removed.append(doc_id)
                    del new[doc_id]
            next_revision = revision + bool(changed or removed)
            snapshot = _snapshot(
                collection_id, next_revision, self._profile, list(new.values()), "all"
            )
            counts = GraphCounts(len(snapshot.nodes), len(snapshot.edges), len(snapshot.evidence))
            if (
                counts.nodes > self._limits.max_nodes
                or counts.edges > self._limits.max_edges
                or counts.evidence > self._limits.max_evidence
            ):
                raise CapacityError("collection exceeds graph limits")
            if changed or removed:
                if current is None:
                    self._connection.execute(
                        "INSERT INTO collections VALUES (?,?,?)",
                        (collection_id, next_revision, self._profile.profile_digest),
                    )
                else:
                    self._connection.execute(
                        "UPDATE collections SET graph_revision=? WHERE collection_id=?",
                        (next_revision, collection_id),
                    )
                for doc_id in sorted((*changed, *removed)):
                    self._connection.execute(
                        "DELETE FROM documents WHERE collection_id=? AND document_id=?",
                        (collection_id, doc_id),
                    )
                for doc_id in sorted(changed):
                    self._write_document_projection(collection_id, next_revision, new[doc_id])
                self._write_collection_projection(snapshot)
            self._connection.execute("COMMIT")
            warnings = tuple(sorted({str(w) for row in prepared for w in row["warnings"]}))
            return UpdateResult(
                collection_id,
                revision,
                next_revision,
                tuple(sorted(changed)),
                tuple(sorted(removed)),
                counts,
                warnings,
            )
        except sqlite3.Error as exc:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if _is_busy(exc):
                raise StoreBusyError("DB busy") from exc
            raise StoreWriteError("DB write failed") from exc
        except GraphDocumentError:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        except Exception as exc:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise StoreCorruptError("invalid stored contribution") from exc

    def read(
        self, *, collection_id: str, selection: str | tuple[str, ...], limits: ReadLimits
    ) -> DocumentGraphSnapshot:
        self._ensure_open()
        valid_string(collection_id, "collection_id")
        if not isinstance(limits, ReadLimits):
            raise InvalidDocumentError("read limits required")
        if selection != "all" and not isinstance(selection, tuple):
            raise InvalidDocumentError("selection must be all or unique document IDs")
        if isinstance(selection, tuple):
            for document_id in selection:
                valid_string(document_id, "selection document_id")
            if len(set(selection)) != len(selection):
                raise InvalidDocumentError("selection document IDs must be unique")
            if len(selection) > limits.max_documents:
                raise CapacityError("read exceeds document limit")
        try:
            self._connection.execute("BEGIN")
            current = self._collection(collection_id)
            if current is None:
                raise UnknownCollectionError("unknown collection")
            if current[1] != self._profile.profile_digest:
                raise ProfileMismatchError("collection profile differs")
            ids: tuple[str, ...] | None = (
                None if selection == "all" else cast(tuple[str, ...], selection)
            )
            if ids is None:
                count = self._connection.execute(
                    "SELECT COUNT(*) FROM contributions WHERE collection_id=?", (collection_id,)
                ).fetchone()[0]
                if count > limits.max_documents:
                    raise CapacityError("read exceeds document limit")
            rows = self._rows(collection_id, ids)
            if ids is not None and set(ids) - {str(row["document_id"]) for row in rows}:
                raise UnknownDocumentError("selection includes an unknown document")
            snapshot = self._read_materialized(
                collection_id,
                current[0],
                "all" if ids is None else tuple(sorted(ids)),
                limits,
            )
            payload_docs = {
                row["document_id"]: (
                    row["source_revision"],
                    row["input_digest"],
                    row["extraction_digest"],
                    row["source_locator"],
                )
                for row in rows
            }
            if payload_docs != {
                doc.document_id: (
                    doc.source_revision,
                    doc.input_digest,
                    doc.extraction_digest,
                    doc.source_locator,
                )
                for doc in snapshot.documents
            }:
                raise StoreCorruptError("document metadata differs from contributions")
            expected_snapshot = _snapshot(
                collection_id, current[0], self._profile, rows, snapshot.selection, limits
            )
            if snapshot.digest != expected_snapshot.digest:
                raise StoreCorruptError("materialized graph differs from document contributions")
            if (
                len(snapshot.nodes) > limits.max_nodes
                or len(snapshot.edges) > limits.max_edges
                or len(snapshot.evidence) > limits.max_evidence
                or len(snapshot.documents) > limits.max_documents
                or len(
                    canonical(
                        {
                            "nodes": [asdict(x) for x in snapshot.nodes],
                            "edges": [asdict(x) for x in snapshot.edges],
                            "evidence": [asdict(x) for x in snapshot.evidence],
                            "documents": [asdict(x) for x in snapshot.documents],
                        }
                    ).encode("utf-8")
                )
                > limits.max_serialized_utf8_bytes
            ):
                raise CapacityError("read exceeds limits")
            self._connection.execute("COMMIT")
            return snapshot
        except sqlite3.Error as exc:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            if _is_busy(exc):
                raise StoreBusyError("DB busy") from exc
            raise StoreCorruptError("DB read failed") from exc
        except GraphDocumentError:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        except Exception as exc:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise StoreCorruptError("invalid stored contribution") from exc
