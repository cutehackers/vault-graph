"""Shadow bridge from Vault graph occurrences to the independent document graph.

The legacy metadata store remains authoritative. A revision is readable through
this bridge only when its complete occurrence manifest has been published.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from graph_document import (
    Document,
    DocumentFeatures,
    DocumentGraphSnapshot,
    EntityFact,
    EntityKey,
    EvidenceLocation,
    ExtractedDocument,
    ExtractionProfile,
    GraphDocument,
    GraphLimits,
    LocatedValue,
    ReadLimits,
    RelationFact,
    UnknownCollectionError,
    extraction_digest,
)

from vault_graph.indexing.extraction.entity_extractor import DeterministicEntityExtractor
from vault_graph.indexing.extraction.graph_occurrences import (
    EntityOccurrence,
    RelationshipOccurrence,
    entity_occurrence_key,
)
from vault_graph.indexing.extraction.graph_source_store import GraphExtractionContext, MetadataGraphSourceStore
from vault_graph.indexing.extraction.relationship_extractor import DeterministicRelationshipExtractor
from vault_graph.indexing.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.operation.scope.vault_catalog import QueryScope
from vault_graph.retrieval.graph.graph_contracts import (
    GraphEvidenceRef,
    GraphExtractionSpec,
    current_graph_extraction_spec,
)
from vault_graph.retrieval.graph.graph_identity import stable_entity_id, stable_evidence_ref_id, stable_relationship_id
from vault_graph.retrieval.graph.projection.graph_projection import (
    GraphProjectionDirection,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
)
from vault_graph.storage.interfaces.metadata_store import MetadataStore

_RELATION_TYPES = (
    "mentions",
    "links_to",
    "related_to",
    "depends_on",
    "blocks",
    "implements",
    "supersedes",
    "revisit_when",
)


class VaultDocumentMappingError(RuntimeError):
    """The shadow revision cannot safely restore legacy identity or evidence."""


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _encoded(*parts: str) -> str:
    return _canonical(parts)


def _entity_key(key: tuple[str, str, str, str]) -> EntityKey:
    return EntityKey("legacy", _encoded(*key))


@dataclass(frozen=True)
class VaultDocumentContribution:
    document: Document
    source: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    entity_occurrences: tuple[EntityOccurrence, ...]
    relationship_occurrences: tuple[RelationshipOccurrence, ...]


@dataclass(frozen=True)
class VaultDocumentBatch:
    collection_id: str
    scope: QueryScope
    documents: tuple[VaultDocumentContribution, ...]
    complete_inventory: bool


@dataclass(frozen=True)
class VaultSyncResult:
    collection_id: str
    graph_revision: int
    changed_document_ids: tuple[str, ...]
    removed_document_ids: tuple[str, ...]
    ready: bool


@dataclass(frozen=True)
class RestoredGraph:
    collection_id: str
    graph_revision: int
    nodes: tuple[GraphProjectionNode, ...]
    relationships: tuple[GraphProjectionEdge, ...]
    evidence_refs: tuple[GraphEvidenceRef, ...]
    read_digest: str


@dataclass(frozen=True)
class VaultProjectionRequest:
    collection_id: str
    selection: str | tuple[str, ...]
    seed_entity_ids: tuple[str, ...]
    actual_scope_keys: tuple[str, ...]
    max_depth: int
    direction: GraphProjectionDirection
    relationship_types: tuple[str, ...]
    statuses: tuple[str, ...]
    include_cross_vault: bool
    limit: int
    edge_limit: int
    source_graph_revisions: tuple[str, ...]
    relationship_revisions: tuple[tuple[str, str, str], ...]


class _LegacyV1Extractor:
    def __init__(self, contributions: tuple[VaultDocumentContribution, ...]) -> None:
        self._by_id = {item.document.document_id: item for item in contributions}

    def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
        item = self._by_id[document.document_id]
        if item.document.input_digest != document.input_digest:
            raise VaultDocumentMappingError("Document changed after materialization.")
        identity = EntityKey("document", document.document_id)
        document_location = EvidenceLocation("document")
        facts: list[EntityFact] = [EntityFact(identity, document.title, (), "document", (document_location,))]
        locations = [document_location]
        entity_keys: set[EntityKey] = set()
        for index, entity_occurrence in enumerate(item.entity_occurrences):
            location = EvidenceLocation(f"e:{index}")
            key = _entity_key(entity_occurrence_key(entity_occurrence))
            entity_keys.add(key)
            facts.append(
                EntityFact(
                    key,
                    entity_occurrence.name,
                    entity_occurrence.aliases,
                    entity_occurrence.extraction_method,
                    (location,),
                )
            )
            locations.append(location)
        relations: list[RelationFact] = []
        for index, relationship_occurrence in enumerate(item.relationship_occurrences):
            source = _entity_key(relationship_occurrence.source_entity_key)
            target = _entity_key(relationship_occurrence.target_entity_key)
            if (
                relationship_occurrence.source_vault_id != relationship_occurrence.target_vault_id
                or source not in entity_keys
                or target not in entity_keys
            ):
                continue
            location = EvidenceLocation(f"r:{index}")
            relations.append(
                RelationFact(
                    source,
                    target,
                    relationship_occurrence.relationship_type,
                    relationship_occurrence.extraction_method,
                    (location,),
                )
            )
            locations.append(location)
        return ExtractedDocument(
            document.document_id,
            document.input_digest,
            profile.profile_digest,
            tuple(facts),
            tuple(relations),
            tuple(locations),
        )


class VaultGraphDocumentAdapter:
    """Materialize full Vault documents and publish revision-bound mappings."""

    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        db_path: Path,
        manifest_dir: Path,
        graph_limits: GraphLimits,
        read_limits: ReadLimits,
        spec: GraphExtractionSpec | None = None,
    ) -> None:
        if not db_path.is_absolute() or not manifest_dir.is_absolute():
            raise ValueError("Shadow paths must be absolute.")
        self._metadata_store = metadata_store
        self._db_path = db_path
        self._manifest_dir = manifest_dir
        self._graph_limits = graph_limits
        self._read_limits = read_limits
        self._spec = spec or current_graph_extraction_spec()
        self._profile = ExtractionProfile(
            profile_id="legacy-v1",
            extractor_fingerprint=f"vault-graph:{self._spec.spec_digest}",
            name_normalization="identity_v1",
            allowed_kinds=("document", "legacy"),
            allowed_relation_types=_RELATION_TYPES,
            max_excerpt_chars=0,
        )

    def materialize_documents(self, actual_scope: QueryScope) -> VaultDocumentBatch:
        """Read the complete scope inventory before accepting any deletion."""
        if len(actual_scope.vault_ids) != 1:
            raise VaultDocumentMappingError("Expected a per-Vault actual scope.")
        documents = self._metadata_store.list_documents(actual_scope)
        scoped_chunks = self._metadata_store.list_chunks(actual_scope)
        if len({(doc.vault_id, doc.document_id) for doc in documents}) != len(documents):
            raise VaultDocumentMappingError("Duplicate source document.")
        source_store = MetadataGraphSourceStore(self._metadata_store)
        backed_ids = {(chunk.vault_id, chunk.document_id) for chunk in scoped_chunks}
        context = GraphExtractionContext(
            scope=actual_scope,
            current_documents=tuple(doc for doc in documents if (doc.vault_id, doc.document_id) in backed_ids),
            source_store=source_store,
        )
        entity_extractor = DeterministicEntityExtractor()
        relationship_extractor = DeterministicRelationshipExtractor()
        contributions: list[VaultDocumentContribution] = []
        for source in sorted(documents, key=lambda item: (item.vault_id, item.path, item.document_id)):
            if source.vault_id not in actual_scope.vault_ids:
                raise VaultDocumentMappingError("Document outside requested scope.")
            chunks = tuple(
                sorted(
                    self._metadata_store.list_document_chunks(vault_id=source.vault_id, document_id=source.document_id),
                    key=lambda item: (item.document_order, item.chunk_id),
                )
            )
            if any(chunk.document_id != source.document_id or chunk.vault_id != source.vault_id for chunk in chunks):
                raise VaultDocumentMappingError("Incomplete or mixed document chunks.")
            if any(chunk.path != source.path or chunk.index_revision != source.index_revision for chunk in chunks):
                raise VaultDocumentMappingError("Document and chunk path or revision differ.")
            expected_chunks = tuple(
                sorted(
                    (
                        chunk
                        for chunk in scoped_chunks
                        if chunk.vault_id == source.vault_id and chunk.document_id == source.document_id
                    ),
                    key=lambda item: (item.document_order, item.chunk_id),
                )
            )
            if chunks != expected_chunks:
                raise VaultDocumentMappingError("Scope and document chunk snapshots differ.")
            entities: list[EntityOccurrence] = []
            relationships: list[RelationshipOccurrence] = []
            for chunk in chunks:
                extracted = entity_extractor.extract(
                    chunk=chunk, document=source, context=context, scope=actual_scope, spec=self._spec
                )
                entities.extend(extracted)
                relationships.extend(
                    relationship_extractor.extract(
                        chunk=chunk,
                        document=source,
                        entities=extracted,
                        context=context,
                        scope=actual_scope,
                        spec=self._spec,
                    )
                )
            source_revision = _digest(
                {
                    "source": {
                        key: value
                        for key, value in asdict(source).items()
                        if key not in {"last_seen_at", "last_indexed_at"}
                    },
                    "chunks": [asdict(chunk) for chunk in chunks],
                }
            )
            document = Document(
                document_id=_encoded(source.vault_id, source.document_id),
                source_revision=source_revision,
                title=source.path,
                text="\n".join(chunk.text for chunk in chunks),
                features=DocumentFeatures(
                    tags=tuple(
                        LocatedValue(f"e:{index}", EvidenceLocation(f"e:{index}")) for index in range(len(entities))
                    )
                    + tuple(
                        LocatedValue(f"r:{index}", EvidenceLocation(f"r:{index}"))
                        for index in range(len(relationships))
                    )
                ),
                source_locator=source.path,
            )
            contributions.append(
                VaultDocumentContribution(document, source, chunks, tuple(entities), tuple(relationships))
            )
        if documents != self._metadata_store.list_documents(
            actual_scope
        ) or scoped_chunks != self._metadata_store.list_chunks(actual_scope):
            raise VaultDocumentMappingError("Source inventory changed during materialization.")
        collection_id = _encoded(
            actual_scope.vault_ids[0],
            _canonical(tuple(sorted(actual_scope.content_scopes))),
            str(actual_scope.include_cross_vault),
            self._profile.profile_digest,
        )
        return VaultDocumentBatch(collection_id, actual_scope, tuple(contributions), True)

    def sync(self, batch: VaultDocumentBatch, expected_revision: int) -> VaultSyncResult:
        """Apply changed contributions, then publish a full immutable manifest."""
        if not batch.complete_inventory:
            raise VaultDocumentMappingError("Deletion requires a complete document inventory.")
        if len({item.document.document_id for item in batch.documents}) != len(batch.documents):
            raise VaultDocumentMappingError("Duplicate encoded document ID.")
        source_documents = tuple(
            sorted(
                (item.source for item in batch.documents), key=lambda item: (item.vault_id, item.path, item.document_id)
            )
        )
        current_documents = tuple(
            sorted(
                self._metadata_store.list_documents(batch.scope),
                key=lambda item: (item.vault_id, item.path, item.document_id),
            )
        )
        source_chunks = tuple(
            sorted(
                (chunk for item in batch.documents for chunk in item.chunks),
                key=lambda item: (item.vault_id, item.document_id, item.document_order, item.chunk_id),
            )
        )
        current_chunks = tuple(
            sorted(
                self._metadata_store.list_chunks(batch.scope),
                key=lambda item: (item.vault_id, item.document_id, item.document_order, item.chunk_id),
            )
        )
        if source_documents != current_documents or source_chunks != current_chunks:
            raise VaultDocumentMappingError("Source inventory changed after materialization.")
        self._check_paths()
        self._manifest_dir.mkdir(parents=True, exist_ok=True)
        previous: dict[str, Any] | None = None
        if expected_revision:
            previous = self._load_manifest(batch.collection_id, expected_revision)
        if expected_revision == 0 and not batch.documents:
            if self._db_path.exists():
                with GraphDocument.open(
                    self._db_path,
                    mode="read_only",
                    limits=self._graph_limits,
                    profile=self._profile,
                    max_excerpt_chars=0,
                ) as store:
                    try:
                        store.read(collection_id=batch.collection_id, selection="all", limits=self._read_limits)
                    except UnknownCollectionError:
                        pass
                    else:
                        raise VaultDocumentMappingError("Expected an absent collection at revision zero.")
            self._write_manifest(self._empty_manifest(batch.collection_id))
            return VaultSyncResult(batch.collection_id, 0, (), (), True)
        records = dict(previous["documents"]) if previous is not None else {}
        incoming = {item.document.document_id: item for item in batch.documents}
        extractor = _LegacyV1Extractor(batch.documents)
        for doc_id, item in incoming.items():
            prior = records.get(doc_id)
            if prior is not None and prior["input_digest"] == item.document.input_digest:
                current_digest = extraction_digest(extractor.extract(item.document, profile=self._profile))
                if prior["extraction_digest"] != current_digest:
                    raise VaultDocumentMappingError("Unchanged input produced different legacy extraction.")
        changed = tuple(
            incoming[doc_id].document
            for doc_id in sorted(incoming)
            if doc_id not in records or records[doc_id]["input_digest"] != incoming[doc_id].document.input_digest
        )
        removed = tuple(sorted(set(records) - set(incoming)))
        mode = "read_write" if self._db_path.exists() else "create"
        with GraphDocument.open(
            self._db_path,
            mode=mode,
            limits=self._graph_limits,
            profile=self._profile,
            extractor=extractor,
            max_excerpt_chars=0,
        ) as store:
            revision = expected_revision
            changed_ids: tuple[str, ...] = ()
            removed_ids: tuple[str, ...] = ()
            if previous is not None:
                current = store.read(collection_id=batch.collection_id, selection="all", limits=self._read_limits)
                self._validate_mapping(current, previous)
            if changed:
                result = store.update_documents(changed, collection_id=batch.collection_id, expected_revision=revision)
                revision = result.graph_revision
                changed_ids = result.changed_document_ids
            if removed:
                result = store.remove_documents(removed, collection_id=batch.collection_id, expected_revision=revision)
                revision = result.graph_revision
                removed_ids = result.removed_document_ids
            read = store.read(collection_id=batch.collection_id, selection="all", limits=self._read_limits)
        for doc_id in changed_ids:
            records[doc_id] = self._record(incoming[doc_id])
        for doc_id in removed_ids:
            records.pop(doc_id)
        if set(records) != {doc.document_id for doc in read.documents}:
            raise VaultDocumentMappingError("Manifest inventory differs from committed graph.")
        info = {doc.document_id: doc for doc in read.documents}
        for doc_id, record in records.items():
            if (
                record["input_digest"] != info[doc_id].input_digest
                or record["source_revision"] != info[doc_id].source_revision
            ):
                raise VaultDocumentMappingError("Manifest document digest differs from committed graph.")
            record["extraction_digest"] = info[doc_id].extraction_digest
        payload = {
            "version": 1,
            "collection_id": batch.collection_id,
            "graph_revision": revision,
            "profile_digest": self._profile.profile_digest,
            "read_digest": read.digest,
            "documents": records,
        }
        self._validate_mapping(read, payload)
        self._write_manifest(payload)
        return VaultSyncResult(batch.collection_id, revision, changed_ids, removed_ids, True)

    def restore_snapshot(self, *, collection_id: str, selection: str | tuple[str, ...] = "all") -> RestoredGraph:
        """Return legacy IDs only after revision, document, and ID mapping checks."""
        _, restored, _ = self.read_verified_snapshot(collection_id=collection_id, selection=selection)
        return restored

    def read_verified_snapshot(
        self, *, collection_id: str, selection: str | tuple[str, ...] = "all"
    ) -> tuple[DocumentGraphSnapshot | None, RestoredGraph, dict[str, Any]]:
        """Read and validate one revision for callers that need both graph views."""
        self._check_paths()
        if not self._db_path.exists():
            return None, self._restore_empty(collection_id, selection), self._empty_manifest(collection_id)
        with GraphDocument.open(
            self._db_path,
            mode="read_only",
            limits=self._graph_limits,
            profile=self._profile,
            max_excerpt_chars=0,
        ) as store:
            try:
                read = store.read(collection_id=collection_id, selection=selection, limits=self._read_limits)
            except UnknownCollectionError:
                return None, self._restore_empty(collection_id, selection), self._empty_manifest(collection_id)
        manifest = self._load_manifest(collection_id, read.graph_revision)
        self._validate_mapping(read, manifest)
        return read, self._restore(read, manifest), manifest

    def recover(self, batch: VaultDocumentBatch, *, expected_revision: int) -> VaultSyncResult:
        """Republish a missing manifest from a complete, matching source inventory.

        An interrupted update may have committed before manifest publication.
        Any document mismatch requires a separate full reindex into a new
        collection; this method never guesses an occurrence mapping.
        """
        if not batch.complete_inventory or expected_revision < 1:
            raise VaultDocumentMappingError("Recovery requires complete inventory and a committed revision.")
        self._check_paths()
        incoming = {item.document.document_id: item for item in batch.documents}
        if len(incoming) != len(batch.documents):
            raise VaultDocumentMappingError("Duplicate encoded document ID.")
        with GraphDocument.open(
            self._db_path,
            mode="read_write",
            limits=self._graph_limits,
            profile=self._profile,
            max_excerpt_chars=0,
        ) as store:
            read = store.read(collection_id=batch.collection_id, selection="all", limits=self._read_limits)
            if read.graph_revision != expected_revision:
                raise VaultDocumentMappingError("Committed revision changed during recovery.")
            info = {doc.document_id: doc for doc in read.documents}
            if not set(incoming) <= set(info):
                raise VaultDocumentMappingError("Committed graph lacks a supplied document.")
            extractor = _LegacyV1Extractor(batch.documents)
            for doc_id, item in incoming.items():
                extracted = extractor.extract(item.document, profile=self._profile)
                existing = info[doc_id]
                if (
                    existing.input_digest != item.document.input_digest
                    or existing.source_revision != item.document.source_revision
                    or existing.extraction_digest != extraction_digest(extracted)
                ):
                    raise VaultDocumentMappingError("Committed graph differs from supplied occurrences.")
            removed = tuple(sorted(set(info) - set(incoming)))
            if removed:
                result = store.remove_documents(
                    removed, collection_id=batch.collection_id, expected_revision=expected_revision
                )
                expected_revision = result.graph_revision
                read = store.read(collection_id=batch.collection_id, selection="all", limits=self._read_limits)
                info = {doc.document_id: doc for doc in read.documents}
        records = {doc_id: self._record(item) for doc_id, item in incoming.items()}
        for doc_id, record in records.items():
            record["extraction_digest"] = info[doc_id].extraction_digest
        payload = {
            "version": 1,
            "collection_id": batch.collection_id,
            "graph_revision": expected_revision,
            "profile_digest": self._profile.profile_digest,
            "read_digest": read.digest,
            "documents": records,
        }
        self._validate_mapping(read, payload)
        self._manifest_dir.mkdir(parents=True, exist_ok=True)
        self._write_manifest(payload)
        return VaultSyncResult(batch.collection_id, expected_revision, (), removed, True)

    def _empty_manifest(self, collection_id: str) -> dict[str, Any]:
        return {
            "version": 1,
            "collection_id": collection_id,
            "graph_revision": 0,
            "profile_digest": self._profile.profile_digest,
            "read_digest": _digest(("empty", collection_id, self._profile.profile_digest)),
            "documents": {},
        }

    def _restore_empty(self, collection_id: str, selection: str | tuple[str, ...]) -> RestoredGraph:
        payload = self._load_manifest(collection_id, 0)
        if payload != self._empty_manifest(collection_id) or selection not in ("all", ()):
            raise VaultDocumentMappingError("Empty collection mapping or selection differs.")
        return RestoredGraph(collection_id, 0, (), (), (), payload["read_digest"])

    def read_projection_input(self, request: VaultProjectionRequest) -> GraphProjectionInput:
        restored = self.restore_snapshot(collection_id=request.collection_id, selection=request.selection)
        seeds = tuple(node for node in restored.nodes if node.entity_id in request.seed_entity_ids)
        if len(seeds) != len(set(request.seed_entity_ids)):
            raise VaultDocumentMappingError("Requested legacy seed is not present in selection.")
        if any(not revision for revision in request.source_graph_revisions):
            raise VaultDocumentMappingError("Source graph revisions must be authoritative values.")
        revisions: dict[tuple[str, str], str] = {}
        for vault_id, relationship_id, revision in request.relationship_revisions:
            key = (vault_id, relationship_id)
            if not vault_id or not relationship_id or not revision or key in revisions:
                raise VaultDocumentMappingError("Relationship revision mapping is invalid.")
            revisions[key] = revision
        relationship_keys = {(edge.source_vault_id, edge.relationship_id) for edge in restored.relationships}
        if set(revisions) != relationship_keys:
            raise VaultDocumentMappingError("Relationship revision mapping differs from selected graph.")
        relationships = tuple(
            replace(edge, graph_index_revision=revisions[(edge.source_vault_id, edge.relationship_id)])
            for edge in restored.relationships
        )
        return GraphProjectionInput(
            seeds=seeds,
            nodes=restored.nodes,
            relationships=relationships,
            actual_scope_keys=request.actual_scope_keys,
            source_graph_revisions=request.source_graph_revisions,
            max_depth=request.max_depth,
            direction=request.direction,
            relationship_types=request.relationship_types,
            statuses=request.statuses,
            include_cross_vault=request.include_cross_vault,
            limit=request.limit,
            edge_limit=request.edge_limit,
        )

    def _record(self, item: VaultDocumentContribution) -> dict[str, Any]:
        return {
            "source_revision": item.document.source_revision,
            "input_digest": item.document.input_digest,
            "metadata_index_revision": item.source.index_revision,
            "parser_version": item.source.parser_version,
            "chunker_versions": sorted({chunk.chunker_version for chunk in item.chunks}),
            "spec_digest": self._spec.spec_digest,
            "entities": [dict(asdict(value), excerpt=None) for value in item.entity_occurrences],
            "relationships": [dict(asdict(value), excerpt=None) for value in item.relationship_occurrences],
        }

    def _manifest_path(self, collection_id: str, revision: int) -> Path:
        key = _digest((collection_id, revision, self._profile.profile_digest))
        return self._manifest_dir / f"{key}.json"

    def _check_paths(self) -> None:
        for path in (self._db_path, self._manifest_dir):
            if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
                raise VaultDocumentMappingError("Shadow cache path cannot cross a symlink.")

    def _write_manifest(self, payload: dict[str, Any]) -> None:
        content = _canonical(payload)
        wrapped = _canonical({"digest": hashlib.sha256(content.encode("utf-8")).hexdigest(), "payload": payload})
        target = self._manifest_path(payload["collection_id"], payload["graph_revision"])
        name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self._manifest_dir, prefix=".manifest-", delete=False
            ) as output:
                name = output.name
                output.write(wrapped)
                output.flush()
                os.fsync(output.fileno())
            os.replace(name, target)
            directory = os.open(self._manifest_dir, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)

    def _load_manifest(self, collection_id: str, revision: int) -> dict[str, Any]:
        self._check_paths()
        path = self._manifest_path(collection_id, revision)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "r", encoding="utf-8") as input_file:
                if not stat.S_ISREG(os.fstat(input_file.fileno()).st_mode):
                    raise VaultDocumentMappingError("Manifest must be a regular file.")
                wrapped = json.load(input_file)
            payload = wrapped["payload"]
            if wrapped["digest"] != _digest(payload) or payload["version"] != 1:
                raise VaultDocumentMappingError("Manifest digest mismatch.")
            if (
                payload["collection_id"] != collection_id
                or payload["graph_revision"] != revision
                or payload["profile_digest"] != self._profile.profile_digest
            ):
                raise VaultDocumentMappingError("Manifest revision or profile mismatch.")
            return cast(dict[str, Any], payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise VaultDocumentMappingError("Verified manifest is unavailable.") from exc

    def _validate_mapping(self, read: DocumentGraphSnapshot, manifest: dict[str, Any]) -> None:
        if (
            read.collection_id != manifest["collection_id"]
            or read.graph_revision != manifest["graph_revision"]
            or read.profile_digest != manifest["profile_digest"]
        ):
            raise VaultDocumentMappingError("Snapshot and manifest identity differ.")
        if read.selection == "all" and read.digest != manifest["read_digest"]:
            raise VaultDocumentMappingError("Full snapshot digest differs from manifest.")
        records: dict[str, Any] = manifest["documents"]
        selected = {doc.document_id for doc in read.documents}
        if read.selection == "all" and selected != set(records):
            raise VaultDocumentMappingError("Manifest inventory is incomplete.")
        if not selected <= set(records):
            raise VaultDocumentMappingError("Selected document mapping is missing.")
        known_keys: set[tuple[str, str]] = set()
        known_locations: dict[tuple[str, str], tuple[str, tuple[str, str, str] | None]] = {}
        expected_relations: set[tuple[str, str, str]] = set()
        for doc in read.documents:
            record = records[doc.document_id]
            if (
                record["input_digest"] != doc.input_digest
                or record["source_revision"] != doc.source_revision
                or record["extraction_digest"] != doc.extraction_digest
            ):
                raise VaultDocumentMappingError("Selected document digest mismatch.")
            known_keys.add(("document", doc.document_id))
            local_keys: set[str] = set()
            for index, entity in enumerate(record["entities"]):
                key = _encoded(
                    entity["vault_id"],
                    entity["entity_type"],
                    entity["normalized_name"],
                    entity["canonical_path"] or "",
                )
                known_keys.add(("legacy", key))
                local_keys.add(key)
                known_locations[(doc.document_id, f"e:{index}")] = (
                    entity["extraction_method"],
                    ("legacy", key, ""),
                )
            for index, relationship in enumerate(record["relationships"]):
                source = _encoded(*relationship["source_entity_key"])
                target = _encoded(*relationship["target_entity_key"])
                if (
                    relationship["source_vault_id"] != relationship["target_vault_id"]
                    or source not in local_keys
                    or target not in local_keys
                ):
                    continue
                edge_key = (source, target, relationship["relationship_type"])
                expected_relations.add(edge_key)
                known_locations[(doc.document_id, f"r:{index}")] = (
                    relationship["extraction_method"],
                    edge_key,
                )
            known_locations[(doc.document_id, "document")] = ("document", None)
        by_id = {node.node_id: node for node in read.nodes}
        if {(node.kind, node.key) for node in read.nodes} != known_keys:
            raise VaultDocumentMappingError("Snapshot nodes differ from legacy mapping.")
        observed_relations = {
            (by_id[edge.source_node_id].key, by_id[edge.target_node_id].key, edge.relation_type)
            for edge in read.edges
            if edge.source_node_id in by_id and edge.target_node_id in by_id
        }
        if len(observed_relations) != len(read.edges) or observed_relations != expected_relations:
            raise VaultDocumentMappingError("Snapshot edges differ from legacy mapping.")
        by_edge = {edge.edge_id: edge for edge in read.edges}
        if {(item.document_id, item.structural_id) for item in read.evidence} != set(known_locations):
            raise VaultDocumentMappingError("Snapshot evidence differs from legacy mapping.")
        for item in read.evidence:
            located = known_locations.get((item.document_id, item.structural_id))
            if located is None or located[0] != item.rule_id:
                raise VaultDocumentMappingError("Snapshot evidence has no legacy locator.")
            expected_owner = located[1]
            if expected_owner is None:
                owner = by_id.get(item.owner_id)
                if owner is None or owner.kind != "document" or owner.key != item.document_id:
                    raise VaultDocumentMappingError("Document identity evidence owner differs.")
            elif expected_owner[2] == "":
                owner = by_id.get(item.owner_id)
                if owner is None or (owner.kind, owner.key) != expected_owner[:2]:
                    raise VaultDocumentMappingError("Entity evidence owner differs.")
            else:
                edge = by_edge.get(item.owner_id)
                if (
                    edge is None
                    or (
                        by_id[edge.source_node_id].key,
                        by_id[edge.target_node_id].key,
                        edge.relation_type,
                    )
                    != expected_owner
                ):
                    raise VaultDocumentMappingError("Relationship evidence owner differs.")

    def _restore(self, read: DocumentGraphSnapshot, manifest: dict[str, Any]) -> RestoredGraph:
        entity_values: dict[tuple[str, str, str, str], list[EntityOccurrence]] = {}
        relation_values: list[RelationshipOccurrence] = []
        for info in read.documents:
            record = manifest["documents"][info.document_id]
            for raw in record["entities"]:
                raw["aliases"] = tuple(raw["aliases"])
                occurrence = EntityOccurrence(**raw)
                entity_values.setdefault(entity_occurrence_key(occurrence), []).append(occurrence)
            for raw in record["relationships"]:
                raw["source_entity_key"] = tuple(raw["source_entity_key"])
                raw["target_entity_key"] = tuple(raw["target_entity_key"])
                relation_values.append(RelationshipOccurrence(**raw))
        nodes: list[GraphProjectionNode] = []
        ids: dict[tuple[str, str, str, str], str] = {}
        evidence: list[GraphEvidenceRef] = []
        for key, entity_values_for_key in sorted(entity_values.items()):
            entity_group = sorted(
                entity_values_for_key,
                key=lambda value: (
                    value.vault_id,
                    value.path,
                    value.chunk_id,
                    value.extraction_method,
                    value.name,
                ),
            )
            entity_representative = max(entity_group, key=lambda value: value.confidence)
            entity_id = stable_entity_id(
                vault_id=key[0],
                entity_type=key[1],
                normalized_name=key[2],
                canonical_path=key[3] or None,
            )
            ids[key] = entity_id
            nodes.append(
                GraphProjectionNode(
                    entity_representative.vault_id,
                    entity_id,
                    entity_representative.entity_type,
                    entity_representative.name,
                    entity_representative.normalized_name,
                )
            )
            evidence.extend(self._evidence_ref("entity", entity_id, value) for value in entity_group)
        relation_groups: dict[str, list[RelationshipOccurrence]] = {}
        for relationship_occurrence in relation_values:
            if relationship_occurrence.source_vault_id != relationship_occurrence.target_vault_id:
                continue
            source = ids.get(relationship_occurrence.source_entity_key)
            target = ids.get(relationship_occurrence.target_entity_key)
            if source is None or target is None:
                continue
            relation_id = stable_relationship_id(
                relationship_type=relationship_occurrence.relationship_type,
                source_vault_id=relationship_occurrence.source_vault_id,
                source_entity_id=source,
                target_vault_id=relationship_occurrence.target_vault_id,
                target_entity_id=target,
            )
            relation_groups.setdefault(relation_id, []).append(relationship_occurrence)
            evidence.append(self._evidence_ref("relationship", relation_id, relationship_occurrence))
        relationships: list[GraphProjectionEdge] = []
        for relation_id, relation_values_for_id in sorted(relation_groups.items()):
            relationship_group = sorted(
                relation_values_for_id,
                key=lambda value: (
                    value.source_vault_id,
                    value.path,
                    value.chunk_id,
                    value.extraction_method,
                ),
            )
            relationship_representative = max(relationship_group, key=lambda value: value.confidence)
            relationship_evidence = tuple(
                dict.fromkeys(
                    stable_evidence_ref_id(
                        owner_kind="relationship",
                        owner_vault_id=value.source_vault_id,
                        owner_id=relation_id,
                        evidence_vault_id=value.evidence_vault_id,
                        document_id=value.document_id,
                        chunk_id=value.chunk_id,
                        anchor=value.anchor,
                    )
                    for value in relationship_group
                )
            )
            relationships.append(
                GraphProjectionEdge(
                    relationship_representative.source_vault_id,
                    ids[relationship_representative.source_entity_key],
                    relationship_representative.target_vault_id,
                    ids[relationship_representative.target_entity_key],
                    relation_id,
                    relationship_representative.relationship_type,
                    relationship_representative.status,
                    relationship_representative.confidence,
                    relationship_evidence,
                    "",
                )
            )
        return RestoredGraph(
            read.collection_id,
            read.graph_revision,
            tuple(nodes),
            tuple(relationships),
            tuple({value.evidence_ref_id: value for value in evidence}.values()),
            read.digest,
        )

    @staticmethod
    def _evidence_ref(
        kind: str, owner_id: str, occurrence: EntityOccurrence | RelationshipOccurrence
    ) -> GraphEvidenceRef:
        owner_vault_id = occurrence.vault_id if isinstance(occurrence, EntityOccurrence) else occurrence.source_vault_id
        return GraphEvidenceRef(
            evidence_ref_id=stable_evidence_ref_id(
                owner_kind=kind,
                owner_vault_id=owner_vault_id,
                owner_id=owner_id,
                evidence_vault_id=occurrence.evidence_vault_id,
                document_id=occurrence.document_id,
                chunk_id=occurrence.chunk_id,
                anchor=occurrence.anchor,
            ),
            owner_kind=kind,
            owner_vault_id=owner_vault_id,
            owner_id=owner_id,
            evidence_vault_id=occurrence.evidence_vault_id,
            document_id=occurrence.document_id,
            chunk_id=occurrence.chunk_id,
            content_hash=occurrence.content_hash,
            section=occurrence.section,
            anchor=occurrence.anchor,
            path=occurrence.path,
        )
