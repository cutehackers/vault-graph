"""A-21: a ``remember`` draft names the ``cwd`` project, and correction or rule memories carry a tag.

The Vault project summary (vault-builder ``tools/wiki/lib/maps.py`` ``_project_summary_pages``) lists a
page under a project only when frontmatter ``project`` names it, and lists it as a correction only when
``tags`` holds ``correction`` or ``rule`` (``PROJECT_CORRECTION_TAGS``).
"""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from vault_graph.interface.composition.adapters.vault_publish_cli import VaultPublishCli
from vault_graph.interface.mcp.mcp_memory_tools import McpMemoryTools, RememberInput, UpdateMemoryInput
from vault_graph.interface.mcp.mcp_service_factory import McpServiceFactory
from vault_graph.operation.integration.vault_map import VAULT_MAP_ENV
from vault_graph.operation.memory.memory_drafts import build_remember_draft, build_update_draft
from vault_graph.operation.memory.memory_ports import PageText, WriteOutcome
from vault_graph.operation.memory.memory_requests import RememberRequest, UpdateRequest

TODAY = date(2026, 11, 6)


def _remember(*, project_id: str | None, memory_kind: str | None) -> RememberRequest:
    return RememberRequest(
        title="Use SQLite",
        kind="decision",
        body="We use SQLite.",
        evidence=("docs/a.md",),
        basis="stated",
        memory_kind=memory_kind,
        project_id=project_id,
    )


def _frontmatter(draft: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], draft["frontmatter"])


@pytest.mark.parametrize("memory_kind", ["correction", "rule"])
def test_remember_draft_in_a_project_has_project_and_kind_tag(memory_kind: str) -> None:
    frontmatter = _frontmatter(
        build_remember_draft(_remember(project_id="vault-graph", memory_kind=memory_kind), today=TODAY)
    )

    assert frontmatter["project"] == "vault-graph"
    assert frontmatter["tags"] == [memory_kind]


@pytest.mark.parametrize("memory_kind", [None, "decision", "preference"])
def test_remember_draft_tags_stay_empty_for_other_memory_kinds(memory_kind: str | None) -> None:
    frontmatter = _frontmatter(
        build_remember_draft(_remember(project_id="vault-graph", memory_kind=memory_kind), today=TODAY)
    )

    assert frontmatter["project"] == "vault-graph"
    assert frontmatter["tags"] == []


def test_remember_draft_outside_a_project_has_no_project() -> None:
    frontmatter = _frontmatter(build_remember_draft(_remember(project_id=None, memory_kind="correction"), today=TODAY))

    assert "project" not in frontmatter


def test_update_draft_keeps_the_current_project() -> None:
    page = PageText(
        text="---\ntitle: Use SQLite\ntype: decision\nproject: vault-graph\ntags: []\n---\n# Use SQLite\n\nOld.\n",
        sha256="x",
    )
    request = UpdateRequest(
        path="wiki/decisions/use-sqlite.md", body="New.", evidence=("e",), basis="stated", memory_kind="correction"
    )

    frontmatter = _frontmatter(build_update_draft(request, page, today=TODAY))

    assert frontmatter["project"] == "vault-graph"


# --- MCP: the write tool finds the project id from ``cwd`` -----------------------------------------


@pytest.fixture
def mapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, list[dict[str, Any]]]:
    """A git repo linked as project ``proj`` to Vault ``main``, and a publish stand-in that keeps drafts."""
    vault = tmp_path / "vault"
    (vault / "wiki" / "decisions").mkdir(parents=True)
    (vault / "wiki" / "decisions" / "use-sqlite.md").write_text(
        "---\ntitle: Use SQLite\ntype: decision\nstatus: active\nproject: other\n---\n# Use SQLite\n\nOld.\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    map_file = tmp_path / "vault-map.json"
    map_file.write_text(
        json.dumps(
            {
                "version": 2,
                "vaults": {"main": {"path": str(vault), "role": "project"}},
                "projects": {"proj": {"root": str(repo), "vaults": ["main"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(VAULT_MAP_ENV, str(map_file))
    drafts: list[dict[str, Any]] = []

    def stand_in(self: VaultPublishCli, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        drafts.append(json.loads(draft_path.read_text(encoding="utf-8")))
        return WriteOutcome(status="published", written_paths=(str(drafts[-1]["path"]),))

    monkeypatch.setattr(VaultPublishCli, "publish", stand_in)
    return map_file, repo, drafts


def _tools(tmp_path: Path, map_file: Path) -> McpMemoryTools:
    factory = McpServiceFactory(graph_home_path=tmp_path / "state", vault_map_path=map_file)
    factory.start_background_index = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return McpMemoryTools(service_factory=factory, on_index_finished=lambda _: None)


def test_mcp_remember_in_a_project_folder_writes_project_and_tag(
    tmp_path: Path, mapped: tuple[Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, repo, drafts = mapped

    body = _tools(tmp_path, map_file).remember(
        RememberInput(
            title="Do not mock the database",
            kind="decision",
            body="Tests use a real database.",
            evidence=("user said so",),
            basis="stated",
            cwd=str(repo),
            memory_kind="correction",
        )
    )

    assert body.payload["status"] == "published"
    assert drafts[0]["frontmatter"]["project"] == "proj"
    assert drafts[0]["frontmatter"]["tags"] == ["correction"]


def test_mcp_remember_outside_a_project_writes_no_project(
    tmp_path: Path, mapped: tuple[Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, _, drafts = mapped
    outside = tmp_path / "outside"
    outside.mkdir()

    body = _tools(tmp_path, map_file).remember(
        RememberInput(
            title="Loose note",
            kind="decision",
            body="Body.",
            evidence=("e",),
            basis="stated",
            cwd=str(outside),
            vault="main",
            memory_kind="rule",
        )
    )

    assert body.payload["status"] == "published"
    assert "project" not in drafts[0]["frontmatter"]
    assert drafts[0]["frontmatter"]["tags"] == ["rule"]


def test_mcp_update_memory_keeps_the_page_project(
    tmp_path: Path, mapped: tuple[Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, repo, drafts = mapped

    body = _tools(tmp_path, map_file).update_memory(
        UpdateMemoryInput(
            path="wiki/decisions/use-sqlite.md", body="New.", evidence=("e",), basis="stated", cwd=str(repo)
        )
    )

    assert body.payload["status"] == "published"
    assert drafts[0]["frontmatter"]["project"] == "other"
