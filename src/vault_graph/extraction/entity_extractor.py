from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from vault_graph.extraction.graph_occurrences import EntityOccurrence, entity_occurrence_key
from vault_graph.extraction.graph_source_store import GraphExtractionContext
from vault_graph.graph.graph_contracts import GraphExtractionSpec
from vault_graph.graph.graph_identity import normalize_entity_name
from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope

GENERIC_HEADINGS = {"overview", "summary", "notes", "todo", "appendix", "references"}
FRONTMATTER_RELATIONSHIP_METHODS = {
    "related": "frontmatter-related-target-v1",
    "depends_on": "frontmatter-depends-on-target-v1",
    "blocks": "frontmatter-blocks-target-v1",
    "implements": "frontmatter-implements-target-v1",
    "supersedes": "frontmatter-supersedes-target-v1",
}
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)")
WIKI_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


class EntityExtractor(Protocol):
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[EntityOccurrence, ...]: ...


class DeterministicEntityExtractor:
    def extract(
        self,
        *,
        chunk: ChunkSnapshot,
        document: DocumentSnapshot | None,
        context: GraphExtractionContext,
        scope: QueryScope,
        spec: GraphExtractionSpec,
    ) -> tuple[EntityOccurrence, ...]:
        occurrences: list[EntityOccurrence] = []
        if document is not None:
            occurrences.append(
                _document_entity(
                    chunk=chunk,
                    document=document,
                    extraction_method="document-identity-v1",
                )
            )
            occurrences.extend(_tag_entities(chunk=chunk, document=document))
            occurrences.extend(_frontmatter_target_entities(chunk=chunk, document=document, context=context))
        if chunk.section and not _generic_heading(chunk.section):
            occurrences.append(_heading_entity(chunk))
        occurrences.extend(_link_entities(chunk=chunk, context=context))
        return tuple(_dedupe_occurrences(occurrences))


@dataclass(frozen=True)
class ParsedLocalLink:
    target: str
    label: str


def _document_entity(
    *,
    chunk: ChunkSnapshot,
    document: DocumentSnapshot,
    extraction_method: str,
    use_evidence_heading: bool = True,
) -> EntityOccurrence:
    name = _document_name(document=document, chunk=chunk if use_evidence_heading else None)
    return EntityOccurrence(
        vault_id=document.vault_id,
        entity_type=_document_entity_type(document),
        name=name,
        normalized_name=normalize_entity_name(name),
        aliases=_aliases(document),
        canonical_path=document.path,
        evidence_vault_id=chunk.vault_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        content_hash=chunk.content_hash,
        section=chunk.section,
        anchor=chunk.anchor,
        path=chunk.path,
        excerpt=_excerpt(chunk.text),
        confidence=1.0,
        extraction_method=extraction_method,
    )


def _document_entity_type(document: DocumentSnapshot) -> str:
    frontmatter_type = str(document.frontmatter.get("type") or document.frontmatter.get("kind") or "").casefold()
    if frontmatter_type == "decision" or "/decisions/" in document.path:
        return "Decision"
    if document.path.startswith("wiki/"):
        return "WikiPage"
    if document.path.startswith("raw/"):
        return "Source"
    return "Document"


def _document_name(*, document: DocumentSnapshot, chunk: ChunkSnapshot | None) -> str:
    title = _scalar_frontmatter(document, "title")
    if title is not None:
        return title
    if chunk is not None and chunk.section:
        return chunk.section
    basename = PurePosixPath(document.path).name
    if basename.endswith(".md"):
        return basename[:-3]
    return document.path


def _aliases(document: DocumentSnapshot) -> tuple[str, ...]:
    aliases: list[str] = []
    for field_name in ("aliases", "alias"):
        aliases.extend(_frontmatter_values(document.frontmatter.get(field_name)))
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _heading_entity(chunk: ChunkSnapshot) -> EntityOccurrence:
    name = chunk.section or ""
    return EntityOccurrence(
        vault_id=chunk.vault_id,
        entity_type="Concept",
        name=name,
        normalized_name=normalize_entity_name(name),
        aliases=(),
        canonical_path=None,
        evidence_vault_id=chunk.vault_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        content_hash=chunk.content_hash,
        section=chunk.section,
        anchor=chunk.anchor,
        path=chunk.path,
        excerpt=_excerpt(chunk.text),
        confidence=0.85,
        extraction_method="heading-concept-v1",
    )


def _tag_entities(*, chunk: ChunkSnapshot, document: DocumentSnapshot) -> tuple[EntityOccurrence, ...]:
    return tuple(
        _concept_entity(chunk=chunk, name=tag, confidence=0.8, extraction_method="frontmatter-tag-concept-v1")
        for tag in _frontmatter_tags(document)
    )


