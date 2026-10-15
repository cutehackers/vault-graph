"""Select a generation's graph backend without changing it during reads."""

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Literal, cast

from vault_graph.errors import GraphStoreUnavailable
from vault_graph.storage.interfaces.graph_store import GraphStore
from vault_graph.storage.interfaces.metadata_store import MetadataStore
from vault_graph.storage.local.sqlite_graph_store import SQLiteGraphStore
from vault_graph.vault_scope.catalog_service import CatalogService

type GraphBackend = Literal["legacy", "document"]


def document_store_path(catalog_service: CatalogService) -> Path:
    return catalog_service.graph_path.parent / "document-store"


def selected_graph_backend(catalog_service: CatalogService) -> GraphBackend:
    marker = catalog_service.graph_path.parent / "backend.json"
    if marker.is_symlink() or any(parent.is_symlink() for parent in marker.parents):
        raise GraphStoreUnavailable("graph backend path cannot cross a symlink")
    if not marker.exists():
        path = document_store_path(catalog_service)
        if path.exists() or path.is_symlink():
            raise GraphStoreUnavailable("graph backend selector is missing for a migrated generation")
        return "legacy"
    try:
        fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024:
                raise ValueError("backend selector must be a bounded regular file")
            payload = json.loads(stream.read(1025))
        if not isinstance(payload, dict) or payload != {"version": 1, "backend": payload.get("backend")}:
            raise ValueError("invalid backend selector")
        if payload["backend"] not in ("legacy", "document"):
            raise ValueError("unknown graph backend")
        return cast(GraphBackend, payload["backend"])
    except (OSError, ValueError) as exc:
        raise GraphStoreUnavailable("graph backend selector is unavailable") from exc


def write_graph_backend_selection(catalog_service: CatalogService, backend: GraphBackend) -> None:
    """Persist selection in a private generation before publishing that generation."""
    marker = catalog_service.graph_path.parent / "backend.json"
    catalog_service.assert_graph_home_write_target_safe(target_path=marker, catalog=catalog_service.load_catalog())
    if marker.is_symlink() or any(parent.is_symlink() for parent in marker.parents):
        raise GraphStoreUnavailable("graph backend path cannot cross a symlink")
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=marker.parent, delete=False) as stream:
            temporary = stream.name
            json.dump({"version": 1, "backend": backend}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
        fd = os.open(marker.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary is not None and os.path.exists(temporary):
            os.unlink(temporary)


def open_graph_store(
    catalog_service: CatalogService,
    *,
    metadata_store: MetadataStore,
    writable: bool = False,
    backend: GraphBackend | None = None,
) -> GraphStore:
    selected = backend or selected_graph_backend(catalog_service)
    if selected == "legacy":
        return (
            SQLiteGraphStore.open_writable(catalog_service.graph_path)
            if writable
            else SQLiteGraphStore.open_read_only(catalog_service.graph_path)
        )
    from graph_document import GraphLimits, ReadLimits

    from vault_graph.storage.local.document_graph_store import DocumentGraphStore

    # Admission limits bound hydration as well as extraction. They are capacity
    # limits, not a latency guarantee for inputs larger than measured workloads.
    graph_limits = GraphLimits(10000, 16 * 1024 * 1024, 256 * 1024 * 1024, 100000, 200000, 500000, 4096)
    read_limits = ReadLimits(100000, 200000, 500000, 10000, 256 * 1024 * 1024)
    path = document_store_path(catalog_service)
    if writable:
        catalog_service.assert_graph_home_write_target_safe(target_path=path, catalog=catalog_service.load_catalog())
    opener = DocumentGraphStore.open_writable if writable else DocumentGraphStore.open_read_only
    return opener(path, metadata_store=metadata_store, graph_limits=graph_limits, read_limits=read_limits)
