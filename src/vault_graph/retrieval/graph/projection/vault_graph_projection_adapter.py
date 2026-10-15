"""Keep Vault projection policy outside the independent graph-search engine."""

from dataclasses import dataclass
from typing import Literal

from graph_search import Edge, GraphLimits, GraphSearchError, GraphSnapshot, PathOptions, search_paths

from vault_graph.errors import GraphStoreError
from vault_graph.retrieval.graph.projection.graph_projection import (
    GRAPH_PROJECTION_VERSION,
    GraphPath,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionResult,
)
from vault_graph.retrieval.graph.projection.rustworkx_projection import (
    _dedupe_nodes,
    _edge_allowed,
    _edge_sort_key,
    _explain_path,
    _node_sort_key,
    _path_sort_key,
    _projection_build_id,
    _score_path,
)

Identity = tuple[str, str]
LegacyPathKey = tuple[Identity, Identity, tuple[str, ...]]


@dataclass(frozen=True)
class ProjectionExecutionLimits:
    """Optional caller admission limits; default execution covers every legacy request."""

    max_nodes: int
    max_edge_examinations: int
    max_paths: int
    max_dedup_paths: int
    max_input_relationships: int
    max_original_id_bytes: int
    max_total_original_id_bytes: int

    def __post_init__(self) -> None:
        for value in (
            self.max_nodes,
            self.max_edge_examinations,
            self.max_paths,
            self.max_dedup_paths,
            self.max_input_relationships,
            self.max_original_id_bytes,
            self.max_total_original_id_bytes,
        ):
            if type(value) is not int or value < 0:
                raise GraphStoreError("projection execution limits must be nonnegative integers")


class VaultGraphProjectionAdapter:
    def __init__(self, *, execution_limits: ProjectionExecutionLimits | None = None) -> None:
        self._execution_limits = execution_limits

    def project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        try:
            return self._project(request)
        except GraphSearchError as exc:
            raise GraphStoreError("graph projection traversal failed") from exc
        except KeyError as exc:
            raise GraphStoreError("graph projection mapping failed") from exc

    def _project(self, request: GraphProjectionInput) -> GraphProjectionResult:
        if self._execution_limits is not None:
            _admit_input(request, self._execution_limits)
        nodes = _dedupe_nodes(request.nodes)
        ordered = tuple(sorted(nodes, key=_node_sort_key))
        node_ids = tuple(f"n{index:012d}" for index in range(len(ordered)))
        id_by_identity = {
            (node.vault_id, node.entity_id): node_id for node, node_id in zip(ordered, node_ids, strict=True)
        }
        node_by_id = dict(zip(node_ids, ordered, strict=True))
        filtered = tuple(
            edge
            for edge in sorted(request.relationships, key=_edge_sort_key)
            if _edge_allowed(edge=edge, request=request)
            and (edge.source_vault_id, edge.source_entity_id) in id_by_identity
            and (edge.target_vault_id, edge.target_entity_id) in id_by_identity
        )
        selected = filtered[: request.edge_limit]
        core_edges = tuple(
            Edge(
                f"e{index:012d}",
                id_by_identity[(edge.source_vault_id, edge.source_entity_id)],
                id_by_identity[(edge.target_vault_id, edge.target_entity_id)],
            )
            for index, edge in enumerate(selected)
        )
        edge_by_id = {edge.id: original for edge, original in zip(core_edges, selected, strict=True)}
        a = 2 * len(selected)
        examination_bound = a + a * a
        path_bound = max(1, examination_bound)
        limits = self._execution_limits
        if limits is not None:
            if len(nodes) > limits.max_nodes:
                raise GraphStoreError("graph_projection_budget_exceeded: nodes")
            examination_bound = min(examination_bound, limits.max_edge_examinations)
            path_bound = max(1, min(path_bound, limits.max_paths))
        ids = (*node_ids, *(edge.id for edge in core_edges))
        graph = GraphSnapshot.build(
            node_ids=node_ids,
            edges=core_edges,
            limits=GraphLimits(len(nodes), max(1, len(selected)), max(map(len, ids)), sum(map(len, ids)) * 3),
        )
        ranks = _legacy_neighbor_ranks(core_edges, selected, request.direction)
        direction: Literal["outbound", "inbound", "both"] = {
            "out": "outbound",
            "in": "inbound",
            "both": "both",
        }[request.direction]  # type: ignore[assignment]
        seeds = {(seed.vault_id, seed.entity_id) for seed in request.seeds}
        chosen: dict[LegacyPathKey, tuple[tuple[int, ...], GraphPath]] = {}
        total_examinations = 0
        total_paths = 0
        for seed_rank, seed in enumerate(sorted(request.seeds, key=_node_sort_key)):
            seed_identity = (seed.vault_id, seed.entity_id)
            remaining_examinations = (
                examination_bound if limits is None else max(0, limits.max_edge_examinations - total_examinations)
            )
            with search_paths(
                graph,
                source_id=id_by_identity[seed_identity],
                options=PathOptions(direction, int(request.max_depth), path_bound, remaining_examinations),
            ) as traversal:
                for path in traversal:
                    total_paths += 1
                    if limits is not None and total_paths > limits.max_paths:
                        raise GraphStoreError("graph_projection_budget_exceeded: paths")
                    target = node_by_id[path.node_ids[-1]]
                    target_identity = (target.vault_id, target.entity_id)
                    if target_identity in seeds:
                        continue
                    original_edges = tuple(edge_by_id[step.edge_id] for step in path.steps)
                    ordinal = (seed_rank, *(ranks[(step.from_id, step.edge_id, step.reversed)] for step in path.steps))
                    key = (seed_identity, target_identity, tuple(edge.relationship_id for edge in original_edges))
                    previous = chosen.get(key)
                    if previous is None or ordinal < previous[0]:
                        chosen[key] = (
                            ordinal,
                            GraphPath(
                                seed,
                                target,
                                original_edges,
                                len(original_edges),
                                _score_path(original_edges),
                                _explain_path(original_edges),
                            ),
                        )
                    if limits is not None and len(chosen) > limits.max_dedup_paths:
                        raise GraphStoreError("graph_projection_budget_exceeded: deduplication")
            summary = traversal.summary
            if summary is None or summary.stop_reason != "completed":
                raise GraphStoreError("graph_projection_budget_exceeded: incomplete traversal")
            total_examinations += summary.examined_edges
            if limits is not None and total_examinations > limits.max_edge_examinations:
                raise GraphStoreError("graph_projection_budget_exceeded: examinations")
        paths = tuple(
            value[1] for value in sorted(chosen.values(), key=lambda value: (_path_sort_key(value[1]), value[0]))
        )
        return GraphProjectionResult(
            projection_build_id=_projection_build_id(request=request, nodes=nodes),
            graph_projection_version=GRAPH_PROJECTION_VERSION,
            source_graph_revisions=tuple(sorted(request.source_graph_revisions)),
            node_count=len(nodes),
            edge_count=len(selected),
            truncated=len(filtered) > len(selected) or len(paths) > request.limit,
            paths=paths[: request.limit],
        )


