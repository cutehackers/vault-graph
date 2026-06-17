from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NoReturn, Protocol

from vault_graph.ingestion.vault_catalog import VaultCatalog
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_errors import McpErrorPayload, McpProtocolError, map_exception_to_mcp_error
from vault_graph.mcp.mcp_service_factory import McpServiceFactory, McpServices
from vault_graph.mcp.mcp_uri import McpResourceUri, parse_mcp_resource_uri

if TYPE_CHECKING:
    from vault_graph.mcp.graph_resource_reader import GraphResourceReader
    from vault_graph.mcp.metadata_resource_reader import MetadataResourceReader

McpResourceContentMime = Literal["text/markdown", "application/json"]


@dataclass(frozen=True)
class McpResourceRequest:
    uri: str


@dataclass(frozen=True)
class McpResourceBody:
    uri: str
    content_mime_type: McpResourceContentMime
    text: str
    metadata: dict[str, object]
    warnings: tuple[McpErrorPayload, ...] = ()

    def to_json_dict(self) -> dict[str, object]:
        return {
            "uri": self.uri,
            "content_mime_type": self.content_mime_type,
            "text": self.text,
            "metadata": self.metadata,
            "warnings": [
                {
                    "code": warning.code,
                    "message": warning.message,
                    "severity": warning.severity,
                    "affected_vault_ids": list(warning.affected_vault_ids),
                    "recovery_hint": warning.recovery_hint,
                }
                for warning in self.warnings
            ],
        }


class McpResourceServer(Protocol):
    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


class GraphResourceReaderFactory(Protocol):
    def get(self) -> GraphResourceReader: ...


class McpResourceRegistry:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        metadata_reader: MetadataResourceReader,
        graph_reader_factory: GraphResourceReaderFactory,
        context_pack_cache: ContextPackResourceCache,
        current_context_reader: CurrentContextResourceReader,
    ) -> None:
        self._catalog = catalog
        self._metadata_reader = metadata_reader
        self._graph_reader_factory = graph_reader_factory
        self._context_pack_cache = context_pack_cache
        self._current_context_reader = current_context_reader

    def read(self, request: McpResourceRequest) -> McpResourceBody:
        uri = parse_mcp_resource_uri(request.uri, catalog=self._catalog)
        try:
            return self._read_parsed(uri)
        except McpProtocolError:
            raise
        except Exception as exc:
            affected = (uri.vault_id,) if uri.vault_id else ()
            raise map_exception_to_mcp_error(exc, affected_vault_ids=affected) from exc

    def read_json(self, request: McpResourceRequest) -> str:
        body = self.read(request)
        return json.dumps(body.to_json_dict(), sort_keys=True, ensure_ascii=False, indent=2) + "\n"

    def _read_parsed(self, uri: McpResourceUri) -> McpResourceBody:
        if uri.kind == "document":
            return self._metadata_reader.read_document(uri)
        if uri.kind == "page":
            return self._metadata_reader.read_page(uri)
        if uri.kind == "source":
            return self._metadata_reader.read_source(uri)
        if uri.kind == "decision":
            return self._metadata_reader.read_decision(uri)
        if uri.kind == "issue":
            return self._metadata_reader.read_issue(uri)
        if uri.kind == "graph_entity":
            return self._graph_reader_factory.get().read_entity(uri)
        if uri.kind == "concept":
            return self._graph_reader_factory.get().read_concept(uri)
        if uri.kind == "context_current":
            return self._current_context_reader.read_current_context(uri)
        if uri.kind == "timeline_recent":
            return self._current_context_reader.read_recent_timeline(uri)
        if uri.kind == "context_pack":
            return self._read_context_pack(uri)
        raise AssertionError(f"unsupported resource kind: {uri.kind}")

    def _read_context_pack(self, uri: McpResourceUri) -> McpResourceBody:
        pack_id = _required_value(uri.value)
        cached = self._context_pack_cache.get(pack_id)
        if cached is None:
            _raise_resource_not_found(
                message=f"context pack resource not found: {pack_id}",
                recovery_hint="Call build_context_pack again to regenerate this in-process resource.",
            )
        return McpResourceBody(
            uri=uri.normalized_uri,
            content_mime_type="application/json",
            text=cached.pack_json,
            metadata={
                "pack_id": cached.pack_id,
                "generated_at": cached.generated_at,
                "requested_scope_key": cached.requested_scope_key,
                "actual_scope_keys": list(cached.actual_scope_keys),
                "cached_at": cached.cached_at,
            },
        )


