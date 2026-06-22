from __future__ import annotations

from dataclasses import dataclass

from vault_graph.errors import MemoryProjectionError
from vault_graph.ingestion.document_normalizer import DocumentSnapshot
from vault_graph.ingestion.vault_catalog import QueryScope
from vault_graph.memory.memory_models import (
    MemoryDocumentResourceKind,
    MemoryEvidenceRef,
    MemoryWarning,
)
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore


@dataclass(frozen=True)
class MemoryHeadingRef:
    chunk_id: str
    section: str
    anchor: str | None


@dataclass(frozen=True)
class MemoryDocumentRead:
    document: DocumentSnapshot
    evidence: tuple[MemoryEvidenceRef, ...]
    headings: tuple[MemoryHeadingRef, ...]
    body_excerpt: str | None
    warnings: tuple[MemoryWarning, ...]


class MemorySourceReader:
    def __init__(self, *, metadata_store: MetadataStore) -> None:
        self._metadata_store = metadata_store

    def list_documents(self, *, scope: QueryScope) -> tuple[DocumentSnapshot, ...]:
        return self._metadata_store.list_documents(scope)

    def read_document(
        self,
        *,
        document: DocumentSnapshot,
        max_evidence_chunks: int = 3,
        preferred_chunk_ids: tuple[str, ...] = (),
    ) -> MemoryDocumentRead:
        if max_evidence_chunks < 1:
            raise MemoryProjectionError("invalid_memory_evidence_limit: max_evidence_chunks must be positive")
        chunks = self._metadata_store.list_document_chunks(vault_id=document.vault_id, document_id=document.document_id)
        headings = tuple(
            MemoryHeadingRef(chunk_id=chunk.chunk_id, section=chunk.section, anchor=chunk.anchor)
            for chunk in chunks
            if chunk.section
        )
        warnings: list[MemoryWarning] = []
        if not chunks:
            warnings.append(
                _warning(
                    code="document_has_no_chunks",
                    message=f"document has no indexed chunks: {document.document_id}",
                    affected_vault_ids=(document.vault_id,),
                    recovery_hint="Run vg index for the selected Vault.",
                )
            )
        preferred_ids = set(preferred_chunk_ids)
        preferred = tuple(chunk for chunk in chunks if chunk.chunk_id in preferred_ids)
        remaining = tuple(chunk for chunk in chunks if chunk.chunk_id not in preferred_ids)
        selected = (*preferred, *remaining)[:max_evidence_chunks]
        evidence: list[MemoryEvidenceRef] = []
        for chunk in selected:
            resolved = self._metadata_store.resolve_chunk_evidence(
                vault_id=chunk.vault_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
            )
            if resolved is None:
                warnings.append(
                    _warning(
                        code="unresolved_evidence",
                        message=f"chunk evidence could not be resolved: {chunk.chunk_id}",
                        affected_vault_ids=(chunk.vault_id,),
                        recovery_hint="Run vg index for the selected Vault.",
                    )
                )
                continue
            evidence.append(_memory_evidence_from_metadata(resolved))
        return MemoryDocumentRead(
            document=document,
            evidence=tuple(evidence),
            headings=headings,
            body_excerpt=_body_excerpt(chunks),
            warnings=tuple(warnings),
        )


def document_resource_kinds_for_document(document: DocumentSnapshot) -> tuple[MemoryDocumentResourceKind, ...]:
    kinds: list[MemoryDocumentResourceKind] = ["document"]
    if document.path.startswith("wiki/"):
        kinds.append("page")
    if _is_source(document):
        kinds.append("source")
    if _is_decision(document):
        kinds.append("decision")
    if _is_issue(document):
        kinds.append("issue")
    return tuple(kinds)


def _memory_evidence_from_metadata(evidence: EvidenceReference) -> MemoryEvidenceRef:
    return MemoryEvidenceRef(
        vault_id=evidence.vault_id,
        document_id=evidence.document_id,
        chunk_id=evidence.chunk_id,
        path=evidence.path,
        section=evidence.section,
        anchor=evidence.anchor,
        content_hash=evidence.content_hash,
        raw_sha256=evidence.raw_sha256,
        metadata_index_revision=evidence.metadata_index_revision,
        vault_revision=evidence.vault_revision,
    )


def _body_excerpt(chunks: tuple[object, ...]) -> str | None:
    for chunk in chunks:
        text = getattr(chunk, "text", "").strip()
        if text:
            return text[:280]
    return None


def _warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> MemoryWarning:
    return MemoryWarning(
        code=code,
        message=message,
        severity="warning",
        affected_vault_ids=affected_vault_ids,
        recovery_hint=recovery_hint,
    )


def _is_source(document: DocumentSnapshot) -> bool:
    return (
        document.path.startswith(("raw/", "docs/", "scratch/reports/"))
        or str(document.frontmatter.get("type", "")) == "source"
    )


def _is_decision(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/decisions/") or str(document.frontmatter.get("type", "")) == "decision"


def _is_issue(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/issues/") or str(document.frontmatter.get("type", "")) == "issue"
