from dataclasses import replace
from typing import Literal

import pytest

from vault_graph.errors import GraphStoreError
from vault_graph.projection.graph_projection import (
    DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
    DEFAULT_GRAPH_RESULT_LIMIT,
    GRAPH_PROJECTION_VERSION,
    GraphProjectionEdge,
    GraphProjectionInput,
    GraphProjectionNode,
)
from vault_graph.projection.rustworkx_projection import RustworkxGraphProjection


def node(vault_id: str, entity_id: str, name: str) -> GraphProjectionNode:
    return GraphProjectionNode(
        vault_id=vault_id,
        entity_id=entity_id,
        type="Concept",
        name=name,
        normalized_name=name.casefold(),
    )


def edge(
    source: GraphProjectionNode,
    target: GraphProjectionNode,
    relationship_id: str = "rel-1",
) -> GraphProjectionEdge:
    return GraphProjectionEdge(
        source_vault_id=source.vault_id,
        source_entity_id=source.entity_id,
        target_vault_id=target.vault_id,
        target_entity_id=target.entity_id,
        relationship_id=relationship_id,
        relationship_type="related_to",
        status="stated",
        confidence=0.9,
        evidence_ref_ids=("evidence-1",),
        graph_index_revision="graph-1",
    )


def projection_input(
    *,
    seeds: tuple[GraphProjectionNode, ...],
    nodes: tuple[GraphProjectionNode, ...],
    relationships: tuple[GraphProjectionEdge, ...],
    max_depth: int = 1,
    direction: Literal["out", "in", "both"] = "both",
    relationship_types: tuple[str, ...] = (),
    statuses: tuple[str, ...] = ("stated",),
    limit: int = DEFAULT_GRAPH_RESULT_LIMIT,
    edge_limit: int = DEFAULT_GRAPH_PROJECTION_EDGE_LIMIT,
) -> GraphProjectionInput:
    return GraphProjectionInput(
        seeds=seeds,
        nodes=nodes,
        relationships=relationships,
        actual_scope_keys=("default:wiki",),
        source_graph_revisions=("graph-1",),
        max_depth=max_depth,
        direction=direction,
        relationship_types=relationship_types,
        statuses=statuses,
        include_cross_vault=False,
        limit=limit,
        edge_limit=edge_limit,
    )


def test_projection_input_rejects_depth_above_phase_limit() -> None:
    source = node("default", "source", "GraphRAG")
    target = node("default", "target", "Search")

    with pytest.raises(GraphStoreError, match="unsupported graph projection depth"):
        projection_input(
            seeds=(source,),
            nodes=(source, target),
            relationships=(edge(source, target),),
            max_depth=3,
        )


def test_projection_input_requires_seeds_to_be_present_in_nodes() -> None:
    source = node("default", "source", "GraphRAG")
    target = node("default", "target", "Search")

    with pytest.raises(GraphStoreError, match="seeds must be present in nodes"):
        projection_input(
            seeds=(source,),
            nodes=(target,),
            relationships=(edge(source, target),),
        )


def test_projection_version_is_stable() -> None:
    assert GRAPH_PROJECTION_VERSION == "graph-projection-v1"


def test_rustworkx_projection_returns_depth_one_paths_in_deterministic_order() -> None:
    seed = node("default", "seed", "GraphRAG")
    high = node("default", "high", "Hybrid Retrieval")
    low = node("default", "low", "Contested Link")
    relationships = (
        edge(seed, low, "rel-low"),
        replace(edge(seed, high, "rel-high"), confidence=1.0),
    )

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, high, low),
            relationships=relationships,
            direction="out",
            limit=10,
            edge_limit=500,
        )
    )

    assert result.graph_projection_version == GRAPH_PROJECTION_VERSION
    assert result.paths[0].target.entity_id == "high"
    assert result.paths[0].score > result.paths[1].score
    assert result.projection_build_id


def test_rustworkx_projection_uses_contract_relationship_type_priority() -> None:
    seed = node("default", "seed", "GraphRAG")
    unknown = node("default", "unknown", "Unknown")
    supersedes = node("default", "supersedes", "Supersedes")
    blocks = node("default", "blocks", "Blocks")
    relationships = (
        replace(edge(seed, unknown, "rel-unknown"), relationship_type="zzz_unknown"),
        replace(edge(seed, blocks, "rel-blocks"), relationship_type="blocks"),
        replace(edge(seed, supersedes, "rel-supersedes"), relationship_type="supersedes"),
    )

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, unknown, supersedes, blocks),
            relationships=relationships,
            direction="out",
            relationship_types=(),
            limit=10,
        )
    )

    assert tuple(path.target.entity_id for path in result.paths)[:3] == ("supersedes", "blocks", "unknown")


