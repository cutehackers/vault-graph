from __future__ import annotations

import json
from typing import cast

from tests.test_mcp_explore_project import _context
from vault_graph.mcp.mcp_tool_serialization import project_context_to_payload, resource_links_for_project_context


def test_project_context_serialization_is_deterministic_and_source_body_free() -> None:
    context = _context()

    first = project_context_to_payload(context)
    second = project_context_to_payload(context)

    assert first == second
    assert json.dumps(first, sort_keys=True, separators=(",", ":"))
    assert "source_lines" not in repr(first)
    assert first["repository_id"] == "demo"
    binding = cast(dict[str, object], first["binding"])
    assert binding["vault_ids"] == ("main",)
    assert {link.uri for link in resource_links_for_project_context(context)} == {
        "vg-source://demo/src/demo.py#L3-L5",
        "vault://main/wiki/decision.md",
    }
