from __future__ import annotations

from types import SimpleNamespace

import pytest

from vault_graph.project_context import ProjectFreshness, combine_freshness
from vault_graph.project_context.project_context_service import _vault_freshness_from_status


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


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        (SimpleNamespace(metadata_ok=False, metadata_schema_compatible=True), "unavailable"),
        (
            SimpleNamespace(
                metadata_ok=True,
                metadata_schema_compatible=True,
                vector_schema_compatible=True,
                vector_ok=True,
                vector_stale_count=1,
                vector_last_error=None,
                graph_readiness=SimpleNamespace(freshness="fresh"),
                graph_last_error=None,
            ),
            "stale",
        ),
        (
            SimpleNamespace(
                metadata_ok=True,
                metadata_schema_compatible=True,
                vector_schema_compatible=True,
                vector_ok=True,
                vector_stale_count=0,
                vector_last_error=None,
                graph_readiness=SimpleNamespace(freshness="syncing"),
                graph_last_error=None,
            ),
            "syncing",
        ),
    ],
)
def test_vault_status_mapping_preserves_projection_state_precedence(report: object, expected: ProjectFreshness) -> None:
    assert _vault_freshness_from_status(report)[0] == expected