class CurrentContextResourceReader:
    def __init__(
        self,
        *,
        catalog: VaultCatalog,
        service_factory: McpServiceFactory,
        context_pack_cache: ContextPackResourceCache,
    ) -> None:
        self._catalog = catalog
        self._service_factory = service_factory
        self._context_pack_cache = context_pack_cache

    def read_current_context(self, uri: McpResourceUri) -> McpResourceBody:
        vault_id = _required_value(uri.vault_id)
        entry = self._catalog.resolve(vault_id)
        warnings: list[McpErrorPayload] = []
        metadata_health: dict[str, object] = {"ok": False, "message": "unavailable"}
        search_health: dict[str, object] = {"ok": False, "message": "unavailable"}
        graph_health: dict[str, object] = {"ok": False, "message": "unavailable"}
        try:
            report = self._service_factory.open_status_service().status(
                scope=self._catalog.scope_for_vault_ids((vault_id,)),
            )
            metadata_health = {
                "ok": report.metadata_ok,
                "schema_compatible": report.metadata_schema_compatible,
                "message": report.metadata_message,
            }
            search_health = {
                "vector_ok": report.vector_ok,
                "vector_backend": report.vector_backend,
                "vector_schema_compatible": report.vector_schema_compatible,
                "vector_message": report.vector_message,
            }
            graph_health = {
                "backend_available": report.graph_readiness.backend_available,
                "schema_compatible": report.graph_readiness.schema_compatible,
                "freshness": report.graph_readiness.freshness,
                "message": report.graph_readiness.recovery_hint,
            }
        except Exception as exc:
            warnings.append(
                McpErrorPayload(
                    code="resource_not_available",
                    message=str(exc),
                    severity="warning",
                    affected_vault_ids=(vault_id,),
                    recovery_hint="Run vg status for detailed backend readiness.",
                )
            )
        payload: dict[str, object] = {
            "vault_id": entry.vault_id,
            "display_name": entry.display_name,
            "active": entry.vault_id == self._catalog.active_vault_id,
            "content_scopes": list(entry.content_scopes),
            "state_namespace": entry.state_namespace,
            "metadata_health": metadata_health,
            "search_health": search_health,
            "graph_health": graph_health,
            "context_pack_cache": {
                "size": len(self._context_pack_cache),
                "max_entries": self._context_pack_cache.max_entries,
            },
            "warnings": [_warning_to_dict(warning) for warning in warnings],
        }
        return McpResourceBody(
            uri=uri.normalized_uri,
            content_mime_type="application/json",
            text=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
            metadata=payload,
            warnings=tuple(warnings),
        )

    def read_recent_timeline(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available(
            affected_vault_ids=(uri.vault_id,) if uri.vault_id else (),
            message="Timeline projection resources are not available in Phase 5B.",
            recovery_hint="Timeline projection resources are planned for Phase 6.",
        )


def register_mcp_resources(
    server: McpResourceServer,
    *,
    services: McpServices,
    service_factory: McpServiceFactory,
    context_pack_cache: ContextPackResourceCache,
) -> McpResourceRegistry:
    from vault_graph.mcp.metadata_resource_reader import MetadataResourceReader

    registry = McpResourceRegistry(
        catalog=services.catalog,
        metadata_reader=MetadataResourceReader(catalog=services.catalog, metadata_store=services.metadata_store),
        graph_reader_factory=LazyGraphResourceReaderFactory(service_factory=service_factory),
        context_pack_cache=context_pack_cache,
        current_context_reader=CurrentContextResourceReader(
            catalog=services.catalog,
            service_factory=service_factory,
            context_pack_cache=context_pack_cache,
        ),
    )

    @server.resource("vault://{vault_id}/documents/{path}", mime_type="application/json")
    def read_document_resource(vault_id: str, path: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/documents/{path}"))

    @server.resource("vault://{vault_id}/pages/{path}", mime_type="application/json")
    def read_page_resource(vault_id: str, path: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/pages/{path}"))

    @server.resource("vault://{vault_id}/sources/{id}", mime_type="application/json")
    def read_source_resource(vault_id: str, id: str) -> str:  # noqa: A002
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/sources/{id}"))

    @server.resource("vault://{vault_id}/concepts/{name}", mime_type="application/json")
    def read_concept_resource(vault_id: str, name: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/concepts/{name}"))

    @server.resource("vault://{vault_id}/decisions/{id}", mime_type="application/json")
    def read_decision_resource(vault_id: str, id: str) -> str:  # noqa: A002
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/decisions/{id}"))

    @server.resource("vault://{vault_id}/issues/{id}", mime_type="application/json")
    def read_issue_resource(vault_id: str, id: str) -> str:  # noqa: A002
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/issues/{id}"))

    @server.resource("vault://{vault_id}/timeline/recent", mime_type="application/json")
    def read_recent_timeline_resource(vault_id: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/timeline/recent"))

    @server.resource("vault://{vault_id}/context/current", mime_type="application/json")
    def read_current_context_resource(vault_id: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/context/current"))

    @server.resource("vault://{vault_id}/graph/entities/{id}", mime_type="application/json")
    def read_graph_entity_resource(vault_id: str, id: str) -> str:  # noqa: A002
        return registry.read_json(McpResourceRequest(uri=f"vault://{vault_id}/graph/entities/{id}"))

    @server.resource("vault://context/packs/{pack_id}", mime_type="application/json")
    def read_context_pack_resource(pack_id: str) -> str:
        return registry.read_json(McpResourceRequest(uri=f"vault://context/packs/{pack_id}"))

    return registry


class _UnavailableMetadataResourceReader:
    def read_document(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available_for_uri(uri)

    def read_page(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available_for_uri(uri)

    def read_source(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available_for_uri(uri)

    def read_decision(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available_for_uri(uri)

    def read_issue(self, uri: McpResourceUri) -> McpResourceBody:
        _raise_resource_not_available_for_uri(uri)


class LazyGraphResourceReaderFactory:
    def __init__(self, *, service_factory: McpServiceFactory) -> None:
        self._service_factory = service_factory
        self._reader: GraphResourceReader | None = None

    def get(self) -> GraphResourceReader:
        if self._reader is None:
            from vault_graph.mcp.graph_resource_reader import GraphResourceReader

            self._reader = GraphResourceReader(
                graph_resource_service=self._service_factory.open_graph_resource_service(),
            )
        return self._reader


def _raise_resource_not_available_for_uri(uri: McpResourceUri) -> NoReturn:
    _raise_resource_not_available(
        affected_vault_ids=(uri.vault_id,) if uri.vault_id else (),
        message=f"resource reader is not available for: {uri.normalized_uri}",
        recovery_hint="Complete the Phase 5B resource reader implementation.",
    )


def _raise_resource_not_found(*, message: str, recovery_hint: str | None = None) -> NoReturn:
    raise McpProtocolError(
        kind="not_found",
        payload=McpErrorPayload(
            code="resource_not_found",
            message=message,
            severity="error",
            affected_vault_ids=(),
            recovery_hint=recovery_hint,
        ),
    )


def _raise_resource_not_available(
    *,
    affected_vault_ids: tuple[str, ...],
    message: str,
    recovery_hint: str | None = None,
) -> NoReturn:
    raise _resource_not_available_error(
        affected_vault_ids=affected_vault_ids,
        message=message,
        recovery_hint=recovery_hint,
    )


def _resource_not_available_error(
    *,
    message: str,
    affected_vault_ids: tuple[str, ...] = (),
    recovery_hint: str | None = None,
) -> McpProtocolError:
    return McpProtocolError(
        kind="execution",
        payload=McpErrorPayload(
            code="resource_not_available",
            message=message,
            severity="error",
            affected_vault_ids=affected_vault_ids,
            recovery_hint=recovery_hint,
        ),
    )


def _required_value(value: str | None) -> str:
    if value is None:
        raise AssertionError("resource value is required")
    return value


def _warning_to_dict(warning: McpErrorPayload) -> dict[str, object]:
    return {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "affected_vault_ids": list(warning.affected_vault_ids),
        "recovery_hint": warning.recovery_hint,
    }
