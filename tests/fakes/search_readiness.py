from __future__ import annotations

from vault_graph.retrieval.search_readiness import SearchReadinessReport
from vault_graph.retrieval.search_response import SearchStoreRevision
from vault_graph.storage.interfaces.store_health import StoreHealth


def ready_report(
    *,
    vector_ok: bool = False,
    vector_stale_count: int | None = None,
    can_embed_without_download: bool = False,
    scope_key: str = "default:wiki",
) -> SearchReadinessReport:
    return SearchReadinessReport(
        metadata_health=StoreHealth(
            ok=True,
            backend="metadata",
            schema_version="v1",
            schema_compatible=True,
            message="ok",
        ),
        keyword_health=StoreHealth(
            ok=True,
            backend="keyword",
            schema_version="v1",
            schema_compatible=True,
            message="ok",
        ),
        vector_health=StoreHealth(
            ok=vector_ok,
            backend="vector",
            schema_version="v1",
            schema_compatible=vector_ok,
            message="ok" if vector_ok else "not initialized",
        ),
        vector_stale_count=vector_stale_count,
        can_embed_without_download=can_embed_without_download,
        store_revisions=(
            SearchStoreRevision(kind="metadata", revision="metadata-1", scope_key=scope_key),
            SearchStoreRevision(kind="keyword", revision="metadata-1", scope_key=scope_key),
        )
        + ((SearchStoreRevision(kind="vector", revision="vector-1", scope_key=scope_key),) if vector_ok else ()),
    )