def test_rustworkx_projection_build_id_changes_when_edge_limit_changes() -> None:
    seed = node("default", "seed", "GraphRAG")
    targets = tuple(node("default", f"target-{index}", f"Target {index}") for index in range(3))
    relationships = tuple(edge(seed, target, f"rel-{index}") for index, target in enumerate(targets))
    first = RustworkxGraphProjection().project(
        projection_input(seeds=(seed,), nodes=(seed, *targets), relationships=relationships, edge_limit=2)
    )
    second = RustworkxGraphProjection().project(
        projection_input(seeds=(seed,), nodes=(seed, *targets), relationships=relationships, edge_limit=3)
    )

    assert first.projection_build_id != second.projection_build_id


def test_rustworkx_projection_sets_truncated_when_edge_limit_is_hit() -> None:
    seed = node("default", "seed", "GraphRAG")
    targets = tuple(node("default", f"target-{index}", f"Target {index}") for index in range(3))
    relationships = tuple(edge(seed, target, f"rel-{index}") for index, target in enumerate(targets))

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, *targets),
            relationships=relationships,
            direction="out",
            limit=10,
            edge_limit=2,
        )
    )

    assert result.truncated is True
    assert result.edge_count == 2


def test_rustworkx_projection_applies_filters_before_edge_limit() -> None:
    seed = node("default", "seed", "GraphRAG")
    noise = tuple(node("default", f"noise-{index}", f"Noise {index}") for index in range(3))
    valid = node("default", "valid", "Valid Target")
    relationships = (
        *(replace(edge(seed, item, f"noise-{index}"), status="deprecated") for index, item in enumerate(noise)),
        edge(seed, valid, "rel-valid"),
    )

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, *noise, valid),
            relationships=relationships,
            direction="out",
            edge_limit=1,
        )
    )

    assert tuple(path.target.entity_id for path in result.paths) == ("valid",)
    assert result.edge_count == 1
    assert result.truncated is False


def test_rustworkx_projection_respects_in_direction() -> None:
    seed = node("default", "seed", "GraphRAG")
    source = node("default", "source", "Search")

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(source, seed),
            relationships=(edge(source, seed, "rel-in"),),
            direction="in",
        )
    )

    assert tuple(path.target.entity_id for path in result.paths) == ("source",)


def test_rustworkx_projection_respects_both_direction_without_duplicate_paths() -> None:
    seed = node("default", "seed", "GraphRAG")
    source = node("default", "source", "Search")

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(source, seed),
            relationships=(edge(source, seed, "rel-in"),),
            direction="both",
        )
    )

    assert tuple(path.target.entity_id for path in result.paths) == ("source",)
    assert len(result.paths) == 1


def test_rustworkx_projection_returns_depth_two_paths_with_depth_weight() -> None:
    seed = node("default", "seed", "GraphRAG")
    middle = node("default", "middle", "Search")
    target = node("default", "target", "Evidence")

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, middle, target),
            relationships=(edge(seed, middle, "rel-1"), edge(middle, target, "rel-2")),
            max_depth=2,
            direction="out",
        )
    )

    depth_two = next(path for path in result.paths if path.target.entity_id == "target")
    assert depth_two.depth == 2
    assert depth_two.score == pytest.approx(0.54)


def test_rustworkx_projection_omits_deprecated_edges_by_default() -> None:
    seed = node("default", "seed", "GraphRAG")
    target = node("default", "target", "Old Decision")
    deprecated = replace(edge(seed, target, "rel-deprecated"), status="deprecated")

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, target),
            relationships=(deprecated,),
            direction="out",
        )
    )

    assert result.paths == ()


def test_rustworkx_projection_scores_deprecated_edges_as_zero_when_requested() -> None:
    seed = node("default", "seed", "GraphRAG")
    target = node("default", "target", "Old Decision")
    deprecated = replace(edge(seed, target, "rel-deprecated"), status="deprecated")

    result = RustworkxGraphProjection().project(
        projection_input(
            seeds=(seed,),
            nodes=(seed, target),
            relationships=(deprecated,),
            direction="out",
            statuses=("deprecated",),
        )
    )

    assert result.paths[0].score == 0.0
