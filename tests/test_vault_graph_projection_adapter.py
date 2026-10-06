from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from itertools import permutations
from typing import Literal

import pytest
from graph_search import GraphSearchError, Path, PathSummary, TraversalStep

from tests.fakes.legacy_graph_projection import LegacyGraphProjection
from tests.test_graph_projection import edge, node, projection_input
from vault_graph.projection.vault_graph_projection_adapter import VaultGraphProjectionAdapter


@pytest.mark.parametrize("direction", ["out", "in", "both"])
@pytest.mark.parametrize("depth", [1, 2])
def test_adapter_preserves_complete_legacy_response(direction: Literal["out", "in", "both"], depth: int) -> None:
    seed = node("a", "seed", "Seed")
    middle = node("a", "middle", "Same name")
    other = node("b", "other", "Same name")
    target = node("a", "target", "Target")
    duplicate_seed = replace(seed, name="Alternate seed")
    rows = (
        edge(seed, middle, "duplicate"),
        replace(edge(seed, middle, "duplicate"), confidence=0.4, evidence_ref_ids=("different",)),
        edge(other, middle, "duplicate"),
        edge(middle, target, "last"),
        edge(target, seed, "cycle"),
        edge(seed, seed, "self"),
    )
    for order in (rows, tuple(reversed(rows))):
        request = replace(
            projection_input(
                seeds=(seed, duplicate_seed),
                nodes=(seed, middle, other, target, replace(middle, name="ignored")),
                relationships=order,
                direction=direction,
                max_depth=depth,
                limit=2,
            ),
            include_cross_vault=True,
        )
        assert VaultGraphProjectionAdapter().project(request) == LegacyGraphProjection().project(request)


def test_adapter_preserves_first_native_duplicate_and_stable_ties() -> None:
    seed = node("a", "seed", "Seed")
    target = node("a", "target", "Target")
    rows = (
        replace(edge(seed, target, "same"), confidence=0.1, evidence_ref_ids=("first",)),
        replace(edge(seed, target, "same"), confidence=0.9, evidence_ref_ids=("second",)),
        edge(target, seed, "reverse"),
    )
    for order in permutations(rows):
        request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=order, max_depth=2)
        assert VaultGraphProjectionAdapter().project(request) == LegacyGraphProjection().project(request)


@pytest.mark.parametrize("filtered", [False, True])
def test_adapter_preserves_empty_selected_graph(filtered: bool) -> None:
    seed = node("v", "seed", "Seed")
    target = node("v", "target", "Target")
    request = projection_input(
        seeds=(seed,),
        nodes=(seed, target),
        relationships=(edge(seed, target),) if filtered else (),
        relationship_types=("blocks",) if filtered else (),
    )
    assert VaultGraphProjectionAdapter().project(request) == LegacyGraphProjection().project(request)


def test_adapter_matches_frozen_oracle_across_generated_multigraphs() -> None:
    import random

    randomizer = random.Random(20261004)
    for _ in range(80):
        nodes = tuple(node(f"v{index % 2}", f"n{index}", f"Name {index % 2}") for index in range(5))
        rows = tuple(
            replace(
                edge(randomizer.choice(nodes), randomizer.choice(nodes), f"r{randomizer.randrange(3)}"),
                status=randomizer.choice(("stated", "inferred", "deprecated")),
                confidence=randomizer.choice((0.2, 0.9, 1.0)),
                relationship_type=randomizer.choice(("related_to", "blocks", "mentions")),
            )
            for _ in range(12)
        )
        for direction in ("out", "in", "both"):
            request = replace(
                projection_input(
                    seeds=nodes[: randomizer.randrange(1, 4)],
                    nodes=nodes,
                    relationships=rows,
                    direction=direction,
                    max_depth=2,
                    edge_limit=randomizer.randrange(1, 13),
                    limit=3,
                    statuses=("stated", "inferred"),
                ),
                include_cross_vault=bool(randomizer.randrange(2)),
            )
            assert VaultGraphProjectionAdapter().project(request) == LegacyGraphProjection().project(request)


def test_explicit_execution_budget_never_publishes_partial_ranking() -> None:
    from vault_graph.errors import GraphStoreError
    from vault_graph.projection.vault_graph_projection_adapter import ProjectionExecutionLimits

    seed = node("v", "s", "Seed")
    target = node("v", "t", "Target")
    request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=(edge(seed, target),))
    adapter = VaultGraphProjectionAdapter(execution_limits=ProjectionExecutionLimits(2, 0, 1, 1, 1, 32, 128))
    with pytest.raises(GraphStoreError, match="graph_projection_budget_exceeded"):
        adapter.project(request)


