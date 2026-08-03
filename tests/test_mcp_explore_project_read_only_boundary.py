from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from tests.test_mcp_explore_project import _context
from tests.test_mcp_tools import fake_services
from tests.test_read_only_boundary import file_bytes
from vault_graph.mcp.context_pack_resource_cache import ContextPackResourceCache
from vault_graph.mcp.mcp_tools import ExploreProjectInput, McpToolRegistry
from vault_graph.mcp.result_explanation_cache import ResultExplanationCache


@dataclass
class _ProjectService:
    context: object

    def build(self, request: object) -> object:
        del request
        return self.context


class _Factory:
    def __init__(self, service: _ProjectService) -> None:
        self._service = service

    def open_project_context_service(self) -> _ProjectService:
        return self._service


def test_explore_project_adapter_does_not_write_vault_or_repository(tmp_path: Path) -> None:
    roots = tmp_path / "authorities"
    vault_root = roots / "vault"
    repository_root = roots / "repository"
    vault_root.mkdir(parents=True)
    repository_root.mkdir()
    (vault_root / "wiki.md").write_text("# Vault\n", encoding="utf-8")
    (repository_root / "module.py").write_text("def run(): pass\n", encoding="utf-8")
    before_vault = file_bytes(vault_root)
    before_repository = file_bytes(repository_root)
    registry = McpToolRegistry(
        services=fake_services(tmp_path),
        service_factory=cast(Any, _Factory(_ProjectService(_context()))),
        context_pack_cache=ContextPackResourceCache(),
        result_explanation_cache=ResultExplanationCache(),
    )

    registry.explore_project(ExploreProjectInput(task="Trace request", repository_id="demo"))

    assert file_bytes(vault_root) == before_vault
    assert file_bytes(repository_root) == before_repository
