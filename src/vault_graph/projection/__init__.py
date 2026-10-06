"""Runtime graph projection contracts and local adapters."""

from typing import TYPE_CHECKING

from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
    DEFAULT_GRAPH_RELATED_DEPTH,
    DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT,
    DEFAULT_GRAPH_RESULT_LIMIT,
    DEFAULT_GRAPH_TARGET_LIMIT,
    GRAPH_PROJECTION_VERSION,
    MAX_GRAPH_PROJECTION_DEPTH,
    MAX_GRAPH_PROJECTION_EDGE_LIMIT,
    MAX_GRAPH_RESULT_LIMIT,
    GraphPath,
    GraphProjection,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
    GraphProjectionResult,
)

if TYPE_CHECKING:
    from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection
    from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter

__all__ = [
    "DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT",
    "DEFAULT_GRAPH_RELATED_DEPTH",
    "DEFAULT_GRAPH_RELATIONSHIP_READ_LIMIT",
    "DEFAULT_GRAPH_RESULT_LIMIT",
    "DEFAULT_GRAPH_TARGET_LIMIT",
    "GRAPH_PROJECTION_VERSION",
    "MAX_GRAPH_PROJECTION_DEPTH",
    "MAX_GRAPH_PROJECTION_EDGE_LIMIT",
    "MAX_GRAPH_RESULT_LIMIT",
    "GraphPath",
    "GraphProjection",
    "GraphProjectionEdge",
    "GraphProjectionInput",
    "GraphProjectionNode",
    "GraphProjectionResult",
    "RustworkxGraphProjection",
    "VaultGraphProjectionAdapter",
]


def __getattr__(name: str) -> object:
    if name == "RustworkxGraphProjection":
        from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection

        return RustworkxGraphProjection
    if name == "VaultGraphProjectionAdapter":
        from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter

        return VaultGraphProjectionAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
