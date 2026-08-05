from __future__ import annotations

import pytest

from vault_graph.project_context.project_context_models import (
    MAX_PROJECT_CONTEXT_DEPTH,
    MAX_PROJECT_CONTEXT_TOKENS,
    ProjectContextRequest,
)


def test_project_context_request_defaults_to_a_bounded_budget() -> None:
    request = ProjectContextRequest(task="Explain the indexing boundary")

    assert request.depth == 2
    assert request.limit == 20
    assert request.max_tokens == 4000


def test_project_context_request_rejects_unbounded_values() -> None:
    with pytest.raises(ValueError, match="max_tokens"):
        ProjectContextRequest(task="Explain", max_tokens=MAX_PROJECT_CONTEXT_TOKENS + 1)

    with pytest.raises(ValueError, match="depth"):
        ProjectContextRequest(task="Explain", depth=MAX_PROJECT_CONTEXT_DEPTH + 1)
