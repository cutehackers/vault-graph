from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import NoReturn

from vault_graph.ingestion.document_normalizer import ChunkSnapshot, DocumentSnapshot
from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError
from vault_graph.mcp.mcp_resources import McpResourceBody
from vault_graph.mcp.mcp_uri import McpResourceUri
from vault_graph.storage.interfaces.metadata_store import EvidenceReference, MetadataStore


@dataclass(frozen=True)
class MetadataResourceRead:
    document: DocumentSnapshot
    chunks: tuple[ChunkSnapshot, ...]
    evidence: tuple[EvidenceReference, ...]
    warnings: tuple[McpErrorPayload, ...]


class MetadataResourceReader:
    def __init__(self, *, catalog: VaultCatalog, metadata_store: MetadataStore) -> None:
        self._catalog = catalog
        self._metadata_store = metadata_store

    def read_document(self, uri: McpResourceUri) -> McpResourceBody:
        return self._read_by_path(resource_kind="document", uri=uri)

    def read_page(self, uri: McpResourceUri) -> McpResourceBody:
        return self._read_by_path(resource_kind="page", uri=uri, classifier=lambda document: _is_page(document))

    def read_source(self, uri: McpResourceUri) -> McpResourceBody:
        return self._read_by_document_id(resource_kind="source", uri=uri, classifier=_is_source)

    def read_decision(self, uri: McpResourceUri) -> McpResourceBody:
        return self._read_by_document_id(resource_kind="decision", uri=uri, classifier=_is_decision)

    def read_issue(self, uri: McpResourceUri) -> McpResourceBody:
        return self._read_by_document_id(resource_kind="issue", uri=uri, classifier=_is_issue)

    def _read_by_path(
        self,
        *,
        resource_kind: str,
        uri: McpResourceUri,
        classifier: Callable[[DocumentSnapshot], bool] | None = None,
    ) -> McpResourceBody:
        vault_id = _required_value(uri.vault_id)
        path = _required_value(uri.value)
        state = self._metadata_store.document_state(vault_id, path)
        if state.document_id is None or state.is_tombstoned:
            _raise_not_found(uri, f"document resource not found: {vault_id}:{path}")
        document = self._metadata_store.resolve_document(state.document_id)
        if document is None or document.vault_id != vault_id:
            _raise_not_found(uri, f"document resource not found: {vault_id}:{path}")
        if classifier is not None and not classifier(document):
            _raise_not_found(uri, f"document classification does not match resource kind: {resource_kind}")
        return self._render_resource(resource_kind=resource_kind, uri=uri, document=document)

    def _read_by_document_id(
        self,
        *,
        resource_kind: str,
        uri: McpResourceUri,
        classifier: Callable[[DocumentSnapshot], bool],
    ) -> McpResourceBody:
        vault_id = _required_value(uri.vault_id)
        document_id = _required_value(uri.value)
        document = self._metadata_store.resolve_document(document_id)
        if document is None or document.vault_id != vault_id:
            _raise_not_found(uri, f"document resource not found: {vault_id}:{document_id}")
        if not classifier(document):
            _raise_not_found(uri, f"document classification does not match resource kind: {resource_kind}")
        return self._render_resource(resource_kind=resource_kind, uri=uri, document=document)

    def _render_resource(
        self,
        *,
        resource_kind: str,
        uri: McpResourceUri,
        document: DocumentSnapshot,
    ) -> McpResourceBody:
        chunks = self._metadata_store.list_document_chunks(
            vault_id=document.vault_id,
            document_id=document.document_id,
        )
        evidence: list[EvidenceReference] = []
        warnings: list[McpErrorPayload] = []
        for chunk in chunks:
            resolved = self._metadata_store.resolve_chunk_evidence(
                vault_id=chunk.vault_id,
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
            )
            if resolved is None:
                warnings.append(
                    _warning(
                        code="missing_evidence",
                        message=f"missing evidence for chunk: {chunk.chunk_id}",
                        affected_vault_ids=(chunk.vault_id,),
                        recovery_hint="Re-run vg index for the selected Vault.",
                    )
                )
            else:
                evidence.append(resolved)
        if not chunks:
            warnings.append(
                _warning(
                    code="missing_evidence",
                    message=f"document has no current chunks: {document.document_id}",
                    affected_vault_ids=(document.vault_id,),
                    recovery_hint="Re-run vg index for the selected Vault.",
                )
            )
        return McpResourceBody(
            uri=uri.normalized_uri,
            content_mime_type="text/markdown",
            text=_render_markdown(chunks),
            metadata=_document_metadata(
                document=document,
                resource_kind=resource_kind,
                chunks=chunks,
                evidence=tuple(evidence),
            ),
            warnings=tuple(warnings),
        )


