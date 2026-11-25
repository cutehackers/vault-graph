from __future__ import annotations

import pytest

from vault_graph.project.context.project_binding import ProjectBinding
from vault_graph.project.context.project_context_models import (
    MAX_PROJECT_CONTEXT_DEPTH,
    MAX_PROJECT_CONTEXT_TOKENS,
    ProjectContext,
    ProjectContextBudget,
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


def test_project_context_request_takes_an_optional_cwd() -> None:
    assert ProjectContextRequest(task="Explain").cwd is None
    assert ProjectContextRequest(task="Explain", cwd="/work/demo").cwd == "/work/demo"
    with pytest.raises(ValueError, match="cwd"):
        ProjectContextRequest(task="Explain", cwd=" ")


def test_project_context_allows_no_binding_but_binding_still_needs_vaults() -> None:
    context = ProjectContext(
        task="Explain",
        repository_id="git:demo",
        binding=None,
        freshness="fresh",
        code_evidence=(),
        vault_evidence=(),
        relations=(),
        authority_freshness=(),
        warnings=(),
        budget=ProjectContextBudget(max_tokens=4000, used_tokens=10),
    )

    assert context.binding is None
    with pytest.raises(ValueError, match="vault_ids"):
        ProjectBinding("git:demo", ())
