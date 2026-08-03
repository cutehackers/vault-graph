from __future__ import annotations

from pathlib import Path

from tests.test_project_context_service import _Code, _service
from vault_graph.project_context import ProjectContextRequest


def test_project_context_query_does_not_write_vault_or_repository(tmp_path: Path) -> None:
    service = _service(tmp_path, code=_Code())
    repository = tmp_path / "repository"
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "wiki.md").write_text("durable knowledge", encoding="utf-8")
    before_repository = tuple(sorted(path.relative_to(repository) for path in repository.rglob("*")))
    before_vault = (vault / "wiki.md").read_bytes()

    service.build(ProjectContextRequest(task="Find the implementation"))

    assert tuple(sorted(path.relative_to(repository) for path in repository.rglob("*"))) == before_repository
    assert (vault / "wiki.md").read_bytes() == before_vault
