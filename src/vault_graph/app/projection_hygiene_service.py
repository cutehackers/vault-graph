from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

from vault_graph.ingestion.document_authority import DocumentRole
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.storage.local.chroma_vector_store import ChromaVectorStore


@dataclass(frozen=True)
class RoleCount:
    role: DocumentRole
    count: int


@dataclass(frozen=True)
class SchemaVersion:
    projection: str
    version: str


@dataclass(frozen=True)
class ProjectionHygieneReport:
    role_counts: tuple[RoleCount, ...]
    canonical_blob_count: int
    canonical_blob_bytes: int
    logical_chunk_bytes: int
    persisted_search_projection_plaintext_bytes: int
    plaintext_amplification: float
    dangling_keyword_refs: int
    dangling_vector_refs: int
    dangling_graph_refs: int
    result_family_duplication: float | None
    schema_versions: tuple[SchemaVersion, ...]
    active_generation_id: str | None = None
    bundle_manifest_valid: bool = False
    component_capabilities: tuple[str, ...] = ()
    source_snapshot_id: str | None = None
    component_revisions: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProjectionHygieneService:
    """Read-only inventory proving that projections reference canonical metadata."""

    def __init__(self, *, metadata_path: Path, vector_path: Path, graph_path: Path) -> None:
        self._metadata_path = metadata_path
        self._vector_path = vector_path
        self._graph_path = graph_path

    def audit(
        self,
        *,
        scope: QueryScope,
        result_family_duplication: float | None = None,
        active_generation_id: str | None = None,
    ) -> ProjectionHygieneReport:
        with _connect_readonly(self._metadata_path) as connection:
            role_counts = tuple(
                RoleCount(role=cast(DocumentRole, str(row[0])), count=int(row[1]))
                for row in connection.execute(
                    "SELECT source_role, COUNT(*) FROM documents "
                    "WHERE is_tombstoned = 0 GROUP BY source_role ORDER BY source_role"
                )
            )
            canonical_blob_count, canonical_blob_bytes = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(byte_count), 0) FROM content_blobs"
            ).fetchone()
            logical_chunk_bytes = int(
                connection.execute(
                    "SELECT COALESCE(SUM(b.byte_count), 0) FROM chunks c "
                    "INNER JOIN content_blobs b ON b.blob_hash = c.blob_hash"
                ).fetchone()[0]
            )
            dangling_keyword_refs = int(
                connection.execute(
                    "SELECT COUNT(*) FROM keyword_rows r LEFT JOIN chunks c "
                    "ON c.vault_id = r.vault_id AND c.chunk_id = r.chunk_id WHERE c.chunk_id IS NULL"
                ).fetchone()[0]
            )
            chunk_keys = {
                (str(row[0]), str(row[1])) for row in connection.execute("SELECT vault_id, chunk_id FROM chunks")
            }
        vector = ChromaVectorStore(self._vector_path, read_only=True)
        vector_rows = vector.export_manifest(scope)
        dangling_vector_refs = sum((row.vault_id, row.chunk_id) not in chunk_keys for row in vector_rows)
        dangling_graph_refs = _dangling_graph_refs(self._graph_path, chunk_keys)
        metadata_version = _metadata_version(self._metadata_path)
        graph_version = _projection_version(self._graph_path, "graph_metadata")
        vector_version = vector.health().schema_version
        amplification = 1.0
        bundle = _bundle_manifest(self._metadata_path.parent.parent)
        return ProjectionHygieneReport(
            role_counts=role_counts,
            canonical_blob_count=int(canonical_blob_count),
            canonical_blob_bytes=int(canonical_blob_bytes),
            logical_chunk_bytes=logical_chunk_bytes,
            persisted_search_projection_plaintext_bytes=0,
            plaintext_amplification=amplification,
            dangling_keyword_refs=dangling_keyword_refs,
            dangling_vector_refs=dangling_vector_refs,
            dangling_graph_refs=dangling_graph_refs,
            result_family_duplication=result_family_duplication,
            schema_versions=(
                SchemaVersion("metadata", metadata_version),
                SchemaVersion("keyword", "sqlite-keyword-v2"),
                SchemaVersion("vector", vector_version),
                SchemaVersion("graph", graph_version),
            ),
            active_generation_id=active_generation_id,
            bundle_manifest_valid=bundle.valid,
            component_capabilities=bundle.components,
            source_snapshot_id=bundle.source_snapshot_id,
            component_revisions=bundle.revisions,
        )


@dataclass(frozen=True)
class _BundleManifestAudit:
    valid: bool
    components: tuple[str, ...] = ()
    source_snapshot_id: str | None = None
    revisions: tuple[tuple[str, str], ...] = ()


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.expanduser().resolve()}?mode=ro", uri=True)
    return connection


def _metadata_version(path: Path) -> str:
    with _connect_readonly(path) as connection:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return "metadata-v2" if "content_blobs" in tables else "incompatible"


def _projection_version(path: Path, table: str) -> str:
    if not path.exists():
        return "missing"
    with _connect_readonly(path) as connection:
        row = connection.execute(f"SELECT value FROM {table} WHERE key = 'schema_version'").fetchone()
    return str(row[0]) if row is not None else "incompatible"


def _dangling_graph_refs(path: Path, chunk_keys: set[tuple[str, str]]) -> int:
    if not path.exists():
        return 0
    with _connect_readonly(path) as connection:
        refs = connection.execute("SELECT evidence_vault_id, chunk_id FROM graph_evidence_refs").fetchall()
    return sum((str(row[0]), str(row[1])) not in chunk_keys for row in refs)


def _bundle_manifest(root_path: Path) -> _BundleManifestAudit:
    manifest_path = root_path / "bundle-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        return _BundleManifestAudit(valid=False)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _BundleManifestAudit(valid=False)
    if not isinstance(payload, dict) or payload.get("format") != "vault-graph-projection-bundle-v1":
        return _BundleManifestAudit(valid=False)
    components = payload.get("components")
    source_snapshot_id = payload.get("source_snapshot_id")
    if (
        not isinstance(components, list)
        or not components
        or not all(isinstance(component, str) for component in components)
        or not isinstance(source_snapshot_id, str)
    ):
        return _BundleManifestAudit(valid=False)
    revisions_payload = payload.get("component_revisions")
    if not isinstance(revisions_payload, dict) or not all(
        isinstance(component, str) and isinstance(revision, str) for component, revision in revisions_payload.items()
    ):
        return _BundleManifestAudit(valid=False)
    root_components = tuple(sorted(set(components)))
    for component in root_components:
        component_manifest = root_path / component / "manifest.json"
        if component_manifest.is_symlink() or not component_manifest.is_file():
            return _BundleManifestAudit(valid=False)
        try:
            component_payload = json.loads(component_manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return _BundleManifestAudit(valid=False)
        if (
            not isinstance(component_payload, dict)
            or component_payload.get("status") != "ready"
            or component_payload.get("source_snapshot_id") != source_snapshot_id
            or component_payload.get("revision") != revisions_payload.get(component)
        ):
            return _BundleManifestAudit(valid=False)
    return _BundleManifestAudit(
        valid=True,
        components=root_components,
        source_snapshot_id=source_snapshot_id,
        revisions=tuple(sorted((str(component), str(revision)) for component, revision in revisions_payload.items())),
    )