def _render_markdown(chunks: tuple[ChunkSnapshot, ...]) -> str:
    rendered = ""
    for chunk in chunks:
        if not rendered:
            rendered = chunk.text
        elif rendered.endswith("\n\n") or chunk.text.startswith("\n\n"):
            rendered += chunk.text
        else:
            rendered += "\n\n" + chunk.text
    return rendered


def _document_metadata(
    *,
    document: DocumentSnapshot,
    resource_kind: str,
    chunks: tuple[ChunkSnapshot, ...],
    evidence: tuple[EvidenceReference, ...],
) -> dict[str, object]:
    return {
        "vault_id": document.vault_id,
        "document_id": document.document_id,
        "path": document.path,
        "resource_kind": resource_kind,
        "document_kind": document.kind,
        "frontmatter_hash": document.frontmatter_hash,
        "content_hash": document.content_hash,
        "raw_sha256": document.raw_sha256,
        "parser_version": document.parser_version,
        "chunker_version": chunks[0].chunker_version if chunks else None,
        "metadata_index_revision": document.index_revision,
        "vault_revision": document.vault_revision,
        "chunk_count": len(chunks),
        "evidence_refs": [_evidence_dict(ref) for ref in evidence],
    }


def _evidence_dict(evidence: EvidenceReference) -> dict[str, object]:
    return {
        "vault_id": evidence.vault_id,
        "document_id": evidence.document_id,
        "chunk_id": evidence.chunk_id,
        "path": evidence.path,
        "section": evidence.section,
        "anchor": evidence.anchor,
        "content_hash": evidence.content_hash,
        "raw_sha256": evidence.raw_sha256,
        "metadata_index_revision": evidence.metadata_index_revision,
        "vault_revision": evidence.vault_revision,
    }


def _warning(
    *,
    code: str,
    message: str,
    affected_vault_ids: tuple[str, ...],
    recovery_hint: str | None = None,
) -> McpErrorPayload:
    return McpErrorPayload(
        code=code,
        message=message,
        severity="warning",
        affected_vault_ids=affected_vault_ids,
        recovery_hint=recovery_hint,
    )


def _raise_not_found(uri: McpResourceUri, message: str) -> NoReturn:
    raise McpProtocolError(
        kind="not_found",
        payload=McpErrorPayload(
            code="resource_not_found",
            message=message,
            severity="error",
            affected_vault_ids=(uri.vault_id,) if uri.vault_id else (),
            recovery_hint="Use a resource URI returned by search, context pack, or graph tools.",
        ),
    )


def _is_page(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/")


def _is_source(document: DocumentSnapshot) -> bool:
    return (
        document.path.startswith(("raw/", "docs/", "scratch/reports/"))
        or str(document.frontmatter.get("type", "")) == "source"
    )


def _is_decision(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/decisions/") or str(document.frontmatter.get("type", "")) == "decision"


def _is_issue(document: DocumentSnapshot) -> bool:
    return document.path.startswith("wiki/issues/") or str(document.frontmatter.get("type", "")) == "issue"


def _required_value(value: str | None) -> str:
    if value is None:
        raise AssertionError("resource value is required")
    return value
