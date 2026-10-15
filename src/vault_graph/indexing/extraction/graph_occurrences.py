from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import GraphExtractionError

EntityOccurrenceKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class GraphExtractionWarning:
    code: str
    message: str
    vault_id: str
    path: str
    chunk_id: str


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise GraphExtractionError(f"{field_name} is required")


@dataclass(frozen=True)
class EntityOccurrence:
    vault_id: str
    entity_type: str
    name: str
    normalized_name: str
    aliases: tuple[str, ...]
    canonical_path: str | None
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None
    anchor: str | None
    path: str
    excerpt: str | None
    confidence: float
    extraction_method: str

    def __post_init__(self) -> None:
        for field_name in (
            "vault_id",
            "entity_type",
            "name",
            "normalized_name",
            "evidence_vault_id",
            "document_id",
            "chunk_id",
            "content_hash",
            "path",
            "extraction_method",
        ):
            _require_non_empty(str(getattr(self, field_name)), field_name)
        if not isinstance(self.aliases, tuple):
            raise GraphExtractionError("aliases must be a tuple")
        if not 0 <= self.confidence <= 1:
            raise GraphExtractionError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class RelationshipOccurrence:
    relationship_type: str
    source_vault_id: str
    source_entity_key: EntityOccurrenceKey
    target_vault_id: str
    target_entity_key: EntityOccurrenceKey
    evidence_vault_id: str
    document_id: str
    chunk_id: str
    content_hash: str
    section: str | None
    anchor: str | None
    path: str
    excerpt: str | None
    status: str
    confidence: float
    extraction_method: str

    def __post_init__(self) -> None:
        for field_name in (
            "relationship_type",
            "source_vault_id",
            "target_vault_id",
            "evidence_vault_id",
            "document_id",
            "chunk_id",
            "content_hash",
            "path",
            "extraction_method",
        ):
            _require_non_empty(str(getattr(self, field_name)), field_name)
        if self.status not in {"stated", "inferred", "contested", "deprecated"}:
            raise GraphExtractionError(f"unsupported relationship status: {self.status}")
        if not 0 <= self.confidence <= 1:
            raise GraphExtractionError("confidence must be between 0 and 1")
        _require_entity_key(self.source_entity_key, "source_entity_key")
        _require_entity_key(self.target_entity_key, "target_entity_key")


def entity_occurrence_key(occurrence: EntityOccurrence) -> EntityOccurrenceKey:
    return (
        occurrence.vault_id,
        occurrence.entity_type,
        occurrence.normalized_name,
        occurrence.canonical_path or "",
    )


def _require_entity_key(value: EntityOccurrenceKey, field_name: str) -> None:
    if (
        not isinstance(value, tuple)
        or len(value) != 4
        or any(not isinstance(part, str) for part in value)
        or any(not part for part in value[:3])
    ):
        raise GraphExtractionError(f"{field_name} must be a non-empty 4-part tuple")