def _link_entities(*, chunk: ChunkSnapshot, context: GraphExtractionContext) -> tuple[EntityOccurrence, ...]:
    occurrences: list[EntityOccurrence] = []
    for link in _local_links(chunk.text):
        target = context.resolve_local_document_link(source_path=chunk.path, raw_target=link.target)
        if target is None:
            if _link_is_external_or_anchor(link.target):
                continue
            occurrences.append(
                _concept_entity(
                    chunk=chunk,
                    name=link.label or link.target,
                    confidence=0.7,
                    extraction_method="unresolved-local-link-concept-v1",
                )
            )
            continue
        occurrences.append(
                _document_entity(
                    chunk=chunk,
                    document=target,
                    extraction_method="local-link-target-document-v1",
                    use_evidence_heading=False,
                )
            )
    return tuple(occurrences)


def _frontmatter_target_entities(
    *,
    chunk: ChunkSnapshot,
    document: DocumentSnapshot,
    context: GraphExtractionContext,
) -> tuple[EntityOccurrence, ...]:
    occurrences: list[EntityOccurrence] = []
    for field_name, extraction_method in FRONTMATTER_RELATIONSHIP_METHODS.items():
        for raw_target in _frontmatter_values(document.frontmatter.get(field_name)):
            target = context.resolve_local_document_link(source_path=document.path, raw_target=raw_target)
            if target is None:
                continue
            occurrences.append(
                _document_entity(
                    chunk=chunk,
                    document=target,
                    extraction_method=extraction_method,
                    use_evidence_heading=False,
                )
            )
    for revisit_value in _frontmatter_values(document.frontmatter.get("revisit_when")):
        occurrences.append(
            _concept_entity(
                chunk=chunk,
                name=revisit_value,
                confidence=0.8,
                extraction_method="frontmatter-revisit-when-concept-v1",
            )
        )
    return tuple(occurrences)


def _local_links(text: str) -> tuple[ParsedLocalLink, ...]:
    links: list[ParsedLocalLink] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        links.append(ParsedLocalLink(target=match.group(2).strip(), label=match.group(1).strip()))
    for match in WIKI_LINK_PATTERN.finditer(text):
        raw = match.group(1).strip()
        target, _, label = raw.partition("|")
        links.append(ParsedLocalLink(target=target.strip(), label=(label or target).strip()))
    return tuple(links)


def _dedupe_occurrences(occurrences: list[EntityOccurrence]) -> tuple[EntityOccurrence, ...]:
    deduped: dict[tuple[str, str, str, str, str, str], EntityOccurrence] = {}
    for occurrence in occurrences:
        dedupe_key = (
            *entity_occurrence_key(occurrence),
            occurrence.chunk_id,
            occurrence.extraction_method,
        )
        deduped.setdefault(dedupe_key, occurrence)
    return tuple(sorted(deduped.values(), key=lambda item: (*entity_occurrence_key(item), item.extraction_method)))


def _concept_entity(
    *,
    chunk: ChunkSnapshot,
    name: str,
    confidence: float,
    extraction_method: str,
) -> EntityOccurrence:
    stripped_name = name.strip().removeprefix("#").strip()
    return EntityOccurrence(
        vault_id=chunk.vault_id,
        entity_type="Concept",
        name=stripped_name,
        normalized_name=normalize_entity_name(stripped_name),
        aliases=(),
        canonical_path=None,
        evidence_vault_id=chunk.vault_id,
        document_id=chunk.document_id,
        chunk_id=chunk.chunk_id,
        content_hash=chunk.content_hash,
        section=chunk.section,
        anchor=chunk.anchor,
        path=chunk.path,
        excerpt=_excerpt(chunk.text),
        confidence=confidence,
        extraction_method=extraction_method,
    )


def _frontmatter_tags(document: DocumentSnapshot) -> tuple[str, ...]:
    tags = tuple(
        tag.strip().removeprefix("#").strip()
        for tag in _frontmatter_values(document.frontmatter.get("tags"))
        if tag.strip().removeprefix("#").strip()
    )
    return tuple(dict.fromkeys(tags))


def _frontmatter_values(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, list | tuple):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _scalar_frontmatter(document: DocumentSnapshot, field_name: str) -> str | None:
    value = document.frontmatter.get(field_name)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _generic_heading(value: str) -> bool:
    return normalize_entity_name(value) in GENERIC_HEADINGS


def _excerpt(text: str) -> str | None:
    stripped = " ".join(text.split())
    return stripped[:240] if stripped else None


def _link_is_external_or_anchor(target: str) -> bool:
    stripped = target.strip()
    return not stripped or stripped.startswith("#") or "://" in stripped or stripped.startswith("mailto:")