def _admit_input(request: GraphProjectionInput, limits: ProjectionExecutionLimits) -> None:
    if len(request.nodes) > limits.max_nodes or len(request.seeds) > limits.max_nodes:
        raise GraphStoreError("graph_projection_budget_exceeded: input nodes or seeds")
    if len(request.relationships) > limits.max_input_relationships:
        raise GraphStoreError("graph_projection_budget_exceeded: input relationships")
    total = 0
    for node in (*request.nodes, *request.seeds):
        for identifier in (node.vault_id, node.entity_id):
            total = _count_identifier(identifier, total, limits)
    for edge in request.relationships:
        for identifier in (
            edge.source_vault_id,
            edge.source_entity_id,
            edge.target_vault_id,
            edge.target_entity_id,
            edge.relationship_id,
        ):
            total = _count_identifier(identifier, total, limits)


def _count_identifier(identifier: str, total: int, limits: ProjectionExecutionLimits) -> int:
    if len(identifier) > limits.max_original_id_bytes:
        raise GraphStoreError("graph_projection_budget_exceeded: original ID bytes")
    size = len(identifier.encode("utf-8"))
    total += size
    if total > limits.max_total_original_id_bytes:
        raise GraphStoreError("graph_projection_budget_exceeded: total original ID bytes")
    if size > limits.max_original_id_bytes:
        raise GraphStoreError("graph_projection_budget_exceeded: original ID bytes")
    return total


def _legacy_neighbor_ranks(
    edges: tuple[Edge, ...],
    originals: tuple[GraphProjectionEdge, ...],
    direction: str,
) -> dict[tuple[str, str, bool], int]:
    """Reproduce rustworkx 0.17 incident-order ties, without traversing a second graph."""
    outgoing: dict[str, list[tuple[str, Edge, GraphProjectionEdge, bool]]] = {}
    incoming: dict[str, list[tuple[str, Edge, GraphProjectionEdge, bool]]] = {}
    for edge, original in reversed(tuple(zip(edges, originals, strict=True))):
        outgoing.setdefault(edge.source_id, []).append((edge.target_id, edge, original, False))
        incoming.setdefault(edge.target_id, []).append((edge.source_id, edge, original, True))
    result: dict[tuple[str, str, bool], int] = {}
    for node_id in outgoing.keys() | incoming.keys():
        adjacent: list[tuple[str, Edge, GraphProjectionEdge, bool]] = []
        if direction in ("out", "both"):
            adjacent.extend(outgoing.get(node_id, ()))
        if direction in ("in", "both"):
            adjacent.extend(incoming.get(node_id, ()))
        adjacent.sort(key=lambda item: (_edge_sort_key(item[2]), item[0]))
        for rank, (_, edge, _, reversed_step) in enumerate(adjacent):
            result[(node_id, edge.id, reversed_step)] = rank
    return result
