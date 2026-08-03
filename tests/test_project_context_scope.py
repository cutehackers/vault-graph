from __future__ import annotations

import pytest

from vault_graph.project_context import ProjectFreshness, combine_freshness


@pytest.mark.parametrize(
    ("states", "expected"),
    [
        (("fresh", "stale"), "stale"),
        (("stale", "unknown"), "unknown"),
        (("unknown", "syncing"), "syncing"),
        (("syncing", "partial"), "partial"),
        (("partial", "unavailable"), "unavailable"),
    ],
)
def test_project_context_freshness_uses_authority_precedence(
    states: tuple[ProjectFreshness, ...], expected: ProjectFreshness
) -> None:
    assert combine_freshness(states) == expected