@pytest.mark.parametrize(
    "changes",
    [{"max_input_relationships": 0}, {"max_original_id_bytes": 1}, {"max_total_original_id_bytes": 1}],
)
def test_prefilter_input_budgets_reject_oversized_requests(changes: dict[str, int]) -> None:
    from vault_graph.errors import GraphStoreError
    from vault_graph.projection.vault_graph_projection_adapter import ProjectionExecutionLimits

    seed = node("한", "seed", "Seed")
    target = node("한", "target", "Target")
    request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=(edge(seed, target),))
    limits = replace(ProjectionExecutionLimits(2, 10, 10, 10, 1, 32, 128), **changes)
    with pytest.raises(GraphStoreError, match="graph_projection_budget_exceeded"):
        VaultGraphProjectionAdapter(execution_limits=limits).project(request)


def test_legacy_native_incident_order_used_by_compatibility_adapter() -> None:
    import rustworkx

    graph = rustworkx.PyDiGraph(multigraph=True)
    source, target = graph.add_nodes_from(("source", "target"))
    graph.add_edge(source, target, "first")
    graph.add_edge(source, target, "second")
    assert [payload for _, _, payload in graph.out_edges(source)] == ["second", "first"]
    assert [payload for _, _, payload in graph.in_edges(target)] == ["second", "first"]


@pytest.mark.parametrize("missing", ["node", "edge"])
def test_invalid_engine_mapping_surfaces_as_graph_store_error(monkeypatch: pytest.MonkeyPatch, missing: str) -> None:
    from vault_graph.errors import GraphStoreError

    seed = node("v", "s", "Seed")
    target = node("v", "t", "Target")
    request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=(edge(seed, target),))

    @contextmanager
    def invalid_paths(*args: object, **kwargs: object) -> Iterator[Iterator[Path]]:
        yield iter(
            (
                Path(
                    ("n000000000000", "missing" if missing == "node" else "n000000000001"),
                    (TraversalStep("missing", "n000000000000", "n000000000001", False),),
                ),
            )
        )

    monkeypatch.setattr("vault_graph.projection.vault_graph_projection_adapter.search_paths", invalid_paths)
    with pytest.raises(GraphStoreError, match="mapping failed") as raised:
        VaultGraphProjectionAdapter().project(request)
    assert isinstance(raised.value.__cause__, KeyError)


@pytest.mark.parametrize("stop", ["path_limit", "edge_limit", "cancelled", "failed", None])
def test_incomplete_engine_traversal_never_returns_partial_ranking(
    monkeypatch: pytest.MonkeyPatch,
    stop: Literal["path_limit", "edge_limit", "cancelled", "failed"] | None,
) -> None:
    from vault_graph.errors import GraphStoreError

    seed = node("v", "s", "Seed")
    target = node("v", "t", "Target")
    request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=(edge(seed, target),))

    class IncompleteTraversal(Iterator[Path]):
        def __init__(self) -> None:
            self.summary = PathSummary(stop, 1, 1) if stop is not None else None
            self._paths = iter(
                (
                    Path(
                        ("n000000000000", "n000000000001"),
                        (TraversalStep("e000000000000", "n000000000000", "n000000000001", False),),
                    ),
                )
            )

        def __next__(self) -> Path:
            return next(self._paths)

    @contextmanager
    def incomplete_paths(*args: object, **kwargs: object) -> Iterator[IncompleteTraversal]:
        yield IncompleteTraversal()

    monkeypatch.setattr("vault_graph.projection.vault_graph_projection_adapter.search_paths", incomplete_paths)
    with pytest.raises(GraphStoreError, match="incomplete traversal"):
        VaultGraphProjectionAdapter().project(request)


def test_engine_fault_preserves_its_cause(monkeypatch: pytest.MonkeyPatch) -> None:
    from vault_graph.errors import GraphStoreError

    seed = node("v", "s", "Seed")
    target = node("v", "t", "Target")
    request = projection_input(seeds=(seed,), nodes=(seed, target), relationships=(edge(seed, target),))
    error = GraphSearchError("engine fault")

    def failed_paths(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr("vault_graph.projection.vault_graph_projection_adapter.search_paths", failed_paths)
    with pytest.raises(GraphStoreError, match="traversal failed") as raised:
        VaultGraphProjectionAdapter().project(request)
    assert raised.value.__cause__ is error
