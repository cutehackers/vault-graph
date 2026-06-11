from dataclasses import dataclass

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot


@dataclass(frozen=True)
class MetadataRevisionPlan:
    index_revision: str
    mode: str
    vault_ids: tuple[str, ...]
    changed_paths: tuple[tuple[str, str], ...]
    unchanged_paths: tuple[tuple[str, str], ...]
    deleted_paths: tuple[tuple[str, str], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MetadataIndexPreview:
    plan: MetadataRevisionPlan
    chunks_after_apply: tuple[ChunkSnapshot, ...]
    documents_after_apply: tuple[DocumentSnapshot, ...]
