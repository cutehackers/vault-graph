"""A-27 (S12, vg side): ``remember(kind="project")`` writes the first project brief (spec 2026-11-05 §4.4.7).

The brief path comes from the ``cwd`` project id, not the title: ``wiki/projects/<project>.md`` with
frontmatter ``type: project`` and ``project: <id>``. The Vault (vault-builder ``tools/wiki/lib/schema.py``
``_validate_project_page_path``) rejects any other path, name or ``project`` value with ``project-page-path``.
Without a ``cwd`` project the call is rejected, and a second brief is rejected with a pointer to ``update_memory``.
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
from vault_graph.operation.memory.memory_drafts import build_remember_draft
from vault_graph.operation.memory.memory_ports import WriteOutcome
from vault_graph.operation.memory.memory_requests import REMEMBER_KINDS, RememberRequest, validate_remember

TODAY = date(2026, 11, 6)


def _brief(*, project_id: str | None, title: str = "Vault Graph brief") -> RememberRequest:
    return RememberRequest(
        title=title,
        kind="project",
        body="Goal: evidence-first context.",
        evidence=("docs/SPEC.md",),
        basis="stated",
        project_id=project_id,
    )


def test_project_is_an_allowed_remember_kind_after_the_old_ones() -> None:
    assert REMEMBER_KINDS == ("decision", "system", "project")


def test_brief_draft_path_type_and_project_follow_the_project_id() -> None:
    draft = build_remember_draft(_brief(project_id="vault-graph", title="Anything At All"), today=TODAY)
    frontmatter = cast(dict[str, Any], draft["frontmatter"])
    index = cast(dict[str, Any], draft["index"])
    log = cast(dict[str, Any], draft["log"])

    assert draft["path"] == "wiki/projects/vault-graph.md"
    assert frontmatter["type"] == "project"
    assert frontmatter["project"] == "vault-graph"
    assert frontmatter["title"] == "Anything At All"
    assert index["target"] == "projects/vault-graph"
    assert log["event_type"] == "manual-note"


def test_brief_without_a_project_is_rejected_by_validation() -> None:
    problems = validate_remember(_brief(project_id=None))

    assert len(problems) == 1
    assert "project folder" in problems[0]


@pytest.mark.parametrize("project_id", ["../x", "a/b", "-lead", ""])
def test_brief_with_a_project_id_the_vault_rejects_is_refused(project_id: str) -> None:
    assert validate_remember(_brief(project_id=project_id))


def test_other_kinds_without_a_project_stay_valid() -> None:
    request = RememberRequest(title="T", kind="decision", body="B", evidence=("e",), basis="stated")

    assert validate_remember(request) == ()


# --- MCP: the brief goes through the write service and the cwd project ---------------------------


@pytest.fixture
def mapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path, list[dict[str, Any]]]:
    """A git repo linked as project ``proj`` to Vault ``main``, and a publish stand-in that writes the page."""
    vault = tmp_path / "vault"
    (vault / "wiki").mkdir(parents=True)
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
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        drafts.append(draft)
        page = vault_root / str(draft["path"])
        page.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(f"{key}: {value}\n" for key, value in draft["frontmatter"].items() if isinstance(value, str))
        page.write_text(f"---\n{lines}---\n{draft['body']}", encoding="utf-8")
        return WriteOutcome(status="published", written_paths=(str(draft["path"]),))

    monkeypatch.setattr(VaultPublishCli, "publish", stand_in)
    return map_file, repo, vault, drafts


def _tools(tmp_path: Path, map_file: Path) -> McpMemoryTools:
    factory = McpServiceFactory(graph_home_path=tmp_path / "state", vault_map_path=map_file)
    factory.start_background_index = lambda *args, **kwargs: None  # type: ignore[method-assign]
    return McpMemoryTools(service_factory=factory, on_index_finished=lambda _: None)


def _brief_input(cwd: Path, **changes: Any) -> RememberInput:
    values: dict[str, Any] = {
        "title": "Proj brief",
        "kind": "project",
        "body": "Goal: ship v1.",
        "evidence": ("docs/plan.md",),
        "basis": "stated",
        "cwd": str(cwd),
    }
    values.update(changes)
    return RememberInput(**values)


def test_mcp_remember_project_writes_the_brief_of_the_cwd_project(
    tmp_path: Path, mapped: tuple[Path, Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, repo, vault, drafts = mapped

    body = _tools(tmp_path, map_file).remember(_brief_input(repo))

    assert body.payload["status"] == "published"
    assert body.payload["vault"] == "main"
    assert drafts[0]["path"] == "wiki/projects/proj.md"
    assert drafts[0]["frontmatter"]["type"] == "project"
    assert drafts[0]["frontmatter"]["project"] == "proj"
    assert (vault / "wiki" / "projects" / "proj.md").is_file()


def test_mcp_remember_project_outside_a_project_is_rejected(
    tmp_path: Path, mapped: tuple[Path, Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, _, _, drafts = mapped
    outside = tmp_path / "outside"
    outside.mkdir()

    body = _tools(tmp_path, map_file).remember(_brief_input(outside, vault="main"))

    assert body.payload["status"] == "rejected"
    assert any("project folder" in message for message in cast(list[str], body.payload["messages"]))
    assert drafts == []


def test_mcp_second_brief_is_rejected_and_update_memory_changes_it(
    tmp_path: Path, mapped: tuple[Path, Path, Path, list[dict[str, Any]]]
) -> None:
    map_file, repo, _, drafts = mapped
    tools = _tools(tmp_path, map_file)
    assert tools.remember(_brief_input(repo)).payload["status"] == "published"

    second = tools.remember(_brief_input(repo, title="Another title"))

    assert second.payload["status"] == "rejected"
    assert any("update_memory" in message for message in cast(list[str], second.payload["messages"]))
    assert len(drafts) == 1

    updated = tools.update_memory(
        UpdateMemoryInput(
            path="wiki/projects/proj.md", body="Goal: ship v2.", evidence=("e",), basis="stated", cwd=str(repo)
        )
    )

    assert updated.payload["status"] == "published"
    assert drafts[1]["path"] == "wiki/projects/proj.md"
    assert drafts[1]["frontmatter"]["type"] == "project"
    assert drafts[1]["frontmatter"]["project"] == "proj"


def test_mcp_vault_rejection_of_a_brief_is_passed_on(
    tmp_path: Path, mapped: tuple[Path, Path, Path, list[dict[str, Any]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before the Vault knows type project it rejects the draft; vg returns rejected with its message."""
    map_file, repo, _, _ = mapped
    vault_message = "[error] invalid-type - Invalid type: project."

    def refuse(self: VaultPublishCli, vault_root: Path, draft_path: Path, *, timeout_s: float) -> WriteOutcome:
        return WriteOutcome(status="rejected", messages=(vault_message,))

    monkeypatch.setattr(VaultPublishCli, "publish", refuse)

    body = _tools(tmp_path, map_file).remember(_brief_input(repo))

    assert body.payload["status"] == "rejected"
    assert vault_message in cast(list[str], body.payload["messages"])


def test_mcp_brief_to_a_vault_other_than_the_default_is_rejected(
    tmp_path: Path, mapped: tuple[Path, Path, Path, list[dict[str, Any]]]
) -> None:
    """Recall reads a brief only from the project's default write Vault (spec §4.4.7)."""
    map_file, repo, vault, drafts = mapped
    personal = tmp_path / "personal"
    (personal / "wiki").mkdir(parents=True)
    payload = json.loads(map_file.read_text(encoding="utf-8"))
    payload["vaults"]["personal"] = {"path": str(personal), "role": "personal"}
    payload["projects"]["proj"]["vaults"] = ["main", "personal"]
    payload["projects"]["proj"]["default_write_vault"] = "main"
    map_file.write_text(json.dumps(payload), encoding="utf-8")
    tools = _tools(tmp_path, map_file)

    other = tools.remember(_brief_input(repo, vault="personal"))
    named_default = tools.remember(_brief_input(repo, vault="main"))

    assert other.payload["status"] == "rejected"
    assert any("default write Vault" in message for message in cast(list[str], other.payload["messages"]))
    assert not (personal / "wiki" / "projects").exists()
    assert named_default.payload["status"] == "published"
    assert [draft["path"] for draft in drafts] == ["wiki/projects/proj.md"]
