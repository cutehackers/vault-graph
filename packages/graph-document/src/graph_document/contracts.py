from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from .errors import InvalidDocumentError


def canonical(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def valid_string(value: object, name: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        raise InvalidDocumentError(f"{name} must be a nonempty string")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise InvalidDocumentError(f"{name} must be UTF-8 encodable") from exc
    return value


def valid_limit(value: object, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or value < (0 if zero else 1):
        raise InvalidDocumentError(
            f"{name} must be a {'nonnegative' if zero else 'positive'} integer"
        )
    return value


@dataclass(frozen=True, slots=True)
class EntityKey:
    kind: str
    key: str

    def __post_init__(self) -> None:
        valid_string(self.kind, "kind")
        valid_string(self.key, "key")


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    structural_id: str
    text_span: tuple[int, int] | None = None
    label: str | None = None

    def __post_init__(self) -> None:
        valid_string(self.structural_id, "structural_id")
        if self.text_span is not None and (
            not isinstance(self.text_span, tuple)
            or len(self.text_span) != 2
            or any(type(x) is not int for x in self.text_span)
            or self.text_span[0] < 0
            or self.text_span[0] >= self.text_span[1]
        ):
            raise InvalidDocumentError("text_span must have 0 <= start < end")
        if self.label is not None:
            valid_string(self.label, "location.label", empty=True)


@dataclass(frozen=True, slots=True)
class LocatedValue:
    value: str
    location: EvidenceLocation

    def __post_init__(self) -> None:
        valid_string(self.value, "value")
        if not isinstance(self.location, EvidenceLocation):
            raise InvalidDocumentError("location must be EvidenceLocation")


@dataclass(frozen=True, slots=True)
class Reference:
    target_document_id: str | None = None
    unresolved_key: str | None = None
    label: str | None = None
    location: EvidenceLocation = field(default_factory=lambda: EvidenceLocation("reference"))

    def __post_init__(self) -> None:
        if (self.target_document_id is None) == (self.unresolved_key is None):
            raise InvalidDocumentError("reference needs exactly one target")
        if self.target_document_id is not None:
            valid_string(self.target_document_id, "target_document_id")
        if self.unresolved_key is not None:
            valid_string(self.unresolved_key, "unresolved_key")
        if self.label is not None:
            valid_string(self.label, "reference.label", empty=True)
        if not isinstance(self.location, EvidenceLocation):
            raise InvalidDocumentError("location must be EvidenceLocation")


@dataclass(frozen=True, slots=True)
class StatedRelation:
    source: EntityKey
    target: EntityKey
    relation_type: str
    location: EvidenceLocation

    def __post_init__(self) -> None:
        if not isinstance(self.source, EntityKey) or not isinstance(self.target, EntityKey):
            raise InvalidDocumentError("relation endpoints must be EntityKey")
        valid_string(self.relation_type, "relation_type")
        if not isinstance(self.location, EvidenceLocation):
            raise InvalidDocumentError("location must be EvidenceLocation")


@dataclass(frozen=True, slots=True)
class DocumentFeatures:
    tags: tuple[LocatedValue, ...] = ()
    headings: tuple[LocatedValue, ...] = ()
    references: tuple[Reference, ...] = ()
    stated_relations: tuple[StatedRelation, ...] = ()

    def __post_init__(self) -> None:
        for name, expected in (
            ("tags", LocatedValue),
            ("headings", LocatedValue),
            ("references", Reference),
            ("stated_relations", StatedRelation),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, expected) for value in values
            ):
                raise InvalidDocumentError(f"{name} must be a tuple of {expected.__name__}")


@dataclass(frozen=True, slots=True)
class Document:
    document_id: str
    source_revision: str
    title: str
    text: str
    features: DocumentFeatures = field(default_factory=DocumentFeatures)
    source_locator: str | None = None

    def __post_init__(self) -> None:
        valid_string(self.document_id, "document_id")
        valid_string(self.source_revision, "source_revision")
        valid_string(self.title, "title", empty=True)
        valid_string(self.text, "text", empty=True)
        if not isinstance(self.features, DocumentFeatures):
            raise InvalidDocumentError("features must be DocumentFeatures")
        if self.source_locator is not None:
            valid_string(self.source_locator, "source_locator", empty=True)
        locations: dict[str, EvidenceLocation] = {}
        for feature in (
            *self.features.tags,
            *self.features.headings,
            *self.features.references,
            *self.features.stated_relations,
        ):
            loc = feature.location  # type: ignore[attr-defined]
            if loc.text_span is not None and loc.text_span[1] > len(self.text):
                raise InvalidDocumentError("text_span exceeds Document.text")
            prior = locations.setdefault(loc.structural_id, loc)
            if prior != loc:
                raise InvalidDocumentError("conflicting structural_id")

    @property
    def input_digest(self) -> str:
        def ordered(values: tuple[Any, ...]) -> list[dict[str, object]]:
            unique = {canonical(asdict(value)): asdict(value) for value in values}
            return [unique[k] for k in sorted(unique)]

        f = self.features
        return digest(
            {
                "serialization_version": 1,
                "document_id": self.document_id,
                "source_revision": self.source_revision,
                "title": self.title,
                "text": self.text,
                "source_locator": self.source_locator,
                "features": {
                    "tags": ordered(f.tags),
                    "headings": ordered(f.headings),
                    "references": ordered(f.references),
                    "stated_relations": ordered(f.stated_relations),
                },
            }
        )


DEFAULT_RELATIONS = (
    "mentions",
    "links_to",
    "related_to",
    "depends_on",
    "blocks",
    "implements",
    "supersedes",
    "revisit_when",
    "unresolved_reference",
)


@dataclass(frozen=True, slots=True)
class ExtractionProfile:
    profile_id: str = "rule-v1"
    extractor_fingerprint: str = "rule-v1"
    name_normalization: Literal["nfkc_casefold_space_v1", "identity_v1"] = "nfkc_casefold_space_v1"
    excluded_headings: tuple[str, ...] = ()
    allowed_kinds: tuple[str, ...] = ("document", "concept", "unresolved")
    allowed_relation_types: tuple[str, ...] = DEFAULT_RELATIONS
    max_excerpt_chars: int = 0

    def __post_init__(self) -> None:
        valid_string(self.profile_id, "profile_id")
        valid_string(self.extractor_fingerprint, "extractor_fingerprint")
        if self.name_normalization not in ("nfkc_casefold_space_v1", "identity_v1"):
            raise InvalidDocumentError("unsupported name_normalization")
        valid_limit(self.max_excerpt_chars, "max_excerpt_chars", zero=True)
        for name, values in (
            ("excluded_headings", self.excluded_headings),
            ("allowed_kinds", self.allowed_kinds),
            ("allowed_relation_types", self.allowed_relation_types),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(x, str) or not x for x in values
            ):
                raise InvalidDocumentError(f"{name} must be a tuple of nonempty strings")

    @property
    def profile_digest(self) -> str:
        return digest({"identity_version": 1, "serialization_version": 1, **asdict(self)})


@dataclass(frozen=True, slots=True)
class EntityFact:
    key: EntityKey
    label: str
    aliases: tuple[str, ...]
    rule_id: str
    locations: tuple[EvidenceLocation, ...]


@dataclass(frozen=True, slots=True)
class RelationFact:
    source: EntityKey
    target: EntityKey
    relation_type: str
    rule_id: str
    locations: tuple[EvidenceLocation, ...]


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    document_id: str
    input_digest: str
    profile_digest: str
    entities: tuple[EntityFact, ...]
    relations: tuple[RelationFact, ...]
    evidence: tuple[EvidenceLocation, ...]
    warnings: tuple[str, ...] = ()


class Extractor(Protocol):
    def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument: ...


@dataclass(frozen=True, slots=True)
class GraphLimits:
    max_batch_documents: int
    max_document_utf8_bytes: int
    max_batch_utf8_bytes: int
    max_nodes: int
    max_edges: int
    max_evidence: int
    max_id_utf8_bytes: int

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            valid_limit(value, key)


@dataclass(frozen=True, slots=True)
class ReadLimits:
    max_nodes: int
    max_edges: int
    max_evidence: int
    max_documents: int
    max_serialized_utf8_bytes: int

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            valid_limit(value, key)
