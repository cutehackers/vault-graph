from __future__ import annotations

import unicodedata
from dataclasses import asdict
from typing import Any, TypeVar, cast

from .contracts import (
    Document,
    EntityFact,
    EntityKey,
    EvidenceLocation,
    ExtractedDocument,
    ExtractionProfile,
    RelationFact,
    canonical,
    digest,
    valid_string,
)
from .errors import InvalidDocumentError, InvalidExtractionError


def normalize(value: str, method: str) -> str:
    if method == "identity_v1":
        return value
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def extraction_digest(extracted: ExtractedDocument) -> str:
    def ordered(values: tuple[Any, ...]) -> list[dict[str, object]]:
        unique = {canonical(asdict(value)): asdict(value) for value in values}
        return [unique[k] for k in sorted(unique)]

    return digest(
        {
            "entities": ordered(extracted.entities),
            "relations": ordered(extracted.relations),
            "evidence": ordered(extracted.evidence),
            "warnings": sorted(set(extracted.warnings)),
        }
    )


T = TypeVar("T")


class RuleExtractor:
    def extract(self, document: Document, *, profile: ExtractionProfile) -> ExtractedDocument:
        doc_key = EntityKey("document", document.document_id)
        document_location = EvidenceLocation("document")
        entities: list[EntityFact] = [
            EntityFact(
                doc_key,
                document.title or document.document_id,
                (),
                "document",
                (document_location,),
            )
        ]
        relations: list[RelationFact] = []
        locations: set[EvidenceLocation] = {document_location}

        def entity(key: EntityKey, label: str, rule: str, location: EvidenceLocation) -> None:
            entities.append(EntityFact(key, label, (), rule, (location,)))
            locations.add(location)

        def relation(
            source: EntityKey, target: EntityKey, kind: str, rule: str, location: EvidenceLocation
        ) -> None:
            relations.append(RelationFact(source, target, kind, rule, (location,)))
            locations.add(location)

        excluded = {normalize(v, profile.name_normalization) for v in profile.excluded_headings}
        for value, is_heading in (
            *((item, False) for item in document.features.tags),
            *((item, True) for item in document.features.headings),
        ):
            key = normalize(value.value, profile.name_normalization)
            if is_heading and key in excluded:
                continue
            if not key:
                raise InvalidDocumentError("normalized concept key is empty")
            concept = EntityKey("concept", key)
            entity(concept, value.value, "concept", value.location)
            relation(doc_key, concept, "mentions", "mentions", value.location)

        for ref in document.features.references:
            if ref.target_document_id is not None:
                target = EntityKey("document", ref.target_document_id)
                kind = "links_to"
            else:
                target = EntityKey("unresolved", ref.unresolved_key or "")
                kind = "unresolved_reference"
            entity(target, ref.label or target.key, "reference_target", ref.location)
            relation(doc_key, target, kind, kind, ref.location)

        for stated in document.features.stated_relations:
            for endpoint in (stated.source, stated.target):
                if endpoint == doc_key:
                    continue
                entity(endpoint, endpoint.key, "stated_endpoint", stated.location)
            relation(
                stated.source,
                stated.target,
                stated.relation_type,
                "stated_relation",
                stated.location,
            )

        def unique_sorted(values: list[T]) -> tuple[T, ...]:
            return tuple(
                {canonical(asdict(cast(Any, x))): x for x in values}[k]
                for k in sorted({canonical(asdict(cast(Any, x))) for x in values})
            )

        return ExtractedDocument(
            document.document_id,
            document.input_digest,
            profile.profile_digest,
            unique_sorted(entities),
            unique_sorted(relations),
            tuple(sorted(locations, key=lambda x: canonical(asdict(x)))),
        )


def validate_extraction(
    document: Document, result: ExtractedDocument, profile: ExtractionProfile
) -> None:
    def valid_output_string(value: object, name: str, *, empty: bool = False) -> None:
        try:
            valid_string(value, name, empty=empty)
        except InvalidDocumentError as exc:
            raise InvalidExtractionError(f"invalid {name}") from exc

    if not isinstance(result, ExtractedDocument):
        raise InvalidExtractionError("extractor must return ExtractedDocument")
    if (
        result.document_id != document.document_id
        or result.input_digest != document.input_digest
        or result.profile_digest != profile.profile_digest
    ):
        raise InvalidExtractionError("extractor returned incorrect identity or digest")
    if (
        not isinstance(result.entities, tuple)
        or not isinstance(result.relations, tuple)
        or not isinstance(result.evidence, tuple)
    ):
        raise InvalidExtractionError("facts and evidence must be tuples")
    if not isinstance(result.warnings, tuple) or any(
        not isinstance(w, str) for w in result.warnings
    ):
        raise InvalidExtractionError("warnings must be strings")
    for warning in result.warnings:
        valid_output_string(warning, "warning", empty=True)
    known_locations = {EvidenceLocation("document")}
    for feature in (
        *document.features.tags,
        *document.features.headings,
        *document.features.references,
        *document.features.stated_relations,
    ):
        known_locations.add(feature.location)  # type: ignore[attr-defined]
    if any(
        not isinstance(x, EvidenceLocation) or x not in known_locations for x in result.evidence
    ):
        raise InvalidExtractionError("evidence location absent from input document")
    if len(set(result.evidence)) != len(result.evidence):
        raise InvalidExtractionError("duplicate evidence location")
    entities: set[EntityKey] = set()
    used: set[EvidenceLocation] = set()
    document_identity = False
    for fact in result.entities:
        if not isinstance(fact, EntityFact) or not isinstance(fact.key, EntityKey):
            raise InvalidExtractionError("invalid entity fact")
        if fact.key.kind not in profile.allowed_kinds:
            raise InvalidExtractionError("entity kind not allowed")
        valid_output_string(fact.label, "entity label", empty=True)
        valid_output_string(fact.rule_id, "entity rule")
        if not isinstance(fact.aliases, tuple) or any(not isinstance(x, str) for x in fact.aliases):
            raise InvalidExtractionError("invalid aliases")
        for alias in fact.aliases:
            valid_output_string(alias, "alias", empty=True)
        if (
            not isinstance(fact.locations, tuple)
            or not fact.locations
            or any(x not in result.evidence for x in fact.locations)
        ):
            raise InvalidExtractionError("entity has invalid evidence")
        entities.add(fact.key)
        used.update(fact.locations)
        if (
            fact.key == EntityKey("document", document.document_id)
            and EvidenceLocation("document") in fact.locations
        ):
            document_identity = True
    if not document_identity:
        raise InvalidExtractionError("document identity evidence missing")
    for relation in result.relations:
        relation_fact = relation
        if (
            not isinstance(relation_fact, RelationFact)
            or not isinstance(relation_fact.source, EntityKey)
            or not isinstance(relation_fact.target, EntityKey)
        ):
            raise InvalidExtractionError("invalid relation fact")
        if relation_fact.relation_type not in profile.allowed_relation_types:
            raise InvalidExtractionError("relation type not allowed")
        valid_output_string(relation_fact.rule_id, "relation rule")
        if relation_fact.source not in entities or relation_fact.target not in entities:
            raise InvalidExtractionError("relation endpoint missing")
        if (
            not isinstance(relation_fact.locations, tuple)
            or not relation_fact.locations
            or any(x not in result.evidence for x in relation_fact.locations)
        ):
            raise InvalidExtractionError("relation has invalid evidence")
        used.update(relation_fact.locations)
    if used != set(result.evidence):
        raise InvalidExtractionError("unreferenced evidence location")
